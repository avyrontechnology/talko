import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

# PBKDF2-SHA256 via stdlib only (no native wheels to build on Render).
_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 600_000
_JWT_ALGO = "HS256"


def hash_password(raw_password: str) -> str:
    """Hash a password with a random salt. Returns a PHC-style string."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO, raw_password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return "pbkdf2-sha256${}${}${}".format(
        _PBKDF2_ITERATIONS, salt.hex(), digest.hex()
    )


def verify_password(raw_password: str, password_hash: str) -> bool:
    """Constant-time password check. Any malformed hash verifies False."""
    try:
        name, iterations, salt_hex, digest_hex = password_hash.split("$")
        if name != "pbkdf2-sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            _PBKDF2_ALGO,
            raw_password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def mint_talko_token(
    *,
    secret: str,
    user_id: str,
    email: str,
    role: str,
    partner_id: Optional[int],
    ttl_hours: int = 72,
) -> str:
    """Mint a Talko-native JWT (distinguished from console JWTs by issuer)."""
    now = datetime.now(timezone.utc)
    claims: Dict[str, Any] = {
        "iss": "talko",
        "sub": str(user_id),
        "email": email,
        "role": role,
        "is_superadmin": role == "superadmin",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
    }
    if partner_id is not None:
        claims["partner_id"] = int(partner_id)
    return jwt.encode(claims, secret, algorithm=_JWT_ALGO)


def verify_talko_token(secret: str, token: str) -> Optional[Dict[str, Any]]:
    """Verify a Talko-native JWT. Returns claims, or None (never raises)."""
    try:
        claims = jwt.decode(
            token, secret, algorithms=[_JWT_ALGO], issuer="talko",
            options={"require": ["exp", "iss", "sub"]},
        )
        return dict(claims)
    except Exception:
        return None
