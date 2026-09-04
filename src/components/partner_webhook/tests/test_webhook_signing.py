from src.components.partner_webhook.signing import TalkoWebhookSigner


class TestTalkoWebhookSigner:
    def test_sign_is_deterministic(self):
        sig1 = TalkoWebhookSigner.sign("secret", 1000, b'{"a":1}')
        sig2 = TalkoWebhookSigner.sign("secret", 1000, b'{"a":1}')
        assert sig1 == sig2

    def test_sign_changes_with_secret(self):
        sig1 = TalkoWebhookSigner.sign("secret1", 1000, b'{"a":1}')
        sig2 = TalkoWebhookSigner.sign("secret2", 1000, b'{"a":1}')
        assert sig1 != sig2

    def test_sign_changes_with_timestamp(self):
        sig1 = TalkoWebhookSigner.sign("secret", 1000, b'{"a":1}')
        sig2 = TalkoWebhookSigner.sign("secret", 2000, b'{"a":1}')
        assert sig1 != sig2

    def test_sign_changes_with_body(self):
        sig1 = TalkoWebhookSigner.sign("secret", 1000, b'{"a":1}')
        sig2 = TalkoWebhookSigner.sign("secret", 1000, b'{"a":2}')
        assert sig1 != sig2

    def test_sign_returns_hex_digest(self):
        sig = TalkoWebhookSigner.sign("secret", 1000, b"body")
        assert len(sig) == 64  # SHA-256 hex digest length
        int(sig, 16)  # raises if not valid hex
