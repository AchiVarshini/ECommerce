import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt


JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-secret-change-before-deploy")
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt, expected = encoded.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()
        return hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def create_access_token(customer_id: int, role: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    return jwt.encode({"sub": str(customer_id), "role": role, "exp": expires}, JWT_SECRET, algorithm=JWT_ALGORITHM)