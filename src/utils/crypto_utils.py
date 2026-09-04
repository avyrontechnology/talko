import base64
import binascii
import json
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.core.environment import TalkoENV


class TalkoRSAKeyHandler:
    @staticmethod
    def load_private_key() -> rsa.RSAPrivateKey:
        """Load base64-encoded private key from environment string."""
        private_key_b64: Optional[str] = TalkoENV.RSA_PRIVATE_KEY
        if not private_key_b64 or private_key_b64.strip() == "":
            raise ValueError("RSA_PRIVATE_KEY not found or empty in environment")

        try:
            private_key_bytes: bytes = base64.b64decode(private_key_b64)
            return serialization.load_pem_private_key(
                private_key_bytes,
                password=None,
            )
        except Exception as e:
            raise ValueError("Failed to load private key: {}".format(str(e)))

    @staticmethod
    def load_public_key() -> rsa.RSAPublicKey:
        """Load base64-encoded public key from environment string."""
        public_key_b64: Optional[str] = TalkoENV.RSA_PUBLIC_KEY
        if not public_key_b64 or public_key_b64.strip() == "":
            raise ValueError("RSA_PUBLIC_KEY not found or empty in environment")

        try:
            public_key_bytes: bytes = base64.b64decode(public_key_b64)
            return serialization.load_pem_public_key(public_key_bytes)
        except Exception as e:
            raise ValueError("Failed to load public key: {}".format(str(e)))

    @staticmethod
    def encrypt_with_public_key(
        data: Dict[str, Any], public_key: rsa.RSAPublicKey
    ) -> str:
        """Encrypt dict using public key. Returns hex string for consistency."""
        json_data: str = json.dumps(data)
        data_bytes: bytes = json_data.encode("utf-8")
        try:
            ciphertext: bytes = public_key.encrypt(
                data_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            # Return hex-encoded string to match previous storage
            return binascii.hexlify(ciphertext).decode("utf-8")
        except Exception as e:
            raise ValueError("Encryption failed: {}".format(str(e)))

    @staticmethod
    def _is_valid_hex(s: str) -> bool:
        """Check if a string is valid hex."""
        try:
            if len(s) % 2 != 0:  # Hex string must have even length
                return False
            binascii.unhexlify(s)
            return True
        except Exception:
            return False

    @staticmethod
    def _is_base64(s: str) -> bool:
        """Check if a string is valid base64."""
        try:
            decoded = base64.b64decode(s, validate=True)
            # Re-encode to verify
            return base64.b64encode(decoded).decode() == s
        except Exception:
            return False

    @staticmethod
    def decrypt_with_private_key(
        ciphertext_str: str, private_key: Optional[rsa.RSAPrivateKey] = None
    ) -> Dict[str, Any]:
        """
        Decrypt ciphertext using private key.
        Supports both base64 and hex encoded input, prioritizing hex for 512-character strings.
        """
        if not private_key:
            private_key = TalkoRSAKeyHandler.load_private_key()

        try:
            expected_length = 256

            if len(ciphertext_str) == 512 and TalkoRSAKeyHandler._is_valid_hex(ciphertext_str):
                try:
                    ciphertext = binascii.unhexlify(ciphertext_str)
                    if len(ciphertext) != expected_length:
                        raise ValueError(
                            "Invalid ciphertext length: {} bytes, expected {} bytes".format(
                                len(ciphertext), expected_length
                            )
                        )
                except Exception as e:
                    raise ValueError("Hex decoding failed: {}".format(str(e)))
            else:
                try:
                    ciphertext = base64.b64decode(ciphertext_str, validate=True)
                    if len(ciphertext) != expected_length:
                        raise ValueError(
                            "Invalid ciphertext length: {} bytes, expected {} bytes".format(
                                len(ciphertext), expected_length
                            )
                        )
                except Exception as e:
                    raise ValueError(
                        "Invalid ciphertext encoding: must be base64 or valid hex. Error: {}".format(
                            str(e)
                        )
                    )

            plaintext_bytes = private_key.decrypt(
                ciphertext,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            return json.loads(plaintext_bytes.decode("utf-8"))
        except Exception as e:
            raise ValueError("Decryption failed: {}".format(str(e)))
