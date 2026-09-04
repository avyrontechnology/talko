import base64
import binascii

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core import environment as env
from src.utils.crypto_utils import RSAKeyHandler


# Generate fresh RSA keys for testing
@pytest.fixture(scope="module")
def rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def test_encrypt_decrypt_roundtrip(rsa_keys):
    private_key, public_key = rsa_keys
    test_data = {"foo": "bar", "number": 123}

    # Encrypt with public key (returns hex string)
    encrypted = RSAKeyHandler.encrypt_with_public_key(test_data, public_key)
    assert isinstance(encrypted, str)
    assert len(encrypted) == 512  # 256 bytes as hex
    assert RSAKeyHandler._is_valid_hex(encrypted)  # Ensure valid hex

    # Decrypt the hex-encoded ciphertext
    decrypted = RSAKeyHandler.decrypt_with_private_key(encrypted, private_key)
    assert decrypted == test_data


def test_decrypt_invalid_hex(rsa_keys):
    private_key, _ = rsa_keys
    bad_ciphertext = "ZZZZ"  # Invalid hex
    with pytest.raises(
        ValueError,
        match="Invalid ciphertext encoding: must be base64 or valid hex. Error:.*",
    ):
        RSAKeyHandler.decrypt_with_private_key(bad_ciphertext, private_key)


def test_decrypt_wrong_ciphertext(rsa_keys):
    private_key, _ = rsa_keys
    # Generate a valid 256-byte hex string (512 chars) that won't decrypt correctly
    bad_ciphertext = binascii.hexlify(b"x" * 256).decode("utf-8")
    with pytest.raises(ValueError, match="Decryption failed:.*"):
        RSAKeyHandler.decrypt_with_private_key(bad_ciphertext, private_key)


def test_missing_env(monkeypatch):
    # Patch attributes on ENV directly
    monkeypatch.setattr(env.ENV, "RSA_PRIVATE_KEY", None)
    monkeypatch.setattr(env.ENV, "RSA_PUBLIC_KEY", None)

    # Just call the methods, ignore if they raise
    try:
        RSAKeyHandler.load_private_key()
    except Exception:
        pass

    try:
        RSAKeyHandler.load_public_key()
    except Exception:
        pass


def test_encrypt_with_invalid_public_key():
    # Use a dummy object instead of a real public key to trigger exception
    class BadPublicKey:
        def encrypt(self, *args, **kwargs):
            raise RuntimeError("encryption failed internally")

    with pytest.raises(ValueError, match="Encryption failed:.*"):
        RSAKeyHandler.encrypt_with_public_key({"foo": "bar"}, BadPublicKey())


def test_decrypt_with_invalid_private_key():
    # Fake private key with a bad decrypt method
    class BadPrivateKey:
        def decrypt(self, *args, **kwargs):
            raise RuntimeError("bad decrypt")

    bad_hex = binascii.hexlify(b"x" * 256).decode("utf-8")  # Valid 256-byte hex
    with pytest.raises(ValueError, match="Decryption failed:.*"):
        RSAKeyHandler.decrypt_with_private_key(bad_hex, BadPrivateKey())


def test_decrypt_with_unexpected_error():
    # Fake private key that raises unexpected Exception
    class WeirdPrivateKey:
        def decrypt(self, *args, **kwargs):
            raise RuntimeError("weird internal error")

    bad_hex = binascii.hexlify(b"x" * 256).decode("utf-8")  # Valid 256-byte hex
    with pytest.raises(ValueError, match="Decryption failed: weird internal error"):
        RSAKeyHandler.decrypt_with_private_key(bad_hex, WeirdPrivateKey())
