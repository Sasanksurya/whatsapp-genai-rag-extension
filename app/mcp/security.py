"""
Basic SSRF guard for the website-fetch MCP tool.

A user-supplied URL is untrusted input. Without this check, someone
could point the fetcher at http://169.254.169.254/ (cloud metadata
endpoint), http://localhost:..., or an internal-network address and
use this server as an open proxy into infrastructure it shouldn't
reach. This is a minimum bar, not a complete solution — Phase 5
(security hardening) should add DNS-rebinding protection (re-resolve
and re-check the IP the request actually connects to, not just the
hostname at validation time).
"""
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(Exception):
    pass


BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def assert_safe_url(url: str) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: '{parsed.scheme}'. Only http/https allowed.")

    if not parsed.hostname:
        raise UnsafeURLError("URL has no hostname.")

    hostname = parsed.hostname.lower()
    if hostname in BLOCKED_HOSTNAMES:
        raise UnsafeURLError(f"Fetching '{hostname}' is not allowed.")

    try:
        resolved_ips = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as e:
        raise UnsafeURLError(f"Could not resolve host '{hostname}': {e}")

    for ip_str in resolved_ips:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise UnsafeURLError(
                f"'{hostname}' resolves to a non-public address ({ip_str}) — blocked."
            )
