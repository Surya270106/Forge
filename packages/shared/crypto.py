import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet
from packages.shared.config import get_settings


class CryptoService:
    _fernet: Optional[Fernet] = None

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
        """Decrypts a url-safe base64 encoded string."""
        if not encrypted_data:
            return encrypted_data
        f = cls._get_fernet()
        return f.decrypt(encrypted_data.encode("utf-8")).decode("utf-8")
