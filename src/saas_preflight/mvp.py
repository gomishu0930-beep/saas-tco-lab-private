"""Content-addressed, fail-closed local MVP delivery.

The module is deliberately pure: it opens no socket, writes no file, and does
not publish.  An outer HTTP adapter can translate ``MvpResponse`` values after
a separately approved production deployment exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from urllib.parse import urlsplit

from .control_cycle import (
    Ed25519VerificationKey,
    LeaseScope,
    ServingLease,
    verify_serving_lease,
)
from .preview import PreviewPage, cta_visible, data_visible, render_preview
from .release import CtaDecision, ReleaseState, evaluate_visibility


_SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    (
        "Content-Security-Policy",
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'",
    ),
    ("Referrer-Policy", "no-referrer"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("X-Robots-Tag", "noindex, nofollow, noarchive, nosnippet"),
)


def _require_utc(value: datetime, name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _page_without_cta(page: PreviewPage) -> PreviewPage:
    return page.model_copy(
        update={
            "plans": tuple(
                plan.model_copy(
                    update={
                        "affiliate_active": False,
                        "affiliate_url": None,
                        "affiliate_expires_at": None,
                    }
                )
                for plan in page.plans
            )
        }
    )


@dataclass(frozen=True, slots=True)
class MvpArtifact:
    """Immutable HTML bundle and the hashes required to authorize its CTA."""

    built_at: datetime
    home_html: str
    comparison_html: str
    comparison_redacted_html: str
    methodology_html: str
    disclosure_html: str
    destination_bundle_sha256: str
    disclosure_sha256: str
    has_active_cta: bool
    artifact_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_utc(self.built_at, "built_at")
        bodies = (
            self.home_html,
            self.comparison_html,
            self.comparison_redacted_html,
            self.methodology_html,
            self.disclosure_html,
        )
        if any(type(body) is not str or not body for body in bodies):
            raise TypeError("MVP route bodies must be non-empty strings")
        for name, digest in (
            ("destination_bundle_sha256", self.destination_bundle_sha256),
            ("disclosure_sha256", self.disclosure_sha256),
        ):
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if type(self.has_active_cta) is not bool:
            raise TypeError("has_active_cta must be a bool")
        canonical = json.dumps(
            {
                "built_at": self.built_at.isoformat().replace("+00:00", "Z"),
                "routes": {
                    "/": self.home_html,
                    "/comparison/": self.comparison_html,
                    "/comparison/redacted/": self.comparison_redacted_html,
                    "/disclosure/": self.disclosure_html,
                    "/methodology/": self.methodology_html,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(self, "artifact_sha256", _sha256_text(canonical))


@dataclass(frozen=True, slots=True)
class MvpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: str

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers:
            if key.lower() == lowered:
                return value
        return None


def build_mvp_artifact(page: PreviewPage, *, at: datetime) -> MvpArtifact:
    """Build a local candidate only while every numeric input is current."""

    instant = _require_utc(at, "at")
    if page.rendered_at > instant:
        raise ValueError("preview rendered_at cannot be in the future")
    expired_rows = [
        f"{plan.vendor_slug}/{plan.plan_slug}"
        for plan in page.plans
        if not data_visible(plan, at=instant)
    ]
    if expired_rows:
        raise ValueError("cannot build from expired data or rights")
    invalid_ctas = [
        f"{plan.vendor_slug}/{plan.plan_slug}"
        for plan in page.plans
        if plan.affiliate_active and not cta_visible(plan, at=instant)
    ]
    if invalid_ctas:
        raise ValueError("cannot build with an expired affiliate CTA")

    destinations = sorted(
        str(plan.affiliate_url)
        for plan in page.plans
        if plan.affiliate_active and plan.affiliate_url is not None
    )
    disclosure_hash = _sha256_text(page.affiliate_disclosure)
    destination_hash = _sha256_text(
        json.dumps(destinations, ensure_ascii=False, separators=(",", ":"))
    )
    redacted = _page_without_cta(page)
    common_note = "公開前MVP。検索index、外部送客、production保存を行いません。"
    return MvpArtifact(
        built_at=instant,
        home_html=_simple_page(
            "SaaS比較 公開前MVP",
            common_note,
            '<nav aria-label="MVP"><a href="/comparison/">比較</a> '
            '<a href="/methodology/">算定方法</a> '
            '<a href="/disclosure/">広告表示</a></nav>',
        ),
        comparison_html=render_preview(page, at=instant),
        comparison_redacted_html=render_preview(redacted, at=instant),
        methodology_html=_simple_page(
            "算定方法",
            "画面では再計算せず、承認済み根拠からcanonical Python TCOが生成した値だけを表示します。",
            "<p>region、tax、currency、billing、commitment、scenario、根拠時刻、期限を同時に記録します。</p>",
        ),
        disclosure_html=_simple_page(
            "広告表示",
            page.affiliate_disclosure,
            "<p>提携の有無をTCOや適合判定へ混入させず、失効したCTAは配信時に停止します。</p>",
        ),
        destination_bundle_sha256=destination_hash,
        disclosure_sha256=disclosure_hash,
        has_active_cta=bool(destinations),
    )


class LocalPreviewRuntime:
    """Local-only preview; never use this bypass as a production entry point."""

    def __init__(self, artifact: MvpArtifact, state: ReleaseState) -> None:
        if type(artifact) is not MvpArtifact or type(state) is not ReleaseState:
            raise TypeError("LocalPreviewRuntime requires MvpArtifact and ReleaseState")
        self._artifact = artifact
        self._state = state

    def handle(self, target: str, *, method: str = "GET", at: datetime) -> MvpResponse:
        instant = _require_utc(at, "at")
        if type(target) is not str or not target.startswith("/"):
            raise ValueError("target must be an absolute-path request target")
        if method not in ("GET", "HEAD"):
            return _response(405, "Method Not Allowed", method=method, allow="GET, HEAD")
        path = urlsplit(target).path
        routes = {
            "/": self._artifact.home_html,
            "/methodology/": self._artifact.methodology_html,
            "/disclosure/": self._artifact.disclosure_html,
        }
        if path == "/robots.txt":
            return _response(
                200,
                "User-agent: *\nDisallow: /\n",
                method=method,
                content_type="text/plain; charset=utf-8",
            )
        if path == "/healthz":
            return _response(200, "ok\n", method=method, content_type="text/plain; charset=utf-8")
        if path not in routes and path != "/comparison/":
            return _response(404, "Not Found", method=method)
        if not self._artifact_matches_current_release():
            return _response(503, _unavailable_page(), method=method)
        if path in routes:
            return _response(200, routes[path], method=method)

        visibility = evaluate_visibility(self._state, at=instant)
        if not visibility.visible:
            return _response(503, _unavailable_page(), method=method)
        if self._cta_authorized(visibility.cta_enabled):
            body = self._artifact.comparison_html
        else:
            body = self._artifact.comparison_redacted_html
        return _response(200, body, method=method)

    def _artifact_matches_current_release(self) -> bool:
        if self._state.current_release_id is None:
            return False
        manifest = self._state.get(self._state.current_release_id)
        return manifest.artifact_sha256 == self._artifact.artifact_sha256

    def _cta_authorized(self, cta_enabled: bool) -> bool:
        if not self._artifact.has_active_cta or not cta_enabled:
            return False
        assert self._state.current_release_id is not None
        manifest = self._state.get(self._state.current_release_id)
        return (
            manifest.cta.decision is CtaDecision.APPROVED
            and manifest.cta.destination_sha256
            == self._artifact.destination_bundle_sha256
            and manifest.cta.disclosure_sha256 == self._artifact.disclosure_sha256
        )


class ControlledMvpRuntime:
    """Production boundary that requires a current content-bound serving lease."""

    _PROTECTED_PATHS = frozenset(
        {"/", "/comparison/", "/methodology/", "/disclosure/"}
    )

    def __init__(
        self,
        artifact: MvpArtifact,
        state: ReleaseState,
        lease: ServingLease | None,
        *,
        controller_verification_key: Ed25519VerificationKey,
        expected_issuer: str,
        expected_scope: LeaseScope,
        maximum_ttl_seconds: int,
    ) -> None:
        if type(artifact) is not MvpArtifact or type(state) is not ReleaseState:
            raise TypeError("ControlledMvpRuntime requires MvpArtifact and ReleaseState")
        if lease is not None and type(lease) is not ServingLease:
            raise TypeError("lease must be ServingLease or None")
        if type(controller_verification_key) is not Ed25519VerificationKey:
            raise TypeError("controller_verification_key must be Ed25519VerificationKey")
        if type(expected_issuer) is not str or not expected_issuer:
            raise TypeError("expected_issuer must be a non-empty string")
        if type(expected_scope) is not LeaseScope:
            raise TypeError("expected_scope must be LeaseScope")
        if type(maximum_ttl_seconds) is not int or not 1 <= maximum_ttl_seconds <= 3600:
            raise ValueError("maximum_ttl_seconds must be from 1 through 3600")
        self._artifact = artifact
        self._state = state
        self._lease = lease
        self._controller_verification_key = Ed25519VerificationKey.model_validate(
            controller_verification_key.model_dump()
        )
        self._expected_issuer = expected_issuer
        self._expected_scope = expected_scope
        self._maximum_ttl_seconds = maximum_ttl_seconds
        self._runtime = LocalPreviewRuntime(artifact, state)

    def handle(self, target: str, *, method: str = "GET", at: datetime) -> MvpResponse:
        instant = _require_utc(at, "at")
        if type(target) is not str or not target.startswith("/"):
            raise ValueError("target must be an absolute-path request target")
        path = urlsplit(target).path
        if path in self._PROTECTED_PATHS and not self._lease_authorized(at=instant):
            return _response(503, _unavailable_page(), method=method)
        return self._runtime.handle(target, method=method, at=instant)

    def _lease_authorized(self, *, at: datetime) -> bool:
        lease = self._lease
        if lease is None:
            return False
        if not verify_serving_lease(
            lease,
            self._controller_verification_key,
            expected_issuer=self._expected_issuer,
            expected_scope=self._expected_scope,
            maximum_ttl_seconds=self._maximum_ttl_seconds,
            at=at,
        ):
            return False
        if self._state.current_release_id is None:
            return False
        manifest = self._state.get(self._state.current_release_id)
        return (
            lease.release_id == manifest.release_id
            and lease.manifest_sha256 == manifest.manifest_sha256
            and lease.artifact_sha256 == manifest.artifact_sha256
            and lease.artifact_sha256 == self._artifact.artifact_sha256
        )


def _simple_page(title: str, lead: str, content: str) -> str:
    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow,noarchive">'
        f"<title>{escape(title)}</title></head><body><header>NOINDEX / LOCAL PREFLIGHT</header>"
        f"<main><h1>{escape(title)}</h1><p>{escape(lead)}</p>{content}</main>"
        "<footer>Human GOまでは公開しません。</footer></body></html>"
    )


def _unavailable_page() -> str:
    return _simple_page(
        "比較情報を確認中",
        "根拠または公開状態を確認できないため、比較情報と広告リンクを停止しています。",
        "<p>有効なreleaseが確認できるまでお待ちください。</p>",
    )


def _response(
    status: int,
    body: str,
    *,
    method: str,
    content_type: str = "text/html; charset=utf-8",
    allow: str | None = None,
) -> MvpResponse:
    headers = list(_SECURITY_HEADERS)
    headers.append(("Content-Type", content_type))
    if allow is not None:
        headers.append(("Allow", allow))
    return MvpResponse(status=status, headers=tuple(headers), body="" if method == "HEAD" else body)


__all__ = [
    "ControlledMvpRuntime",
    "MvpArtifact",
    "MvpResponse",
    "build_mvp_artifact",
]
