#!/usr/bin/env python3
"""Kommandozeile für den verschlüsselten Passwort-Tresor.

Beispiele:
    python cli.py init                       # neuen Tresor anlegen
    python cli.py add github.com             # Eintrag hinzufügen
    python cli.py list                       # alle Einträge
    python cli.py get github.com             # ein Eintrag
    python cli.py passwd                     # Master-Passwort ändern
    python cli.py migrate                    # alte database.db verschlüsseln
"""

import argparse
import getpass
import sys

from models import dbinit
from models.crypto import InvalidPassword


def ask_master_password(confirm=False):
    pw = getpass.getpass("Master-Passwort: ")
    if confirm:
        if pw != getpass.getpass("Master-Passwort wiederholen: "):
            sys.exit("Die Passwörter stimmen nicht überein.")
        if len(pw) < 8:
            sys.exit("Das Master-Passwort braucht mindestens 8 Zeichen.")
    return pw


def unlock(args):
    try:
        dbinit.unlock(args.master_password or ask_master_password(), path=args.vault)
    except FileNotFoundError:
        sys.exit(f"Kein Tresor unter {args.vault}. Erst 'init' ausführen.")
    except InvalidPassword as exc:
        sys.exit(str(exc))


def cmd_init(args):
    dbinit.init_db(path=args.vault, master_password=args.master_password or ask_master_password(confirm=True))
    print(f"Tresor angelegt: {args.vault}")


def cmd_add(args):
    # Reihenfolge: Eintragsdaten zuerst, Master-Passwort zuletzt (einmal entsperren).
    if args.note is not None:
        note = args.note
    elif sys.stdin.isatty():
        note = input("Notiz (optional): ")
    else:
        note = ""
    password = args.password or ask_master_password(confirm=True)
    unlock(args)
    dbinit.create_password_entry(args.url, password, note)
    print(f"Gespeichert: {args.url}")


def cmd_list(args):
    unlock(args)
    rows = dbinit.list_all_passwords()
    if not rows:
        print("Tresor ist leer.")
        return
    for row in rows:
        shown = row["password"] if args.show else "*" * 12
        print(f"{row['url']:<35} {shown}  {row['note'] or ''}")


def cmd_get(args):
    unlock(args)
    rows = dbinit.search_password_by_url(args.url)
    if not rows:
        sys.exit(f"Kein Eintrag für {args.url}.")
    for row in rows:
        print(f"url:      {row['url']}")
        print(f"password: {row['password']}")
        print(f"note:     {row['note'] or ''}")


def cmd_delete(args):
    unlock(args)
    dbinit.delete_password_entry(args.url)
    print(f"Gelöscht: {args.url}")


def cmd_passwd(args):
    unlock(args)
    dbinit.change_master_password(ask_master_password(confirm=True))
    print("Master-Passwort geändert, Tresor neu verschlüsselt.")


def cmd_migrate(args):
    try:
        count = dbinit.migrate_plaintext_db(
            args.master_password or ask_master_password(confirm=True),
            path=args.vault,
            legacy=args.legacy,
        )
    except (FileExistsError, FileNotFoundError) as exc:
        sys.exit(str(exc))
    print(f"{count} Einträge nach {args.vault} verschlüsselt.")
    print(f"Klartext-Datei {args.legacy} wurde überschrieben und gelöscht.")


def build_parser():
    p = argparse.ArgumentParser(description="Verschlüsselter Passwort-Tresor (PBKDF2-SHA256 + AES-256-GCM)")
    p.add_argument("--vault", default=dbinit.VAULT_PATH, help="Pfad zur Tresor-Datei")
    p.add_argument("--master-password", help="für Skripte; sonst interaktive Abfrage")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="neuen Tresor anlegen").set_defaults(func=cmd_init)

    a = sub.add_parser("add", help="Eintrag anlegen")
    a.add_argument("url")
    a.add_argument("--password", help="statt interaktiver Abfrage")
    a.add_argument("--note")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="alle Einträge anzeigen")
    l.add_argument("--show", action="store_true", help="Passwörter im Klartext zeigen")
    l.set_defaults(func=cmd_list)

    g = sub.add_parser("get", help="Eintrag anzeigen")
    g.add_argument("url")
    g.set_defaults(func=cmd_get)

    d = sub.add_parser("delete", help="Eintrag löschen")
    d.add_argument("url")
    d.set_defaults(func=cmd_delete)

    sub.add_parser("passwd", help="Master-Passwort ändern").set_defaults(func=cmd_passwd)

    m = sub.add_parser("migrate", help="alte Klartext-DB verschlüsseln")
    m.add_argument("--legacy", default=dbinit.LEGACY_DB_PATH)
    m.set_defaults(func=cmd_migrate)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    finally:
        dbinit.lock()


if __name__ == "__main__":
    main()
