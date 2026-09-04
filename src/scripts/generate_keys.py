from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
KEYS_DIR: Path = BASE_DIR / "keys"
KEYS_DIR.mkdir(parents=True, exist_ok=True)


def generate_keys() -> Tuple[str, str]:
    """Generate and save RSA private/public key pair.

    Returns:
        Tuple[str, str]: Paths to the generated private and public key files.
    """
    private_key: rsa.RSAPrivateKey = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Save private key
    private_path: Path = KEYS_DIR / "private_key.pem"
    with open(private_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Save public key
    public_key = private_key.public_key()
    public_path: Path = KEYS_DIR / "public_key.pem"
    with open(public_path, "wb") as f:
        f.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    return str(private_path), str(public_path)


# Script
# from src.scripts.generate_keys import generate_keys

# private, public = generate_keys()
# print("Keys created at:", private, public)
