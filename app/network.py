import os
import socket
import subprocess
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("pedantix.network")

def get_all_lan_ips() -> List[str]:
    """Returns all non-loopback IPv4 addresses detected on the system."""
    ips = set()

    # 1. UDP probe to popular DNS addresses
    for target in [("8.8.8.8", 80), ("1.1.1.1", 80), ("9.9.9.9", 80)]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(target)
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    ips.add(ip)
        except Exception:
            pass

    # 2. Hostname resolution
    try:
        _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in host_ips:
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    # 3. ip command on Linux
    try:
        out = subprocess.check_output(["ip", "-4", "-o", "addr", "show"], text=True, timeout=1.0)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == "inet":
                ip = parts[3].split("/")[0]
                if not ip.startswith("127."):
                    ips.add(ip)
    except Exception:
        pass

    return list(ips)


def get_primary_lan_ip() -> str:
    """Returns the primary LAN IP reachable by other devices on the same Wi-Fi/Ethernet network."""
    env_ip = os.environ.get("PEDANTIX_LAN_IP")
    if env_ip and not env_ip.startswith("127."):
        return env_ip

    # 1. Probe default gateway / internet route
    for target in [("8.8.8.8", 80), ("1.1.1.1", 80), ("9.9.9.9", 80)]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(target)
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass

    # 2. Query routing table for default route
    try:
        out = subprocess.check_output(["ip", "route", "get", "1.1.1.1"], text=True, timeout=1.0)
        # Format: 1.1.1.1 via 10.19.94.35 dev wlp0s20f3 src 10.19.94.235 ...
        for part in out.split():
            if part.count(".") == 3 and not part.startswith("127."):
                idx = out.split().index(part)
                if idx > 0 and out.split()[idx - 1] == "src":
                    return part
    except Exception:
        pass

    # 3. Hostname resolution
    try:
        _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in host_ips:
            if not ip.startswith("127."):
                return ip
    except Exception:
        pass

    # 4. Check all active non-loopback interfaces, prioritizing wifi/ethernet
    all_ips = get_all_lan_ips()
    if all_ips:
        # Prefer private LAN IP ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
        for ip in all_ips:
            if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                return ip
        return all_ips[0]

    return "127.0.0.1"
