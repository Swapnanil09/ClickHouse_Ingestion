import base64
import hashlib
from cryptography.fernet import Fernet
from backend.app.config import settings

def get_encryption_cipher() -> Fernet:
    # Derive a 32-byte key from JWT_SECRET using SHA-256
    derived_key = hashlib.sha256(settings.JWT_SECRET.encode()).digest()
    base64_key = base64.urlsafe_b64encode(derived_key)
    return Fernet(base64_key)

def encrypt_password(plain_text: str) -> str:
    if not plain_text:
        return ""
    cipher = get_encryption_cipher()
    return cipher.encrypt(plain_text.encode()).decode()

def decrypt_password(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    try:
        cipher = get_encryption_cipher()
        return cipher.decrypt(cipher_text.encode()).decode()
    except Exception:
        # Fallback to plain text if decryption fails
        return cipher_text
