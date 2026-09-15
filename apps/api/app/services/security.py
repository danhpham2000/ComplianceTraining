import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings


settings = get_settings()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def require_allowed_email(email: str) -> str:
    return normalize_email(email)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, expected = stored_hash.split("$", 1)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return hmac.compare_digest(actual, expected)


def new_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def verification_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.verification_code_minutes)


def session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.session_duration_days)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)
