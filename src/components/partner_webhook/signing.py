import hashlib
import hmac


class TalkoWebhookSigner:
    """Stripe-style HMAC-SHA256 signing for outbound webhook deliveries.

    The timestamp is included in the signed string so a partner can reject
    stale/replayed deliveries (recommended: reject if abs(now - t) > 300s).
    """

    @staticmethod
    def sign(secret: str, timestamp: int, raw_body: bytes) -> str:
        signed_payload = "{}.{}".format(timestamp, raw_body.decode("utf-8")).encode(
            "utf-8"
        )
        return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
