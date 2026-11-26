"""Öffentliche Datenbank-API des PasswordManagers.

Die Datenbank ist jetzt ein *verschlüsselter Tresor*: sie muss zuerst mit dem
Master-Passwort entsperrt werden, danach funktionieren die bekannten Funktionen
unverändert.

    from models import dbinit

    dbinit.unlock("mein-master-passwort")     # einmal beim App-Start
    dbinit.create_password_entry("github.com", "geheim", note="privat")
    for row in dbinit.list_all_passwords():
        print(row["url"])
    dbinit.lock()                             # beim Beenden
"""

import os
import sqlite3
from contextlib import closing

from .crypto import InvalidPassword
from .database import Vault

VAULT_PATH = "database.vault"
LEGACY_DB_PATH = "database.db"

_vault = None


# -- Entsperren / Sperren ------------------------------------------------------
def unlock(master_password, path=VAULT_PATH):
    """Tresor entsperren. Wirft InvalidPassword bei falschem Passwort."""
    global _vault
    lock()
    _vault = Vault.open(path, master_password)
    return _vault


def lock():
    """Tresor schließen und Schlüssel aus dem Speicher werfen."""
    global _vault
    if _vault is not None:
        _vault.close()
        _vault = None


def is_unlocked():
    return _vault is not None


def get_vault():
    """Aktuell entsperrten Tresor holen (oder RuntimeError)."""
    if _vault is None:
        raise RuntimeError("Tresor ist gesperrt - zuerst dbinit.unlock() aufrufen.")
    return _vault


# -- Schema --------------------------------------------------------------------
def init_db(path=VAULT_PATH, master_password=None):
    """Neuen, leeren Tresor anlegen (nur falls noch keiner existiert)."""
    global _vault
    if os.path.exists(path):
        raise FileExistsError(f"{path} existiert bereits.")
    _vault = Vault.create(path, master_password)
    return _vault


# -- CRUD ----------------------------------------------------------------------
def create_password_entry(url, password, note=""):
    """Einen Eintrag anlegen (wird sofort verschlüsselt gespeichert)."""
    with get_vault().write() as con:
        con.execute(
            "INSERT INTO password (url, password, note) VALUES (?, ?, ?)",
            (url, password, note),
        )


def update_password_entry(url, password=None, note=None):
    """Passwort und/oder Notiz eines bestehenden Eintrags ändern."""
    with get_vault().write() as con:
        if password is not None:
            con.execute("UPDATE password SET password = ? WHERE url = ?", (password, url))
        if note is not None:
            con.execute("UPDATE password SET note = ? WHERE url = ?", (note, url))


def delete_password_entry(url):
    with get_vault().write() as con:
        con.execute("DELETE FROM password WHERE url = ?", (url,))


def list_all_passwords():
    """Alle Einträge zurückgeben."""
    with get_vault().read() as con:
        return con.execute("SELECT url, password, note FROM password ORDER BY url").fetchall()


def search_password_by_url(url):
    """Einträge zu einer URL zurückgeben."""
    with get_vault().read() as con:
        return con.execute(
            "SELECT url, password, note FROM password WHERE url = ?", (url,)
        ).fetchall()


def change_master_password(new_master_password):
    """Master-Passwort ändern (Tresor wird neu verschlüsselt)."""
    get_vault().change_master_password(new_master_password)


# -- Migration der alten Klartext-DB ------------------------------------------
def migrate_plaintext_db(master_password, path=VAULT_PATH, legacy=LEGACY_DB_PATH):
    """Bestehende Klartext-DB in einen verschlüsselten Tresor überführen.

    Danach wird die Klartext-Datei überschrieben und gelöscht - sonst wäre die
    Verschlüsselung sinnlos. Vorher ein Backup machen, wenn Zweifel bestehen.
    """
    global _vault
    if os.path.exists(path):
        raise FileExistsError(f"{path} existiert bereits - bitte erst wegräumen.")
    if not os.path.exists(legacy):
        raise FileNotFoundError(f"Keine alte Datenbank unter {legacy} gefunden.")

    with closing(sqlite3.connect(legacy)) as old:
        old.row_factory = sqlite3.Row
        rows = old.execute("SELECT url, password, note FROM password").fetchall()

    _vault = Vault.create(path, master_password)
    with _vault.write() as con:
        con.executemany(
            "INSERT INTO password (url, password, note) VALUES (?, ?, ?)",
            [(r["url"], r["password"], r["note"] or "") for r in rows],
        )
    migrated = len(rows)
    lock()

    _shred(legacy)
    return migrated


def _shred(path):
    """Klartext-Datei mit Nullen überschreiben, dann entfernen."""
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as fh:
            fh.write(b"\0" * size)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        os.unlink(path)


__all__ = [
    "InvalidPassword",
    "unlock",
    "lock",
    "is_unlocked",
    "get_vault",
    "init_db",
    "create_password_entry",
    "update_password_entry",
    "delete_password_entry",
    "list_all_passwords",
    "search_password_by_url",
    "change_master_password",
    "migrate_plaintext_db",
    "VAULT_PATH",
]
