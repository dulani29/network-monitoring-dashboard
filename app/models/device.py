from dataclasses import dataclass, asdict

DEVICE_TYPES = ("router", "switch", "server", "laptop", "desktop",
                "printer", "phone", "dns", "iot", "other")


@dataclass
class Device:
    id: int
    name: str
    host: str
    device_type: str = "other"
    enabled: bool = True
    created_at: str = ""

    @classmethod
    def from_row(cls, row) -> "Device":
        return cls(
            id=row["id"],
            name=row["name"],
            host=row["host"],
            device_type=row["device_type"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return asdict(self)
