"""User repository – thin wrapper around the SQLite DB for user accounts."""

from ..database import Database


class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_user(self, username: str, password_hash: str):
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )

    def find_by_username(self, username: str):
        with self.db.connection() as conn:
            cur = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,),
            )
            return cur.fetchone()
