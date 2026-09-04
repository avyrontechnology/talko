from cryptography.fernet import Fernet


class TalkoWebhookSecretCipher:
    """Encrypts/decrypts partner webhook signing secrets at rest.

    Unlike partner API keys (hashed — never need to be read back), a
    webhook secret must be readable in plaintext on every delivery to
    compute the outgoing HMAC signature, so it's encrypted, not hashed.
    """

    def __init__(self, master_key: str):
        self.__fernet = Fernet(master_key.encode("utf-8"))

    def encrypt(self, raw_secret: str) -> str:
        return self.__fernet.encrypt(raw_secret.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_secret: str) -> str:
        return self.__fernet.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
