"""Tests für den verschlüsselten Tresor: pytest tests/  oder  python tests/test_vault.py"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import dbinit
from models.crypto import MAGIC, InvalidPassword, derive_key, encrypt_blob, decrypt_blob
from models.database import Vault

PW = "korrekt-pferd-batterie-klammer"


def _tmpdir():
    return tempfile.TemporaryDirectory()


def test_kdf_is_deterministic_and_salted():
    salt = os.urandom(16)
    assert derive_key(PW, salt) == derive_key(PW, salt)
    assert derive_key(PW, salt) != derive_key(PW, os.urandom(16))
    assert derive_key(PW, salt, iterations=1000) != derive_key(PW, salt)


def test_db_file_is_encrypted():
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        v = Vault.create(path, PW)
        with v.write() as con:
            con.execute("INSERT INTO password (url, username, password, note) VALUES (?,?,?,?)",
                        ("bank.de", "yanic", "s3cret!", "IBAN"))
        v.close()

        raw = open(path, "rb").read()
        assert raw.startswith(MAGIC)
        # Nichts vom Klartext darf im Ciphertext auftauchen
        for needle in (b"bank.de", b"s3cret!", b"IBAN", b"CREATE TABLE", b"SQLite format 3"):
            assert needle not in raw
        assert os.stat(path).st_mode & 0o777 == 0o600


def test_wrong_password_is_rejected():
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        Vault.create(path, PW).close()
        try:
            Vault.open(path, "falsch")
        except InvalidPassword:
            pass
        else:
            raise AssertionError("falsches Passwort wurde akzeptiert")


def test_tampering_is_rejected():
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        Vault.create(path, PW).close()
        raw = bytearray(open(path, "rb").read())
        raw[-5] ^= 0xFF  # ein Bit im Ciphertext kippen
        open(path, "wb").write(bytes(raw))
        try:
            Vault.open(path, PW)
        except InvalidPassword:
            pass
        else:
            raise AssertionError("Manipulation wurde nicht erkannt")


def test_roundtrip_and_no_plaintext_db_on_disk():
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        v = Vault.create(path, PW)
        with v.write() as con:
            con.execute("INSERT INTO password (url, username, password, note) VALUES (?,?,?,?)", ("a.de", "u", "geheim", ""))
        v.close()

        v = Vault.open(path, PW)
        with v.read() as con:
            assert con.execute("SELECT password FROM password").fetchone()[0] == "geheim"
        # während der Laufzeit existiert nur die verschlüsselte Datei
        assert sorted(os.listdir(d)) == ["database.vault"]
        v.close()


def test_change_master_password():
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        v = Vault.create(path, PW)
        with v.write() as con:
            con.execute("INSERT INTO password (url, username, password, note) VALUES (?,?,?,?)", ("x.de", "u", "p", "n"))
        v.change_master_password("anderes-langes-passwort")
        v.close()

        try:
            Vault.open(path, PW)
        except InvalidPassword:
            pass
        else:
            raise AssertionError("altes Passwort funktioniert noch")
        assert Vault.open(path, "anderes-langes-passwort") is not None


def test_public_api():
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        dbinit.init_db(path=path, master_password=PW)
        dbinit.create_password_entry("github.com", "gh-token", "work", username="yanic")
        assert [r["url"] for r in dbinit.list_all_passwords()] == ["github.com"]
        assert dbinit.search_password_by_url("github.com")[0]["note"] == "work"
        assert dbinit.entry_exists("github.com") and not dbinit.entry_exists("gibtsnicht.de")
        dbinit.lock()
        assert not dbinit.is_unlocked()

        dbinit.unlock(PW, path=path)
        dbinit.update_password_entry("github.com", password="neu")
        eintrag = dbinit.search_password_by_url("github.com")[0]
        assert eintrag["password"] == "neu"
        assert eintrag["username"] == "yanic"  # nicht ueberschrieben

        # save_password_entry legt an oder ueberschreibt (Upsert)
        dbinit.save_password_entry("github.com", "neu@user", "pw2", "note2")
        dbinit.save_password_entry("neu.de", "u", "p", "n")
        assert len(dbinit.list_all_passwords()) == 2
        eintrag = dbinit.search_password_by_url("github.com")[0]
        assert (eintrag["username"], eintrag["password"], eintrag["note"]) == (
            "neu@user", "pw2", "note2")
        dbinit.lock()


def test_migration_of_plaintext_db():
    with _tmpdir() as d:
        legacy = os.path.join(d, "database.db")
        vault = os.path.join(d, "database.vault")
        con = sqlite3.connect(legacy)
        con.execute("CREATE TABLE password (url TEXT PRIMARY KEY, password TEXT NOT NULL, note TEXT)")
        con.execute("INSERT INTO password (url, password, note) VALUES ('alt.de', 'klartext', 'migriert')")
        con.commit()
        con.close()

        assert dbinit.migrate_plaintext_db(PW, path=vault, legacy=legacy) == 1
        assert not os.path.exists(legacy)  # Klartext-Datei ist weg

        dbinit.unlock(PW, path=vault)
        assert dbinit.search_password_by_url("alt.de")[0]["password"] == "klartext"
        dbinit.lock()
        assert b"klartext" not in open(vault, "rb").read()


def test_payload_is_portable_sql_dump():
    """Das Format darf nicht an Python-/SQLite-Version gebunden sein."""
    from models.crypto import HEADER, decrypt_blob, unpack_header
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        v = Vault.create(path, PW)
        with v.write() as con:
            con.execute("INSERT INTO password (url, username, password, note) VALUES (?,?,?,?)", ("a.de", "u", "p", ""))
        v.close()

        raw = open(path, "rb").read()
        salt, iterations = unpack_header(raw)
        payload = decrypt_blob(derive_key(PW, salt, iterations), raw[HEADER.size:])
        text = payload.decode("utf-8")  # muss UTF-8 sein, kein Binaer-Abbild
        assert text.startswith("BEGIN TRANSACTION")
        assert "CREATE TABLE password" in text

        # und der Dump laesst sich in jeder SQLite-Version wieder einlesen
        con = sqlite3.connect(":memory:")
        con.executescript(text)
        assert con.execute("SELECT password FROM password").fetchone()[0] == "p"


def test_old_schema_is_migrated():
    """Ein Tresor von vor dem username-Feld muss weiter funktionieren."""
    import sqlite3 as sq
    old = ("BEGIN TRANSACTION;\n"
           "CREATE TABLE password (url TEXT PRIMARY KEY, password TEXT NOT NULL, note TEXT);\n"
           "INSERT INTO password VALUES('alt.de','klartext','notiz');\n"
           "COMMIT;\n")
    with _tmpdir() as d:
        path = os.path.join(d, "database.vault")
        from models.crypto import KDF_ITERATIONS, SALT_LEN, encrypt_blob, pack_header
        salt = os.urandom(SALT_LEN)
        with open(path, "wb") as fh:
            fh.write(pack_header(salt, KDF_ITERATIONS) + encrypt_blob(derive_key(PW, salt), old.encode()))

        v = Vault.open(path, PW)
        with v.read() as con:
            row = con.execute("SELECT url, username, password FROM password").fetchone()
            assert tuple(row) == ("alt.de", "", "klartext")
        v.close()


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    raise SystemExit(1 if failed else 0)
