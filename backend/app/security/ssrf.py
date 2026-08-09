"""SSRF protection for outbound research requests (§42).

The research engine fetches external URLs, so every URL is validated before
fetching: only http(s), no private/loopback/link-local/reserved addresses,
no credentials-in-URL, and DNS resolution is checked against the same rules.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFError(ValueError):
    pass


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url(url: str, *, resolve_dns: bool = True) -> str:
    """Validate a URL for safe server-side fetching. Returns the cleaned URL."""
    if not url or len(url) > 2048:
        raise SSRFError("Invalid URL")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"Disallowed URL scheme: {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise SSRFError("Credentials in URL are not allowed")
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no host")
    if host.lower() in ("localhost", "localhost.localdomain"):
        raise SSRFError("Loopback host is not allowed")

    # Literal IP in the URL
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # hostname, resolved below
    else:
        if not _is_public_ip(host):
            raise SSRFError("Non-public IP addresses are not allowed")
        return url

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise SSRFError(f"Host cannot be resolved: {host}") from exc
        for info in infos:
            addr = info[4][0]
            if not _is_public_ip(addr):
                raise SSRFError("Host resolves to a non-public address")
    return url
