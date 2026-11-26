# PasswordManager

Verschlüsselter Passwort-Tresor: die SQLite-Datenbank liegt **nur verschlüsselt**
auf der Platte (`database.vault`) und ist ausschließlich mit dem Master-Passwort
entschlüsselbar.

## Bedienung

Zwei Dateien, mehr brauchst du nicht:

```bash
cd /Users/yanic/Development/PasswordManager

.venv/bin/python cli.py      # Passwörter erfassen
.venv/bin/python show.py     # Passwörter ansehen
```

### `cli.py` — erfassen

Beim **ersten Start** legt das Skript den Tresor automatisch an und fragt nach
einem neuen Master-Passwort (2× zur Kontrolle, mind. 8 Zeichen). Ab dem zweiten
Start wird nur noch nach dem bestehenden Master-Passwort gefragt.

Danach läuft eine Schleife:

```
URL: github.com
Benutzername: yanic
Passwort: ***
Notiz (optional): Arbeit
  gespeichert: github.com

URL: ▊                      ← leer lassen + Enter = fertig
```

Existiert eine URL schon, wird vor dem Überschreiben nachgefragt (`[j/N]`).

### `show.py` — ansehen

```
Master-Passwort: ***

3 Einträge

URL           BENUTZER   PASSWORT
--------------------------------------
github.com    yanic      gh-geheim-123
                Notiz: Arbeit
```

| Aufruf | Wirkung |
|---|---|
| `show.py` | alle Einträge |
| `show.py git` | nur Treffer in URL / Benutzername / Notiz |
| `show.py --versteckt` | Passwörter maskieren |

Mit `Strg+C` brichst du jederzeit ab — der Tresor wird dabei sauber geschlossen.

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
cli.py               Einträge erfassen (legt den Tresor automatisch an)
show.py              Einträge anzeigen / filtern
models/crypto.py     PBKDF2-SHA256, AES-256-GCM, Dateiformat
models/database.py   Vault: Klartext nur im RAM, atomares Speichern
models/dbinit.py     API: unlock/lock, CRUD, Passwortwechsel, Migration
tests/               19 Tests
```

## Tests

```bash
.venv/bin/python tests/test_vault.py     # Krypto & Vault (10)
.venv/bin/python tests/test_cli.py       # cli.py + show.py im PTY (7)
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
