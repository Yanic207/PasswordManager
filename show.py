#!/usr/bin/env python3
"""Passwörter anzeigen.

Fragt das Master-Passwort und zeigt alle Einträge an.

    .venv/bin/python show.py            # alles
    .venv/bin/python show.py git        # nur Treffer in URL/Benutzer/Notiz
    .venv/bin/python show.py --versteckt  # Passwörter maskieren
"""

import getpass
import os
import sys

from models import dbinit
from models.crypto import InvalidPassword


def main():
    argumente = [a for a in sys.argv[1:] if not a.startswith("-")]
    versteckt = any(a in ("-v", "--versteckt", "--hide") for a in sys.argv[1:])
    suche = argumente[0].lower() if argumente else None

    if not os.path.exists(dbinit.VAULT_PATH):
        sys.exit(f"Kein Tresor unter {dbinit.VAULT_PATH}. Erst cli.py starten.")

    try:
        dbinit.unlock(getpass.getpass("Master-Passwort: "))
    except InvalidPassword as exc:
        sys.exit(str(exc))

    try:
        eintraege = dbinit.list_all_passwords()
    finally:
        dbinit.lock()

    if suche:
        eintraege = [
            e
            for e in eintraege
            if suche in e["url"].lower()
            or suche in (e["username"] or "").lower()
            or suche in (e["note"] or "").lower()
        ]

    if not eintraege:
        print("Keine Einträge gefunden." if suche else "Der Tresor ist leer.")
        return

    breite_url = max(len(e["url"]) for e in eintraege)
    breite_user = max([len(e["username"] or "-") for e in eintraege] + [8])

    print(f"\n{len(eintraege)} Eintrag/Einträge\n")
    kopf = f"{'URL':<{breite_url}}  {'BENUTZER':<{breite_user}}  PASSWORT"
    print(kopf)
    print("-" * (len(kopf) + 12))
    for e in eintraege:
        pw = "*" * 10 if versteckt else e["password"]
        print(f"{e['url']:<{breite_url}}  {e['username'] or '-':<{breite_user}}  {pw}")
        if e["note"]:
            print(f"{'':<{breite_url}}  Notiz: {e['note']}")
    print()


if __name__ == "__main__":
    main()
