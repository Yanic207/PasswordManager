"""End-to-End-Tests für cli.py und show.py.

Die Skripte werden in einem echten PTY gestartet (getpass braucht ein TTY) und
bekommen ihre Antworten genau dann, wenn die jeweilige Frage erscheint.

    python3 tests/test_cli.py
"""

import os
import pty
import re
import select
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = "master-pw-123"


def bediene(script, antworten, args=(), timeout=60):
    """Startet script, beantwortet die Fragen in der gegebenen Reihenfolge.

    antworten: Liste von (Frage-Teilstring, Antwort). None = nur darauf warten.
    Gibt die komplette Bildschirmausgabe zurück.
    """
    env = {**os.environ, "PYTHONPATH": ROOT, "PYTHONIOENCODING": "utf-8"}
    pid, fd = pty.fork()
    if pid == 0:  # Kindprozess: im Projektwurzel-Verzeichnis des Tempdirs starten
        os.execve(sys.executable, [sys.executable, os.path.join(ROOT, script), *args], env)

    ausgabe = b""
    pos = 0
    offen = list(antworten)
    ende = time.time() + timeout
    try:
        while offen and time.time() < ende:
            if select.select([fd], [], [], 0.2)[0]:
                try:
                    stueck = os.read(fd, 4096)
                except OSError:
                    stueck = b""
                if not stueck:
                    break
                ausgabe += stueck
                text = ausgabe.decode("utf-8", "replace")
                while offen:
                    frage, antwort = offen[0]
                    treffer = text.find(frage, pos)
                    if treffer < 0:
                        break
                    pos = treffer + len(frage)
                    offen.pop(0)
                    if antwort is not None:
                        os.write(fd, (antwort + "\n").encode())
        # Rest einsammeln, damit auch die Abschlussmeldung im Ergebnis steht
        rest_ende = time.time() + 2
        while time.time() < rest_ende:
            if select.select([fd], [], [], 0.2)[0]:
                try:
                    stueck = os.read(fd, 4096)
                except OSError:
                    break
                if not stueck:
                    break
                ausgabe += stueck
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        _, status = os.waitpid(pid, 0)
    return ausgabe.decode("utf-8", "replace"), status


def _tmpdir():
    return tempfile.TemporaryDirectory()


def _ohne_ansi(text):
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text.replace("\r", ""))


CLI_ERSTER_EINTRAG = [
    ("Neues Master-Passwort:", MASTER),          # Tresor anlegen
    ("Master-Passwort wiederholen:", MASTER),
    ("URL:", "github.com"),
    ("Benutzername:", "yanic"),
    ("Passwort:", "gh-geheim-123"),
    ("Notiz (optional):", "Arbeit"),
    ("URL:", ""),                                # leer = fertig
    ("Ansehen mit", None),
]


def test_cli_legt_tresor_an_und_speichert():
    with _tmpdir() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            out, status = bediene("cli.py", CLI_ERSTER_EINTRAG)
        finally:
            os.chdir(cwd)
        out = _ohne_ansi(out)

        assert status == 0, f"Exit-Status {status}\n{out}"
        assert "Kein Tresor gefunden" in out
        assert "Tresor angelegt" in out
        assert "gespeichert: github.com" in out
        assert "1 Eintrag" in out

        with open(os.path.join(d, "database.vault"), "rb") as fh:
            roh = fh.read()
        for klartext in (b"github.com", b"yanic", b"gh-geheim-123", b"Arbeit"):
            assert klartext not in roh, f"{klartext!r} steht im Klartext in der Datei!"
        # nach dem Beenden darf kein Klartext-Temp-File uebrig sein
        assert sorted(os.listdir(d)) == ["database.vault"]


def test_cli_fragt_bei_zweitem_start_nach_master_passwort():
    with _tmpdir() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            bediene("cli.py", CLI_ERSTER_EINTRAG[:-2] + [("URL:", "")])
            # zweiter Start: kein "Neues Master-Passwort" mehr, nur abfragen
            out, status = bediene("cli.py", [("Master-Passwort:", MASTER), ("URL:", "")])
        finally:
            os.chdir(cwd)
        out = _ohne_ansi(out)
        assert "Kein Tresor gefunden" not in out
        assert "Neues Master-Passwort" not in out
        assert status == 0, out


def test_cli_bricht_bei_falschem_passwort_ab():
    with _tmpdir() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            bediene("cli.py", CLI_ERSTER_EINTRAG[:-2] + [("URL:", "")])
            out, status = bediene(
                "cli.py",
                [("Master-Passwort:", "falsch")] * 3,
            )
        finally:
            os.chdir(cwd)
        out = _ohne_ansi(out)
        assert status != 0, f"falsches Passwort wurde akzeptiert\n{out}"
        assert "Master-Passwort falsch" in out


def test_cli_ueberschreibt_nur_nach_bestaetigung():
    with _tmpdir() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            bediene("cli.py", CLI_ERSTER_EINTRAG[:-2] + [("URL:", "")])
            # gleiche URL, Ueberschreiben verneinen -> nichts aendert sich
            out, _ = bediene("cli.py", [
                ("Master-Passwort:", MASTER),
                ("URL:", "github.com"),
                ("überschreiben?", "n"),
                ("URL:", ""),
            ])
        finally:
            os.chdir(cwd)
        assert "übersprungen" in _ohne_ansi(out)


def test_show_zeigt_eintraege():
    with _tmpdir() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            bediene("cli.py", CLI_ERSTER_EINTRAG[:-2] + [("URL:", "")])
            out, status = bediene("show.py", [("Master-Passwort:", MASTER)])
        finally:
            os.chdir(cwd)
        out = _ohne_ansi(out)
        assert status == 0, out
        assert "github.com" in out
        assert "yanic" in out
        assert "gh-geheim-123" in out
        assert "Arbeit" in out


def test_show_versteckt_und_filtert():
    with _tmpdir() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            bediene("cli.py", CLI_ERSTER_EINTRAG[:-2] + [("URL:", "")])
            maskiert, _ = bediene("show.py", [("Master-Passwort:", MASTER)], args=["--versteckt"])
            gefiltert, _ = bediene("show.py", [("Master-Passwort:", MASTER)], args=["bank"])
            treffer, _ = bediene("show.py", [("Master-Passwort:", MASTER)], args=["github"])
        finally:
            os.chdir(cwd)

        maskiert = _ohne_ansi(maskiert)
        assert "github.com" in maskiert          # Eintrag sichtbar
        assert "gh-geheim-123" not in maskiert   # Passwort aber nicht
        assert "**********" in maskiert

        # Filter "bank": nicht vorhanden -> Hinweis statt Eintrag
        gefiltert = _ohne_ansi(gefiltert)
        assert "github.com" not in gefiltert
        assert "Keine Einträge gefunden" in gefiltert

        # Filter "github": Treffer
        treffer = _ohne_ansi(treffer)
        assert "github.com" in treffer
        assert "gh-geheim-123" in treffer


def test_show_ohne_tresor():
    with _tmpdir() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            out, status = bediene("show.py", [("Kein Tresor", None)])
        finally:
            os.chdir(cwd)
        assert status != 0
        assert "Kein Tresor" in _ohne_ansi(out)


if __name__ == "__main__":
    fehler = 0
    nur = sys.argv[1] if len(sys.argv) > 1 else ""
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn) and nur in name:
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as exc:  # noqa: BLE001
                fehler += 1
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    raise SystemExit(1 if fehler else 0)
