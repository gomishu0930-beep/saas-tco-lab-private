from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from saas_preflight.models import (
    AcquisitionMethod,
    PolicyDecision,
    SourcePolicy,
)
from saas_preflight.source_access import (
    ResponseRejectedError,
    RetryAfterError,
    SourcePermissionError,
    UnsafeDestinationError,
    fetch_approved_source,
)


NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)
URL = "https://vendor.example/pricing"
PUBLIC = lambda host, port: ("93.184.216.34",)


def _policy(**overrides: object) -> SourcePolicy:
    values: dict[str, object] = {
        "field": "base_price",
        "source_url": URL,
        "acquisition_method": AcquisitionMethod.DIRECT_HTTP,
        "fetch": PolicyDecision.APPROVED,
        "reviewed_at": NOW - timedelta(days=1),
        "review_due_at": NOW + timedelta(days=30),
        "reviewed_by": "human-approver",
        "basis": "Synthetic approved fixture",
    }
    values.update(overrides)
    return SourcePolicy(**values)


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_fetches_approved_bounded_source_and_hashes_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == URL
        assert "Cookie" not in request.headers
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8", "ETag": '"v1"'},
            content=b"<html>synthetic</html>",
        )

    result = fetch_approved_source(
        _policy(),
        allowed_hosts=("vendor.example",),
        transport=_transport(handler),
        resolver=PUBLIC,
        clock=lambda: NOW,
    )

    assert result.status_code == 200
    assert result.etag == '"v1"'
    assert result.sha256 == "5be8790e8abd97a38ff67eefebc2bc3321a1d72d60d8139aa4c27a28284f2d03"
    assert result.body == b"<html>synthetic</html>"


def test_unapproved_expired_or_browser_policy_fails_before_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    with pytest.raises(SourcePermissionError):
        fetch_approved_source(
            _policy(fetch=PolicyDecision.UNREVIEWED),
            allowed_hosts=("vendor.example",),
            transport=_transport(handler),
            resolver=PUBLIC,
            clock=lambda: NOW,
        )
    with pytest.raises(SourcePermissionError):
        fetch_approved_source(
            _policy(review_due_at=NOW),
            allowed_hosts=("vendor.example",),
            transport=_transport(handler),
            resolver=PUBLIC,
            clock=lambda: NOW,
        )
    with pytest.raises(SourcePermissionError):
        fetch_approved_source(
            _policy(acquisition_method=AcquisitionMethod.BROWSER),
            allowed_hosts=("vendor.example",),
            transport=_transport(handler),
            resolver=PUBLIC,
            clock=lambda: NOW,
        )
    assert called is False


def test_private_ip_and_unlisted_redirect_are_blocked() -> None:
    with pytest.raises(UnsafeDestinationError, match="non-public"):
        fetch_approved_source(
            _policy(),
            allowed_hosts=("vendor.example",),
            transport=_transport(lambda request: httpx.Response(200)),
            resolver=lambda host, port: ("127.0.0.1",),
            clock=lambda: NOW,
        )

    with pytest.raises(UnsafeDestinationError, match="not allowlisted"):
        fetch_approved_source(
            _policy(),
            allowed_hosts=("vendor.example",),
            transport=_transport(
                lambda request: httpx.Response(
                    302, headers={"Location": "https://evil.example/steal"}
                )
            ),
            resolver=PUBLIC,
            clock=lambda: NOW,
        )

def test_retry_after_is_exposed_without_automatic_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "120"})

    with pytest.raises(RetryAfterError) as captured:
        fetch_approved_source(
            _policy(),
            allowed_hosts=("vendor.example",),
            transport=_transport(handler),
            resolver=PUBLIC,
            clock=lambda: NOW,
        )
    assert calls == 1
    assert captured.value.retry_after == "120"


def test_content_type_and_size_are_fail_closed() -> None:
    with pytest.raises(ResponseRejectedError, match="Content-Type"):
        fetch_approved_source(
            _policy(),
            allowed_hosts=("vendor.example",),
            transport=_transport(
                lambda request: httpx.Response(
                    200,
                    headers={"Content-Type": "application/octet-stream"},
                    content=b"x",
                )
            ),
            resolver=PUBLIC,
            clock=lambda: NOW,
        )

    with pytest.raises(ResponseRejectedError, match="byte limit"):
        fetch_approved_source(
            _policy(),
            allowed_hosts=("vendor.example",),
            transport=_transport(
                lambda request: httpx.Response(
                    200,
                    headers={"Content-Type": "text/plain"},
                    content=b"12345",
                )
            ),
            resolver=PUBLIC,
            clock=lambda: NOW,
            max_bytes=4,
        )


def test_etag_not_modified_has_no_synthetic_body_hash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == '"old"'
        return httpx.Response(304, headers={"ETag": '"old"'})

    result = fetch_approved_source(
        _policy(),
        allowed_hosts=("vendor.example",),
        transport=_transport(handler),
        resolver=PUBLIC,
        clock=lambda: NOW,
        etag='"old"',
    )
    assert result.not_modified is True
    assert result.body == b""
    assert result.sha256 is None
