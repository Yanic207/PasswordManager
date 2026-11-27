# PasswordManager

Verschlüsselter Passwort-Tresor: die SQLite-Datenbank liegt **nur verschlüsselt**
auf der Platte (`database.vault`) und ist ausschließlich mit dem Master-Passwort
entschlüsselbar.

## Am einfachsten: Fenster statt Terminal

**Doppelklick auf `Passwortmanager.command`** im Finder. Fertig.

- Beim ersten Mal: Master-Passwort festlegen (2×).
- Danach: Master-Passwort eingeben → Tabelle mit allen Einträgen.
- Felder unten ausfüllen und **Speichern** drücken. Ein Eintrag aus der Tabelle
  anklicken, um ihn zu ändern; **Löschen** entfernt ihn.
- **Passwort kopieren** legt es in die Zwischenablage.
- **Sperren** schließt den Tresor wieder (Schlüssel wird aus dem Speicher geworfen).

Suchen oben filtert live über URL, Benutzername, Passwort und Notiz.

> Falls `brew install python-tk@3.13` noch nicht gelaufen ist, sagt dir das
> Startskript Bescheid — ohne tkinter gibt es keine Fenster.

## Alternativ: Terminal

```bash
.venv/bin/python gui.py      # gleiche Oberfläche, aus dem Terminal
.venv/bin/python cli.py      # neuer Eintrag, geführt im Terminal
.venv/bin/python show.py     # alles anzeigen
```

`show.py` kennt zwei Extras: `show.py git` (Filter) und `show.py --versteckt`
(Passwörter maskieren).

## Kryptografie

| Zweck | Verfahren |
|---|---|
| Schlüsselableitung | PBKDF2-HMAC-**SHA256**, 600.000 Iterationen, 16-Byte-Zufalls-Salt |
| Verschlüsselung | AES-256-GCM (vertraulich **und** manipulationssicher) |
| Schlüssellänge | 32 Byte (256 Bit) |

SHA-256 allein ist ein Hash und kann nicht verschlüsseln — es wird deshalb als
Basis für PBKDF2 (Schlüsselableitung) verwendet. Das Master-Passwort wird nie
gespeichert, nur der abgeleitete Schlüssel und der nur im RAM.

Dateiformat (`database.vault`):

```
| "PMVAULT1" (8) | Iterationen (4, BE) | Salt (16) | Nonce (12) | AES-256-GCM Ciphertext + Tag |
```

- Salt + Nonce zufällig → gleiche Passwörter ergeben nie gleiche Ciphertexte.
- GCM-Auth-Tag → falsches Passwort oder ein gekipptes Bit führt zu `InvalidPassword`.
- Entschlüsselt wird **in den RAM**; nach jedem Schreibvorgang wird verschlüsselt
  und **atomar** (`os.replace`) zurückgeschrieben — keine Klartext-Temp-Dateien.
- Verschlüsselt wird ein portabler SQL-Dump (nicht `Connection.serialize()`),
  damit die Datei unter Python 3.9 und 3.13 gleich lesbar bleibt.
- Dateirechte `0600`.

## Setup (falls die venv fehlt)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Läuft ab Python 3.9. Wichtig: `.venv/bin/python` benutzen, sonst fehlt `cryptography`.

## Aufbau

```
Passwortmanager.command   Doppelklick-Start der GUI
gui.py                    grafische Oberfläche (tkinter)
cli.py                    Einträge im Terminal erfassen
show.py                   Einträge im Terminal anzeigen
models/crypto.py          PBKDF2-SHA256, AES-256-GCM, Dateiformat
models/database.py        Vault: Klartext nur im RAM, atomares Speichern
models/dbinit.py          API: unlock/lock, CRUD, Passwortwechsel, Migration
tests/                    22 Tests
```

## Tests

```bash
.venv/bin/python tests/test_vault.py     # Krypto & Vault (10)
.venv/bin/python tests/test_cli.py       # cli.py + show.py im PTY (7)
.venv/bin/python tests/test_gui.py       # Fenster, Speichern, Suche (5)
```

## Nützlich zu wissen

- **Master-Passwort vergessen = Daten weg.** Es gibt bewusst keine Hintertür.
- Master-Passwort ändern:
  ```bash
  .venv/bin/python -c "from models import dbinit; from getpass import getpass; \
  dbinit.unlock(getpass('alt: ')); dbinit.change_master_password(getpass('neu: '))"
  ```
- Alte Klartext-Datenbank übernehmen (löscht danach `database.db`):
  ```bash
  .venv/bin/python -c "from models import dbinit; from getpass import getpass; \
  print(dbinit.migrate_plaintext_db(getpass('neu: ')), 'Einträge übernommen')"
  ```
- `database.vault` ist in `.gitignore` — landet nie auf GitHub.
