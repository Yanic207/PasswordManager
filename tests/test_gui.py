"""Tests für die grafische Oberfläche (gui.py).

Braucht tkinter. Fehlt es, werden die Tests übersprungen statt zu scheitern.

    .venv/bin/python tests/test_gui.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tkinter as tk

    TK_OK = True
    TK_GRUND = ""
except Exception as exc:  # noqa: BLE001 - kein tkinter
    TK_OK = False
    TK_GRUND = f"{type(exc).__name__}: {exc}"

from models import dbinit

MASTER = "master-pw-123"


def _app():
    """Frische App mit eigenem, leerem Tresor im Tempverzeichnis."""
    import gui

    verzeichnis = tempfile.mkdtemp()
    pfad = os.path.join(verzeichnis, "database.vault")
    try:
        app = gui.App(pfad=pfad)
    except tk.TclError as exc:
        raise RuntimeError(f"übersprungen - Tk startet hier nicht ({exc})") from exc
    app.update()
    return app, pfad


def _skip_wenn_kein_tk():
    if not TK_OK:
        raise RuntimeError(f"übersprungen - kein tkinter ({TK_GRUND})")


def test_erster_start_zeigt_anlegen_bildschirm():
    _skip_wenn_kein_tk()
    app, pfad = _app()
    try:
        assert not os.path.exists(pfad)
        texte = [w.cget("text") for w in app.rahmen.winfo_children() if w.winfo_class() == "TLabel"]
        assert "Willkommen!" in texte
        assert any("neuer Tresor" in t for t in texte)
    finally:
        app.destroy()


def test_entsperren_zeigt_alle_eintraege():
    _skip_wenn_kein_tk()
    app, pfad = _app()
    try:
        dbinit.init_db(path=pfad, master_password=MASTER)
        dbinit.save_password_entry("github.com", "yanic", "gh-geheim", "Arbeit")
        dbinit.lock()

        app._start()  # Tresor existiert -> Login
        app.update()
        assert any(w.winfo_class() == "TEntry" for w in app.rahmen.winfo_children())

        dbinit.unlock(MASTER, path=pfad)
        app._tresor()
        app.update()

        zeilen = app.tree.get_children()
        assert len(zeilen) == 1
        assert app.tree.item(zeilen[0], "values") == ("github.com", "yanic", "gh-geheim", "Arbeit")
        assert app.anzahl.get() == "1 Eintrag/Einträge"
    finally:
        app.destroy()
        dbinit.lock()


def test_speichern_ueberschreiben_und_loeschen():
    _skip_wenn_kein_tk()
    app, pfad = _app()
    try:
        dbinit.init_db(path=pfad, master_password=MASTER)
        app._tresor()
        app.update()

        app.felder["url"].set("bank.de")
        app.felder["username"].set("yanic")
        app.felder["password"].set("iban-geheim")
        app._speichern()
        app.update()
        assert len(app.tree.get_children()) == 1
        assert app.status.get() == "Gespeichert: bank.de"
        assert app.felder["url"].get() == ""  # Formular ist wieder leer

        # gleiche URL = ueberschreiben, keine zweite Zeile
        app.felder["url"].set("bank.de")
        app.felder["password"].set("neu")
        app._speichern()
        app.update()
        assert len(app.tree.get_children()) == 1
        assert dbinit.search_password_by_url("bank.de")[0]["password"] == "neu"

        app.tree.selection_set(app.tree.get_children()[0])
        app.update()
        assert app.felder["url"].get() == "bank.de"  # Auswahl laedt ins Formular
        assert app.felder["password"].get() == "neu"

        dbinit.delete_password_entry("bank.de")
        app._refresh()
        app.update()
        assert len(app.tree.get_children()) == 0
    finally:
        app.destroy()
        dbinit.lock()


def test_suche_und_passwoerter_verbergen():
    _skip_wenn_kein_tk()
    app, pfad = _app()
    try:
        dbinit.init_db(path=pfad, master_password=MASTER)
        dbinit.save_password_entry("github.com", "yanic", "gh-geheim", "")
        dbinit.save_password_entry("bank.de", "yanic", "iban-geheim", "")
        app._tresor()
        app.update()
        assert len(app.tree.get_children()) == 2

        app.suche.set("git")
        app.update()
        assert len(app.tree.get_children()) == 1

        app.suche.set("")
        app.verbergen.set(True)
        app._refresh()
        app.update()
        for zeile in app.tree.get_children():
            werte = app.tree.item(zeile, "values")
            assert "geheim" not in " ".join(werte)
            assert "••••••••" in werte
    finally:
        app.destroy()
        dbinit.lock()


def test_sperren_zeigt_wieder_login():
    _skip_wenn_kein_tk()
    app, pfad = _app()
    try:
        dbinit.init_db(path=pfad, master_password=MASTER)
        dbinit.save_password_entry("github.com", "yanic", "gh", "")
        app._tresor()
        app.update()

        app._sperren()
        app.update()
        assert not dbinit.is_unlocked()
        assert not hasattr(app, "tree") or app.tree.winfo_exists() == 0
        assert any(w.winfo_class() == "TEntry" for w in app.rahmen.winfo_children())
    finally:
        app.destroy()
        dbinit.lock()


if __name__ == "__main__":
    fehler = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as exc:  # noqa: BLE001
                fehler += 1
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    raise SystemExit(1 if fehler else 0)
