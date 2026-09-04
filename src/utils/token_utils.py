import hashlib
import secrets
from typing import Tuple


class TalkoApiKeyGenerator:
    """Generates and hashes partner-facing API keys.

    Keys carry a static, greppable prefix so callers (and the auth
    middleware) can distinguish them from opaque console-issued keys
    without a DB lookup.
    """

    PREFIX = "tkp_live_"
    DISPLAY_SUFFIX_LENGTH = 8

    @staticmethod
    def generate() -> Tuple[str, str, str]:
        """Generate a new key. Returns (raw_key, key_prefix, key_hash).

        raw_key is returned to the caller exactly once and never stored.
        key_hash (SHA-256 hex digest) is what gets persisted for lookup.
        """
        raw_key = "{}{}".format(
            TalkoApiKeyGenerator.PREFIX, secrets.token_urlsafe(32)
        )
        key_prefix = raw_key[
            : len(TalkoApiKeyGenerator.PREFIX) + TalkoApiKeyGenerator.DISPLAY_SUFFIX_LENGTH
        ]
        return raw_key, key_prefix, TalkoApiKeyGenerator.hash_key(raw_key)

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def is_partner_key(api_key: str) -> bool:
        return api_key.startswith(TalkoApiKeyGenerator.PREFIX)
