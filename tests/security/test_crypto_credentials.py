import pytest
from cryptography.fernet import Fernet

from packages.shared.crypto import CryptoService


def test_encrypted_credentials_round_trip(monkeypatch):
    monkeypatch.setattr(CryptoService, "_fernet", Fernet(Fernet.generate_key()))
    encrypted = CryptoService.encrypt("sk-validproviderkey123")
    assert CryptoService.decrypt(encrypted) == "sk-validproviderkey123"


def test_malformed_ciphertext_is_not_treated_as_plaintext(monkeypatch):
    monkeypatch.setattr(CryptoService, "_fernet", Fernet(Fernet.generate_key()))
    with pytest.raises(ValueError, match="could not be decrypted"):
        CryptoService.decrypt("gAAAA-tampered-ciphertext")


@pytest.mark.parametrize("legacy_key", ["gho_legacytoken1234", "github_pat_legacytoken1234", "sk-legacyprovider1234", "gsk_legacyprovider1234"])
def test_recognizable_legacy_plaintext_credentials_remain_usable(monkeypatch, legacy_key):
    monkeypatch.setattr(CryptoService, "_fernet", Fernet(Fernet.generate_key()))
    assert CryptoService.decrypt(legacy_key) == legacy_key
