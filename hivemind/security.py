import hashlib
import hmac
import secrets


def token() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify(value: str, expected_digest: str) -> bool:
    return hmac.compare_digest(digest(value), expected_digest)
