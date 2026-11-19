"""Authentication service – handles registration and login using bcrypt."""

from flask import current_app

class AuthService:
    def __init__(self, user_repo, bcrypt):
        self.user_repo = user_repo
        self.bcrypt = bcrypt

    def register_user(self, username: str, password: str):
        # hash password and store user
        pw_hash = self.bcrypt.generate_password_hash(password).decode("utf-8")
        self.user_repo.create_user(username, pw_hash)

    def verify_login(self, username: str, password: str):
        user = self.user_repo.find_by_username(username)
        if not user:
            return None
        if self.bcrypt.check_password_hash(user["password_hash"], password):
            return user
        return None
