"""Refuse public endpoints for control sessions; no scanning or cloud discovery."""
import ipaddress
import socket

LOCAL_BLOCKS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10"))


def direct_ssh_ready(profile, timeout=1):
    if profile.topology != "direct":
        return False
    try:
        with socket.create_connection((profile.mac_ip, profile.ssh_port), timeout=timeout,
                                      source_address=(profile.windows_ip, 0)) as connection:
            with connection.makefile("rb") as stream:
                return stream.readline(256).startswith(b"SSH-")
    except OSError:
        return False


def local_ipv4(address):
    try:
        ip = ipaddress.IPv4Address(address)
        return any(ip in block for block in LOCAL_BLOCKS)
    except ipaddress.AddressValueError:
        return False


def resolve_local(host):
    try:
        ipaddress.IPv4Address(host)
        results = [host]
    except ipaddress.AddressValueError:
        results = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)))
    if not results or any(not local_ipv4(address) for address in results):
        raise ValueError("LOCAL_ENDPOINT_REQUIRED: public or unsupported addresses are refused")
    return results[0]
