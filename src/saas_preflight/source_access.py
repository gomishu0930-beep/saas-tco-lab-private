"""Permission-gated HTTP access for explicitly approved public sources.

This module performs no crawling or discovery.  One approved SourcePolicy maps
to one initial URL, every redirect host must be allowlisted, and all resolved
addresses must be public.  Response bytes are transient and size-bounded; this
module never archives them.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx

from .models import AcquisitionMethod, PolicyAction, SourcePolicy


class SourceAccessError(RuntimeError):
    """Base error for denied or unsafe source access."""


class SourcePermissionError(SourceAccessError):
    """The source policy does not currently authorize direct retrieval."""


class UnsafeDestinationError(SourceAccessError):
    """The destination is not an explicitly approved public HTTPS endpoint."""


class ResponseRejectedError(SourceAccessError):
    """The remote response is outside the accepted status/type/size boundary."""


class RetryAfterError(ResponseRejectedError):
    """The server asked the caller to wait; this adapter never bypasses it."""

    def __init__(self, *, status_code: int, retry_after: str | None) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(
            f"source returned {status_code}; honor Retry-After before another attempt"
        )


@dataclass(frozen=True, slots=True)
class FetchResult:
    final_url: str
    retrieved_at: datetime
    status_code: int
    content_type: str | None
    etag: str | None
    sha256: str | None
    body: bytes
    not_modified: bool


Resolver = Callable[[str, int], Iterable[str]]
Clock = Callable[[], datetime]


def fetch_approved_source(
    policy: SourcePolicy,
    *,
    allowed_hosts: Iterable[str],
    transport: httpx.BaseTransport | None = None,
    resolver: Resolver | None = None,
    clock: Clock | None = None,
    etag: str | None = None,
    max_bytes: int = 1_000_000,
    max_redirects: int = 3,
) -> FetchResult:
    """Retrieve one approved URL without discovery, retries, or persistence."""

    now = (clock or _utc_now)()
    _require_aware(now)
    if not policy.permits(PolicyAction.FETCH, at=now):
        raise SourcePermissionError("source fetch is not currently approved")
    if policy.acquisition_method not in {
        AcquisitionMethod.OFFICIAL_API,
        AcquisitionMethod.VENDOR_FEED,
        AcquisitionMethod.DIRECT_HTTP,
    }:
        raise SourcePermissionError(
            "policy acquisition method is not supported by the HTTP adapter"
        )
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    if (
        isinstance(max_redirects, bool)
        or not isinstance(max_redirects, int)
        or max_redirects < 0
        or max_redirects > 10
    ):
        raise ValueError("max_redirects must be an integer between 0 and 10")

    hosts = frozenset(_normalize_host(host) for host in allowed_hosts)
    if not hosts:
        raise UnsafeDestinationError("at least one explicit host is required")
    initial_url = str(policy.source_url)
    resolve = resolver or _resolve_addresses
    _validate_destination(initial_url, allowed_hosts=hosts, resolver=resolve)

    active_client = httpx.Client(
        transport=transport,
        follow_redirects=False,
        timeout=httpx.Timeout(10.0, connect=5.0),
        trust_env=False,
        headers={
            "Accept": "application/json,text/html,text/plain;q=0.8",
            "User-Agent": "saas-preflight/0.1 (+permission-gated-research)",
        },
    )
    try:
        return _request_chain(
            active_client,
            initial_url=initial_url,
            allowed_hosts=hosts,
            resolver=resolve,
            retrieved_at=now,
            etag=etag,
            max_bytes=max_bytes,
            max_redirects=max_redirects,
        )
    finally:
        active_client.close()


def _request_chain(
    client: httpx.Client,
    *,
    initial_url: str,
    allowed_hosts: frozenset[str],
    resolver: Resolver,
    retrieved_at: datetime,
    etag: str | None,
    max_bytes: int,
    max_redirects: int,
) -> FetchResult:
    url = initial_url
    headers = {"If-None-Match": etag} if etag is not None else {}
    for redirect_count in range(max_redirects + 1):
        _validate_destination(url, allowed_hosts=allowed_hosts, resolver=resolver)
        with client.stream(
            "GET", url, headers=headers, follow_redirects=False
        ) as response:
            if response.status_code in {429, 503}:
                raise RetryAfterError(
                    status_code=response.status_code,
                    retry_after=response.headers.get("Retry-After"),
                )
            if response.status_code in {301, 302, 303, 307, 308}:
                if redirect_count >= max_redirects:
                    raise ResponseRejectedError("redirect limit exceeded")
                location = response.headers.get("Location")
                if not location:
                    raise ResponseRejectedError("redirect is missing Location")
                url = urljoin(url, location)
                headers = {}
                continue
            if response.status_code == 304:
                return FetchResult(
                    final_url=url,
                    retrieved_at=retrieved_at,
                    status_code=304,
                    content_type=response.headers.get("Content-Type"),
                    etag=response.headers.get("ETag") or etag,
                    sha256=None,
                    body=b"",
                    not_modified=True,
                )
            if response.status_code != 200:
                raise ResponseRejectedError(
                    f"source returned unsupported status {response.status_code}"
                )

            content_type = response.headers.get("Content-Type")
            if not _accepted_content_type(content_type):
                raise ResponseRejectedError("response Content-Type is not accepted")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise ResponseRejectedError("invalid Content-Length") from exc
                if declared_length < 0 or declared_length > max_bytes:
                    raise ResponseRejectedError("response exceeds the byte limit")

            chunks: list[bytes] = []
            size = 0
            digest = hashlib.sha256()
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise ResponseRejectedError("response exceeds the byte limit")
                digest.update(chunk)
                chunks.append(chunk)
            body = b"".join(chunks)
            return FetchResult(
                final_url=url,
                retrieved_at=retrieved_at,
                status_code=200,
                content_type=content_type,
                etag=response.headers.get("ETag"),
                sha256=digest.hexdigest(),
                body=body,
                not_modified=False,
            )
    raise AssertionError("unreachable request chain")


def _validate_destination(
    url: str, *, allowed_hosts: frozenset[str], resolver: Resolver
) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UnsafeDestinationError("source URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeDestinationError("source URL must not contain user information")
    if parsed.fragment:
        raise UnsafeDestinationError("source URL must not contain a fragment")
    if parsed.port not in {None, 443}:
        raise UnsafeDestinationError("source URL must use the default HTTPS port")
    host = _normalize_host(parsed.hostname or "")
    if host not in allowed_hosts:
        raise UnsafeDestinationError("destination host is not allowlisted")
    addresses = tuple(resolver(host, 443))
    if not addresses:
        raise UnsafeDestinationError("destination host did not resolve")
    for address in addresses:
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeDestinationError("resolver returned an invalid IP address") from exc
        if not parsed_address.is_global:
            raise UnsafeDestinationError("destination resolved to a non-public address")


def _normalize_host(host: str) -> str:
    if not isinstance(host, str) or not host.strip():
        raise UnsafeDestinationError("host must be a non-empty string")
    normalized = host.strip().rstrip(".").lower()
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeDestinationError("host cannot be normalized") from exc


def _resolve_addresses(host: str, port: int) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeDestinationError("destination DNS resolution failed") from exc
    return tuple(sorted({record[4][0] for record in records}))


def _accepted_content_type(value: str | None) -> bool:
    if value is None:
        return False
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type in {
        "application/json",
        "application/ld+json",
        "text/html",
        "text/plain",
    }


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware timestamp")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "FetchResult",
    "ResponseRejectedError",
    "RetryAfterError",
    "SourceAccessError",
    "SourcePermissionError",
    "UnsafeDestinationError",
    "fetch_approved_source",
]
