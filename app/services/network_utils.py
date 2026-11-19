"""Small helpers for discovering local network info."""
import ipaddress
import platform
import re
import socket
import subprocess
from typing import Optional


def detect_default_gateway() -> Optional[str]:
    """Best-effort detection of the default gateway (your router)."""
    system = platform.system().lower()
    try:
        if system == "darwin":
            out = subprocess.run(["route", "-n", "get", "default"], capture_output=True,
                                 text=True, timeout=3).stdout
            m = re.search(r"gateway:\s*(\S+)", out)
        elif system == "linux":
            out = subprocess.run(["ip", "route", "show", "default"], capture_output=True,
                                 text=True, timeout=3).stdout
            m = re.search(r"default via (\S+)", out)
        elif system == "windows":
            out = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=3).stdout
            m = re.search(r"Default Gateway[ .]*:\s*([\d.]+)", out)
        else:
            return None
        return m.group(1) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def detect_local_subnet() -> Optional[str]:
    """Best-effort guess of the subnet this machine is on, e.g. "192.168.1.0/24".

    Finds the local IPv4 address the OS would use to reach the internet (a UDP
    "connect" sends no packets) and assumes a /24, which is what almost every
    home and small-office network uses. Returns None if it is not a private
    address, so the UI falls back to an example instead of suggesting a scan
    of something that is not a LAN.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))          # TEST-NET address, never actually contacted
            local_ip = s.getsockname()[0]
        net = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except (OSError, ValueError):
        return None
    from .validators import is_scannable_network
    return str(net) if is_scannable_network(net) else None


def local_ipv4_addresses() -> set:
    """IPv4 addresses of this machine (best effort), so a scan can label "this computer"."""
    found = set()
    try:
        found.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            found.add(s.getsockname()[0])
    except OSError:
        pass
    return found


_ARP_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_ARP_MAC_RE = re.compile(r"\b([0-9A-Fa-f]{1,2}(?:[:-][0-9A-Fa-f]{1,2}){5})\b")
_NO_MAC = {"ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"}


def parse_arp_output(text: str) -> dict:
    """Parse `ip neigh` / `arp -an` / `arp -a` output into {ip: "aa:bb:cc:dd:ee:ff"}.

    One tolerant parser for all three formats: per line, take the first IPv4
    address and the first MAC address. macOS prints MACs without leading
    zeros ("0:1a:2b:...") and Windows uses dashes; both are normalised.
    """
    table = {}
    for line in text.splitlines():
        ip_m, mac_m = _ARP_IP_RE.search(line), _ARP_MAC_RE.search(line)
        if not ip_m or not mac_m:
            continue
        try:
            ip = str(ipaddress.IPv4Address(ip_m.group(1)))
        except ValueError:
            continue
        mac = ":".join(part.zfill(2) for part in re.split(r"[:-]", mac_m.group(1))).lower()
        if mac not in _NO_MAC:
            table[ip] = mac
    return table


def read_arp_table() -> dict:
    """The OS neighbour (ARP) table: {ip: mac}. Empty if it cannot be read.

    After a ping sweep this holds the MAC address of every device that answered
    on the local network segment.
    """
    system = platform.system().lower()
    if system == "windows":
        commands = [["arp", "-a"]]
    elif system == "darwin":
        commands = [["arp", "-an"]]
    else:
        commands = [["ip", "neigh"], ["arp", "-an"]]
    for cmd in commands:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        table = parse_arp_output(out)
        if table:
            return table
    return {}
