#!/usr/bin/env python3
"""Passwörter erfassen.

Beim ersten Start wird der Tresor automatisch angelegt und nach einem neuen
Master-Passwort gefragt. Danach läuft eine Schleife: URL, Benutzername,
Passwort, Notiz -> speichern -> nächster Eintrag.

URL einfach leer lassen (Enter) = fertig.
Zum Ansehen: show.py
"""

import getpass
import os
import sys

from models import dbinit
from models.crypto import InvalidPassword

MIN_MASTER_LEN = 8
MAX_VERSUCHE = 3


def neues_master_passwort():
    """Neues Master-Passwort zweimal abfragen, bis es passt."""
    while True:
        pw = getpass.getpass("Neues Master-Passwort: ")
        if len(pw) < MIN_MASTER_LEN:
            print(f"  Bitte mindestens {MIN_MASTER_LEN} Zeichen.")
            continue
        if pw != getpass.getpass("Master-Passwort wiederholen: "):
            print("  Die Passwörter stimmen nicht überein.")
            continue
        return pw


def tresor_oeffnen():
    """Tresor anlegen (falls nötig) und entsperren."""
    if os.path.exists(dbinit.VAULT_PATH):
        for versuch in range(MAX_VERSUCHE):
            try:
                dbinit.unlock(getpass.getpass("Master-Passwort: "))
                return
            except InvalidPassword as exc:
                rest = MAX_VERSUCHE - versuch - 1
                print(f"  {exc}" + (f" Noch {rest} Versuche." if rest else ""))
        sys.exit("Abgebrochen.")

    print(f"Kein Tresor gefunden - {dbinit.VAULT_PATH} wird angelegt.")
    print("WICHTIG: Dieses Master-Passwort ist nicht wiederherstellbar!\n")
    dbinit.init_db(master_password=neues_master_passwort())
    print(f"Tresor angelegt: {dbinit.VAULT_PATH}\n")


def eintrag_erfassen():
    """Fragt die Felder eines Eintrags ab und speichert ihn."""
    url = input("URL: ").strip()
    if not url:
        return False

    if dbinit.entry_exists(url):
        antwort = input(f"  '{url}' existiert schon - überschreiben? [j/N] ").strip().lower()
        if antwort not in ("j", "ja", "y"):
            print("  übersprungen.\n")
            return True

    username = input("Benutzername: ").strip()
    password = getpass.getpass("Passwort: ")
    note = input("Notiz (optional): ").strip()

    dbinit.save_password_entry(url, username, password, note)
    print(f"  gespeichert: {url}\n")
    return True


def main():
    tresor_oeffnen()
    print("Neue Einträge - URL leer lassen + Enter zum Beenden.\n")
    anzahl = 0
    try:
        while eintrag_erfassen():
            anzahl += 1
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        dbinit.lock()
    print(f"\n{anzahl} Eintrag/Einträge gespeichert in {dbinit.VAULT_PATH}.")
    print("Ansehen mit: .venv/bin/python show.py")


if __name__ == "__main__":
    main()
