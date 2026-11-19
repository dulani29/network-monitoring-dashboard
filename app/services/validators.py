"""Input validation. Hosts are validated strictly because they are passed to
the system `ping` command (we never use a shell, but we also reject anything
that could be mistaken for a command-line option)."""
import ipaddress
import re

from ..models import DEVICE_TYPES

# Network scanning is limited to private (RFC 1918) address space and to small
# subnets. This keeps the scanner a "find the devices on MY LAN" tool: it will
# not sweep public IP ranges, whatever is typed in.
SCANNABLE_RANGES = tuple(ipaddress.ip_network(n) for n in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
MIN_SCAN_PREFIX = 22          # /22 = at most 1022 hosts
MAX_SCAN_PREFIX = 30          # /30 = 2 hosts

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


class ValidationError(ValueError):
    def __init__(self, errors: dict):
        super().__init__("Validation failed")
        self.errors = errors


def is_valid_host(host: str) -> bool:
    if not host or host.startswith("-"):
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(_HOSTNAME_RE.match(host))


def validate_device_payload(data: dict) -> dict:
    errors = {}
    name = str(data.get("name", "")).strip()
    host = str(data.get("host", "")).strip()
    device_type = str(data.get("device_type", "other")).strip().lower() or "other"
    enabled = bool(data.get("enabled", True))

    if not name:
        errors["name"] = "Name is required."
    elif len(name) > 60:
        errors["name"] = "Name must be 60 characters or fewer."

    if not host:
        errors["host"] = "IP address or hostname is required."
    elif not is_valid_host(host):
        errors["host"] = "Enter a valid IPv4/IPv6 address or hostname."

    if device_type not in DEVICE_TYPES:
        errors["device_type"] = f"Device type must be one of: {', '.join(DEVICE_TYPES)}."

    if errors:
        raise ValidationError(errors)
    return {"name": name, "host": host, "device_type": device_type, "enabled": enabled}


def is_scannable_network(net) -> bool:
    return (isinstance(net, ipaddress.IPv4Network)
            and MIN_SCAN_PREFIX <= net.prefixlen <= MAX_SCAN_PREFIX
            and any(net.subnet_of(r) for r in SCANNABLE_RANGES))


def validate_scan_payload(data: dict) -> ipaddress.IPv4Network:
    """Validate a scan request and return the network to scan.

    Requires the caller to confirm they are authorised to test the network.
    Accepts "192.168.1.0/24" and also a host address like "192.168.1.5/24".
    """
    errors = {}
    raw = str(data.get("subnet", "")).strip()
    net = None

    if not raw:
        errors["subnet"] = "Enter a subnet in CIDR form, e.g. 192.168.1.0/24."
    elif "/" not in raw:
        errors["subnet"] = "Include the prefix length, e.g. 192.168.1.0/24."
    else:
        try:
            net = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            errors["subnet"] = "That is not a valid subnet. Example: 192.168.1.0/24."
        else:
            if not isinstance(net, ipaddress.IPv4Network):
                errors["subnet"] = "Only IPv4 subnets can be scanned."
            elif not is_scannable_network(net):
                errors["subnet"] = (
                    f"Only private networks (10.x, 172.16-31.x, 192.168.x) from /{MIN_SCAN_PREFIX} "
                    f"to /{MAX_SCAN_PREFIX} can be scanned.")

    if data.get("authorized") is not True:
        errors["authorized"] = "Confirm that you own this network or are authorised to test it."

    if errors:
        raise ValidationError(errors)
    return net
