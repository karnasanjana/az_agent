"""Fernet symmetric encryption for credential protection.

SEC-01: All credentials encrypted in transit using Fernet.
Fernet provides authenticated encryption (AES-128-CBC + HMAC).
"""
from functools import lru_cache
from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptor:
    """Encrypt and decrypt credentials using Fernet symmetric encryption.

    Usage:
        encryptor = CredentialEncryptor(key)
        encrypted = encryptor.encrypt("my-password")
        decrypted = encryptor.decrypt(encrypted)
    """

    def __init__(self, key: str | bytes):
        """Initialize with Fernet key.

        Args:
            key: URL-safe base64-encoded 32-byte key.
                 Generate with: Fernet.generate_key()
        """
        if isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt (e.g., database password)

        Returns:
            URL-safe base64-encoded encrypted token
        """
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        """Decrypt an encrypted token.

        Args:
            token: URL-safe base64-encoded encrypted token

        Returns:
            Original plaintext string

        Raises:
            InvalidToken: If token is invalid or corrupted
        """
        return self._fernet.decrypt(token.encode()).decode()

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key.

        Returns:
            URL-safe base64-encoded 32-byte key
        """
        return Fernet.generate_key().decode()


@lru_cache
def get_encryptor() -> CredentialEncryptor:
    """Get singleton encryptor instance using settings key.

    Returns:
        CredentialEncryptor configured with FERNET_KEY from settings
    """
    from app.config import get_settings
    settings = get_settings()
    return CredentialEncryptor(settings.fernet_key)
