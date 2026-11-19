"""User model for authentication."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    created_at: str = datetime.utcnow().isoformat() + 'Z'
