import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken

from packages.shared.config import get_settings


class CryptoService:
    _fernet: Fernet | None = None

    @classmethod
    def _get_fernet(cls) -> Fernet:
        if cls._fernet is None:
            settings = get_settings()
            secret = settings.secret_key.get_secret_value()

            # Fernet requires a 32-byte url-safe base64-encoded key.
            # We hash the application's secret_key to guarantee 32 bytes.
            key = hashlib.sha256(secret.encode("utf-8")).digest()
            fernet_key = base64.urlsafe_b64encode(key)

            cls._fernet = Fernet(fernet_key)
        return cls._fernet

    @classmethod
    def encrypt(cls, data: str) -> str:
        """Encrypts a string and returns a url-safe base64 encoded string."""
        if not data:
            return data
        f = cls._get_fernet()
        return f.encrypt(data.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, encrypted_data: str) -> str:
        """Decrypt credentials, allowing only recognizable legacy plaintext keys."""
        if not encrypted_data:
            return encrypted_data
        try:
            f = cls._get_fernet()
            return f.decrypt(encrypted_data.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Older records may contain GitHub or supported provider tokens in
            # plaintext. Never return arbitrary malformed ciphertext as a key.
            if re.fullmatch(r"(?:gh[pousr]_|github_pat_|sk-|gsk_)[A-Za-z0-9_-]{8,}", encrypted_data):
                return encrypted_data
            raise ValueError("Stored credential could not be decrypted") from None
