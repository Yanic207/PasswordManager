"""Schlüsselableitung und Verschlüsselung für den Passwort-Tresor.

SHA-256 wird an zwei Stellen als Basis benutzt:

  1. PBKDF2-HMAC-SHA256  -> Master-Passwort + Salt  ==>  256-Bit-Schlüssel
     (viele Iterationen, damit Brute-Force teuer wird)
  2. AES-256-GCM         -> verschlüsselt UND authentifiziert den Inhalt
     (falsches Passwort oder Manipulation => InvalidPassword)
"""

import os
import struct

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Das Paket 'cryptography' fehlt. Installieren mit:\n"
        "    .venv/bin/pip install -r requirements.txt"
    ) from exc

# --- Dateiformat ------------------------------------------------------------
# | MAGIC (8) | Iterationen (4, big endian) | Salt (16) | Nonce (12) | Ciphertext |
MAGIC = b"PMVAULT1"
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32
KDF_ITERATIONS = 600_000

HEADER = struct.Struct(">8sI16s")


class InvalidPassword(Exception):
    """Master-Passwort falsch oder Datei manipuliert/beschädigt."""


def derive_key(master_password: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    """Schlüssel aus dem Master-Passwort ableiten (PBKDF2 mit HMAC-SHA256)."""
    if not master_password:
        raise ValueError("Das Master-Passwort darf nicht leer sein.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(master_password.encode("utf-8"))


def encrypt_blob(key: bytes, plaintext: bytes) -> bytes:
    """Nonce + AES-256-GCM-Ciphertext (inkl. Auth-Tag)."""
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def decrypt_blob(key: bytes, blob: bytes) -> bytes:
    """Umkehrung von encrypt_blob; wirft InvalidPassword bei falschem Schlüssel."""
    if len(blob) <= NONCE_LEN:
        raise InvalidPassword("Die Tresor-Datei ist beschädigt oder leer.")
    nonce, ciphertext = blob[:NONCE_LEN], blob[NONCE_LEN:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise InvalidPassword(
            "Master-Passwort falsch oder Tresor-Datei manipuliert."
        ) from exc


def pack_header(salt: bytes, iterations: int) -> bytes:
    return HEADER.pack(MAGIC, iterations, salt)


def unpack_header(raw: bytes) -> tuple:
    """(salt, iterations) aus der Datei lesen und Format prüfen."""
    if len(raw) < HEADER.size:
        raise InvalidPassword("Die Tresor-Datei ist beschädigt oder keine Tresor-Datei.")
    magic, iterations, salt = HEADER.unpack_from(raw)
    if magic != MAGIC:
        raise InvalidPassword(
            "Unbekanntes Dateiformat - ist das wirklich ein verschlüsselter Tresor?"
        )
    return salt, iterations
