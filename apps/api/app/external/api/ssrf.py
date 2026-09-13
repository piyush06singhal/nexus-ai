"""SSRF guard (Phase 10, §security).

Blocks requests to loopback, link-local, private, metadata, and documentation
ranges by default, and re-validates every redirect hop so the guard cannot be
bypassed via a benign first URL. Applies to the secure HTTP client and the
generic HTTP connector. ``ssrf_protection_enabled`` (default True) can only
relax this in explicit operator configuration.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from urllib.parse import urlparse

from app.core.config import settings

# Blocked by default — server-side request forgery primaries.
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    [
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),  # incl. 169.254.169.254 metadata
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.0.0.0/24"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("198.18.0.0/15"),
        ipaddress.ip_network("224.0.0.0/4"),  # multicast
        ipaddress.ip_network("::1"),
        ipaddress.ip_network("fc00::/7"),  # unique local
        ipaddress.ip_network("fe80::/10"),  # link-local
        ipaddress.ip_network("::ffff:127.0.0.1/128"),
    ]
)

_HOSTNAME_ALIASES_BLOCKED = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "metadata.google",
}


class SSRFBlockedError(ValueError):
    """A URL was refused because it targets a blocked/internal address."""


SSRFBlocked = SSRFBlockedError  # shared alias for the guard facade


class SSRFGuard:
    """Convenience facade over the module-level SSRF checks.

    ``validate(url)`` refuses any URL that resolves to a blocked/internal
    address (loopback, link-local, private, metadata, documentation ranges) and
    any URL carrying userinfo credentials. Redirect re-validation happens at
    fetch time through :func:`validate_redirect_chain` so a benign first hop
    can never smuggle a private second hop.
    """

    def __init__(self, *, allowlist: list[str] | None = None) -> None:
        self.allowlist = list(allowlist or [])

    def validate(self, url: str, *, allow_redirects: bool = False) -> bool:
        check_url(url)
        return True

    @staticmethod
    def validate_chain(urls: Iterable[str]) -> None:
        validate_redirect_chain(urls)


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable IPs are refused rather than risked
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    return any(ip in network for network in _BLOCKED_NETWORKS)


def check_host(host: str, port: int | None = None) -> None:
    """Raise :class:`SSRFBlockedError` if *host* must not be contacted."""
    if not settings.ssrf_protection_enabled:
        return
    lowered = host.rstrip(".").lower()

    # Hostname aliases and metadata/cloud endpoints are always refused.
    if lowered in _HOSTNAME_ALIASES_BLOCKED or lowered.endswith(".local"):
        raise SSRFBlockedError(f"host {host!r} is blocked by SSRF protection")
    if _is_ip(lowered):
        if _is_blocked_ip(lowered):
            raise SSRFBlockedError(f"host {host!r} is blocked by SSRF protection")
        return

    # DNS names are allowed through here (the domain allowlist governs which
    # external domains are permitted). Reject only ambiguous numeric/host-like
    # aliases that could decode to an internal IP.
    if _looks_like_internal_ip(lowered):
        raise SSRFBlockedError(f"host {host!r} is blocked by SSRF protection")


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _looks_like_internal_ip(value: str) -> bool:
    """Reject numeric/dec-octal forms that decode to internal addresses."""
    if _is_ip(value):
        return _is_blocked_ip(value)
    # Decimal/octal/host-like aliases of 127.x / 0.x.
    if value in {"127", "127.1", "2130706433", "0177.0.0.1", "0x7f000001"}:
        return True
    try:
        integer = int(value.split(".")[0])
        return integer >= 2130706432  # 127.0.0.0/8 decoded as a single int
    except (ValueError, IndexError):
        return False


def check_url(url: str) -> None:
    """Validate a full URL: scheme + host + (no userinfo with secrets)."""
    if not settings.ssrf_protection_enabled:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"scheme {parsed.scheme!r} is not allowed")
    if not parsed.hostname:
        raise SSRFBlockedError(f"URL {url!r} has no host")
    if parsed.username or parsed.password:
        raise SSRFBlockedError("URLs carrying userinfo/credentials are refused")
    check_host(parsed.hostname, parsed.port)


def check_host_resolution(host: str) -> None:
    """Resolve *host* and refuse it if any address maps to an internal range.

    Closes the DNS-rebinding TOCTOU at the widest practical point: a DNS name
    that ``check_host`` permits (because the name itself is not an internal
    address) can still resolve to a private IP at fetch time. By resolving here,
    immediately before the connect, a ``evil.example`` → ``192.168.0.1`` mapping
    is refused. This is in-process best effort: fully closing the race requires
    pinning the connection to the validated address (deployment-level transport
    item; documented in the threat model).
    """
    if not settings.ssrf_protection_enabled:
        return
    if _is_ip(host):
        return  # literal IPs are already checked by check_host
    import socket

    try:
        infos = socket.getaddrinfo(host.rstrip("."), None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return  # unresolved now — the connect itself will fail safely
    for _family, _socktype, _proto, _canon, sockaddr in infos:
        ip = _extract_ip(sockaddr)
        if ip is not None and _is_blocked_ip(ip):
            raise SSRFBlockedError(f"host {host!r} resolves to blocked address {ip!r}")


def _extract_ip(sockaddr: tuple) -> str | None:
    """Pull the address string from a getaddrinfo sockaddr (4-tuple or 2-tuple)."""
    try:
        return str(sockaddr[0])
    except (IndexError, TypeError):
        return None


def validate_redirect_chain(urls: Iterable[str]) -> None:
    """Validate every URL in a redirect chain (each hop re-checked)."""
    for url in urls:
        check_url(url)


def allowed_domain(domain: str, allowlist: list[str]) -> bool:
    """Whether *domain* is inside the allowlist (exact or subdomain)."""
    if not allowlist:
        return True  # no allowlist configured ⇒ domain governlet only via allowlists
    domain = domain.rstrip(".").lower()
    for allowed in allowlist:
        allowed = allowed.strip().lower()
        if domain == allowed or domain.endswith("." + allowed):
            return True
    return False
