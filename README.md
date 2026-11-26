# PasswordManager

Verschlüsselter Passwort-Tresor: die SQLite-Datenbank liegt **nur verschlüsselt**
auf der Platte und ist ausschließlich mit dem Master-Passwort entschlüsselbar.

## Kryptografie

| Zweck | Verfahren |
|---|---|
| Schlüsselableitung | PBKDF2-HMAC-**SHA256**, 600.000 Iterationen, 16-Byte-Zufalls-Salt |
| Verschlüsselung | AES-256-GCM (vertraulich **und** manipulationssicher) |
| Schlüssellänge | 32 Byte (256 Bit) |

SHA-256 allein ist ein Hash und kann nicht verschlüsseln. Es wird deshalb als
Basis für PBKDF2 (Schlüsselableitung) verwendet – das ist der kryptografisch
richtige Einsatz. Das Master-Passwort selbst wird nie gespeichert, nur der
abgeleitete Schlüssel (und der nur im RAM).

Dateiformat (`database.vault`):

```
| "PMVAULT1" (8) | Iterationen (4, BE) | Salt (16) | Nonce (12) | AES-256-GCM Ciphertext + Tag |
```

Eigenschaften:
- Salt + Nonce sind zufällig → gleiche Passwörter ergeben nie gleiche Ciphertexte.
- GCM-Auth-Tag → falsches Passwort oder ein gekipptes Bit führt zu `InvalidPassword`.
- Die DB wird entschlüsselt **in den RAM** geladen, es entstehen keine
  Klartext-Temp-Dateien. Nach jedem Schreibvorgang wird der Speicherstand neu
  verschlüsselt und **atomar** (`os.replace`) zurückgeschrieben.
- Verschlüsselt wird ein portabler SQL-Dump (kein rohes SQLite-Abbild), damit
  dieselbe Tresor-Datei unter Python 3.9 wie 3.13 lesbar bleibt.
- Dateirechte `0600`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Läuft ab Python 3.9. Wichtig: den Interpreter aus der venv benutzen
(`.venv/bin/python`), sonst fehlt `cryptography`.

## Benutzung (CLI)

```bash
python cli.py init                 # neuen Tresor anlegen (fragt Master-Passwort ab)
python cli.py add github.com       # Eintrag hinzufügen
python cli.py list                 # Übersicht (Passwörter maskiert)
python cli.py list --show          # mit Klartext-Passwörtern
python cli.py get github.com       # einzelner Eintrag
python cli.py delete github.com
python cli.py passwd               # Master-Passwort ändern (neu verschlüsseln)
python cli.py migrate              # alte database.db verschlüsseln
```

`--master-password "..."` überspringt die interaktive Abfrage (z. B. für Skripte,
landet aber in der Shell-History – lieber `getpass`/Umgebungsvariable nutzen).

## Benutzung (Code)

```python
from models import dbinit

dbinit.unlock("mein-master-passwort")        # beim App-Start
dbinit.create_password_entry("github.com", "geheim", note="privat")

for row in dbinit.list_all_passwords():
    print(row["url"], row["note"])

dbinit.lock()                                # beim Beenden
```

## Migration der alten Klartext-DB

```bash
python cli.py migrate            # erzeugt database.vault aus database.db
```

Die alte `database.db` wird nach erfolgreicher Migration mit Nullen überschrieben
und gelöscht – sonst wäre die Verschlüsselung wertlos. **Vorher ein Backup machen**,
falls etwas schiefgeht.

## Tests

```bash
.venv/bin/python tests/test_vault.py     # oder: .venv/bin/python -m pytest
```

9 Tests. Geprüft wird u. a.: kein Klartext in der Datei, falsches Passwort wird
abgelehnt, Manipulation wird erkannt, kein Klartext-Temp-File, Passwortwechsel,
Migration, portables Dateiformat.

## Bewusst nicht umgesetzt

- Der abgeleitete Schlüssel liegt im Prozess-RAM, solange der Tresor offen ist
  (bei Python nicht zuverlässig löschbar). Für mehr Härtung: Schlüssel nur
  pro Operation ableiten (Kosten: ~47 ms je Zugriff).
- Kein Zwangs-Lock nach Inaktivität – `dbinit.lock()` bzw. `Vault.close()` selbst aufrufen.
