from cryptography.fernet import Fernet

from src.components.partner_webhook.crypto import TalkoWebhookSecretCipher


class TestTalkoWebhookSecretCipher:
    def test_encrypt_decrypt_round_trip(self):
        cipher = TalkoWebhookSecretCipher(Fernet.generate_key().decode())
        raw_secret = "super-secret-value"

        encrypted = cipher.encrypt(raw_secret)
        assert encrypted != raw_secret

        decrypted = cipher.decrypt(encrypted)
        assert decrypted == raw_secret

    def test_different_master_keys_produce_incompatible_ciphertext(self):
        cipher_a = TalkoWebhookSecretCipher(Fernet.generate_key().decode())
        cipher_b = TalkoWebhookSecretCipher(Fernet.generate_key().decode())

        encrypted = cipher_a.encrypt("secret")
        try:
            cipher_b.decrypt(encrypted)
            assert False, "decrypting with the wrong key should raise"
        except Exception:
            pass
