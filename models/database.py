"""Verschlüsselter Tresor: die SQLite-Datenbank liegt ausschließlich
verschlüsselt auf der Platte und existiert nur im RAM als Klartext.

Ablauf
------
* ``Vault.create()``  legt eine neue, leere Tresor-Datei an (Schema drin).
* ``Vault.open()``    entschlüsselt die Datei und baut daraus eine
                      In-Memory-SQLite-Datenbank (``executescript``).
* Nach jeder schreibenden Transaktion wird der Speicherstand als SQL-Dump
  (``iterdump``) erneut verschlüsselt und zurückgeschrieben.

Dadurch gibt es zu keinem Zeitpunkt eine Klartext-Datei auf dem Datenträger
und auch keine Temp-Dateien, die man wiederherstellen könnte.

Warum SQL-Dump und nicht ``Connection.serialize()``?
  * ``serialize``/``deserialize`` gibt es erst ab Python 3.11
  * ein rohes SQLite-Abbild ist an SQLite-Version/Plattform gebunden;
    ein Tresor muss aber überall gleich lesbar bleiben
  * ``iterdump``/``executescript`` ist der portable, offizielle Weg
"""

import os
import sqlite3
from contextlib import contextmanager

from .crypto import (
    HEADER,
    KDF_ITERATIONS,
    SALT_LEN,
    decrypt_blob,
    derive_key,
    encrypt_blob,
    pack_header,
    unpack_header,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS password (
    url      TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    note     TEXT
);
"""


class Vault:
    """Ein entsperrter Tresor. Hält den Schlüssel, aber nie das Passwort."""

    def __init__(self, path, key, salt, iterations, con):
        self.path = path
        self._key = key
        self._salt = salt
        self._iterations = iterations
        self._con = con

    # -- Erzeugen / Öffnen ---------------------------------------------------
    @classmethod
    def create(cls, path, master_password, iterations=KDF_ITERATIONS):
        """Neue Tresor-Datei anlegen. Existiert sie schon -> FileExistsError."""
        if os.path.exists(path):
            raise FileExistsError(f"{path} existiert bereits.")
        salt = os.urandom(SALT_LEN)
        key = derive_key(master_password, salt, iterations)
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA)
        vault = cls(path, key, salt, iterations, con)
        vault.save()
        return vault

    @classmethod
    def open(cls, path, master_password):
        """Tresor mit dem Master-Passwort entsperren."""
        with open(path, "rb") as fh:
            raw = fh.read()
        salt, iterations = unpack_header(raw)
        key = derive_key(master_password, salt, iterations)
        plaintext = decrypt_blob(key, raw[HEADER.size:])

        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.executescript(plaintext.decode("utf-8"))
        # Falls eine ältere Tresor-Version das Schema noch nicht hatte.
        con.executescript(SCHEMA)
        return cls(path, key, salt, iterations, con)

    def _dump(self):
        """Portables Klartext-Abbild der DB (nie auf Platte, nur im RAM)."""
        self._con.commit()
        return "\n".join(self._con.iterdump()).encode("utf-8")

    # -- Zugriff -------------------------------------------------------------
    @contextmanager
    def read(self):
        """Nur lesende Operationen (kein Zurückschreiben der Datei)."""
        yield self._con

    @contextmanager
    def write(self):
        """Schreibende Operation: Transaktion + verschlüsseltes Speichern."""
        with self._con:  # commit bei Erfolg, rollback bei Exception
            yield self._con
        self.save()

    # -- Persistenz ----------------------------------------------------------
    def save(self):
        """RAM-Stand als SQL-Dump verschlüsseln und atomar auf Platte schreiben."""
        blob = encrypt_blob(self._key, self._dump())
        raw = pack_header(self._salt, self._iterations) + blob

        tmp = f"{self.path}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(raw)
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)  # atomar, keine halben Tresore

    def change_master_password(self, new_master_password):
        """Neues Passwort setzen (neuer Salt + neuer Schlüssel)."""
        self._salt = os.urandom(SALT_LEN)
        self._key = derive_key(new_master_password, self._salt, self._iterations)
        self.save()

    def close(self):
        self._con.close()
        self._key = b""
        self._con = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
