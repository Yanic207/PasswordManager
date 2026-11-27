#!/usr/bin/env python3
"""Grafische Oberfläche für den Passwort-Tresor.

Startet ohne Terminal-Fenster:  Doppelklick auf "Passwortmanager.command"
oder:                          .venv/bin/python gui.py

Nutzt dieselbe verschlüsselte Datei (database.vault) wie cli.py / show.py.
"""

import os
import tkinter as tk
from tkinter import messagebox, ttk

from models import dbinit
from models.crypto import InvalidPassword

MIN_MASTER_LEN = 8
TITEL = "Passwort-Manager"
SPALTEN = (
    ("url", "URL", 250),
    ("username", "Benutzername", 170),
    ("password", "Passwort", 190),
    ("note", "Notiz", 240),
)


class App(tk.Tk):
    def __init__(self, pfad=None):
        super().__init__()
        if pfad:
            dbinit.VAULT_PATH = pfad
        self.title(TITEL)
        self.geometry("1000x640")
        self.minsize(820, 520)
        self.protocol("WM_DELETE_WINDOW", self._beenden)

        self.rahmen = ttk.Frame(self, padding=16)
        self.rahmen.pack(fill="both", expand=True)

        self._start()

    # -- Bildschirme ---------------------------------------------------------
    def _leeren(self):
        for kind in self.rahmen.winfo_children():
            kind.destroy()

    def _start(self):
        """Entscheidet: Master-Passwort anlegen oder Tresor entsperren."""
        self._leeren()
        if os.path.exists(dbinit.VAULT_PATH):
            self._login()
        else:
            self._neues_master_passwort()

    def _login(self):
        ttk.Label(self.rahmen, text=TITEL, font=("Helvetica", 22, "bold")).pack(pady=(40, 6))
        ttk.Label(self.rahmen, text="Master-Passwort eingeben").pack(pady=(0, 14))

        pw = tk.StringVar()
        feld = ttk.Entry(self.rahmen, textvariable=pw, show="*", width=32, font=("Helvetica", 14))
        feld.pack(pady=6)
        feld.focus_set()

        fehler = tk.StringVar()
        ttk.Label(self.rahmen, textvariable=fehler, foreground="#c0392b").pack(pady=(0, 8))

        def versuchen(_ereignis=None):
            if not pw.get():
                return
            try:
                dbinit.unlock(pw.get())
            except InvalidPassword as exc:
                fehler.set(str(exc))
                pw.set("")
                feld.focus_set()
                return
            except Exception as exc:  # noqa: BLE001 - Datei kaputt o. ä.
                messagebox.showerror(TITEL, str(exc), parent=self)
                return
            self._tresor()

        feld.bind("<Return>", versuchen)
        ttk.Button(self.rahmen, text="Entsperren", command=versuchen).pack(pady=8)

    def _neues_master_passwort(self):
        ttk.Label(self.rahmen, text="Willkommen!", font=("Helvetica", 22, "bold")).pack(pady=(40, 6))
        ttk.Label(
            self.rahmen,
            text="Es wird ein neuer Tresor angelegt.\nLege dazu ein Master-Passwort fest.",
            justify="center",
        ).pack(pady=(0, 4))
        ttk.Label(
            self.rahmen,
            text="Wichtig: ohne dieses Passwort kommt niemand mehr an die Daten.",
            foreground="#c0392b",
        ).pack(pady=(0, 14))

        pw1, pw2 = tk.StringVar(), tk.StringVar()
        for beschriftung, var in (("Master-Passwort", pw1), ("Wiederholen", pw2)):
            zeile = ttk.Frame(self.rahmen)
            zeile.pack(pady=4)
            ttk.Label(zeile, text=beschriftung, width=16, anchor="e").pack(side="left", padx=(0, 8))
            ttk.Entry(zeile, textvariable=var, show="*", width=28, font=("Helvetica", 13)).pack(side="left")

        fehler = tk.StringVar()
        ttk.Label(self.rahmen, textvariable=fehler, foreground="#c0392b").pack(pady=(6, 6))

        def anlegen():
            if len(pw1.get()) < MIN_MASTER_LEN:
                fehler.set(f"Bitte mindestens {MIN_MASTER_LEN} Zeichen.")
                return
            if pw1.get() != pw2.get():
                fehler.set("Die Passwörter stimmen nicht überein.")
                return
            try:
                dbinit.init_db(master_password=pw1.get())
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror(TITEL, str(exc), parent=self)
                return
            self._tresor()

        ttk.Button(self.rahmen, text="Tresor anlegen", command=anlegen).pack(pady=10)

    # -- Tresor --------------------------------------------------------------
    def _tresor(self):
        self._leeren()

        oben = ttk.Frame(self.rahmen)
        oben.pack(fill="x")
        ttk.Label(oben, text="Suchen:").pack(side="left")
        self.suche = tk.StringVar()
        self.suche.trace_add("write", lambda *_: self._refresh())
        suchfeld = ttk.Entry(oben, textvariable=self.suche, width=28)
        suchfeld.pack(side="left", padx=(6, 12))

        self.verbergen = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            oben, text="Passwörter verbergen", variable=self.verbergen, command=self._refresh
        ).pack(side="left")

        ttk.Button(oben, text="Sperren", command=self._sperren).pack(side="right")
        self.anzahl = tk.StringVar()
        ttk.Label(oben, textvariable=self.anzahl).pack(side="right", padx=12)

        tabelle = ttk.Frame(self.rahmen)
        tabelle.pack(fill="both", expand=True, pady=(10, 0))
        self.tree = ttk.Treeview(
            tabelle, columns=[s[0] for s in SPALTEN], show="headings", selectmode="browse"
        )
        for name, titel, breite in SPALTEN:
            self.tree.heading(name, text=titel)
            self.tree.column(name, width=breite, anchor="w")
        scroll = ttk.Scrollbar(tabelle, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._auswahl_geladen)

        form = ttk.LabelFrame(self.rahmen, text="Eintrag bearbeiten / neu anlegen", padding=10)
        form.pack(fill="x", pady=(12, 0))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self.felder = {name: tk.StringVar() for name in ("url", "username", "password", "note")}
        positionen = (("url", "URL", 0, 0), ("username", "Benutzername", 0, 2),
                      ("password", "Passwort", 1, 0), ("note", "Notiz", 1, 2))
        for name, titel, zeile, spalte in positionen:
            ttk.Label(form, text=titel).grid(row=zeile, column=spalte, sticky="e", padx=(0, 6), pady=4)
            ttk.Entry(form, textvariable=self.felder[name]).grid(
                row=zeile, column=spalte + 1, sticky="ew", padx=(0, 16), pady=4
            )

        knoepfe = ttk.Frame(form)
        knoepfe.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(knoepfe, text="Speichern", command=self._speichern).pack(side="left")
        ttk.Button(knoepfe, text="Neuer Eintrag", command=self._form_leeren).pack(side="left", padx=6)
        ttk.Button(knoepfe, text="Löschen", command=self._loeschen).pack(side="left")
        ttk.Button(knoepfe, text="Passwort kopieren", command=self._kopieren).pack(side="left", padx=6)

        self.status = tk.StringVar()
        ttk.Label(self.rahmen, textvariable=self.status, foreground="#27ae60").pack(anchor="w", pady=(8, 0))

        self._refresh()
        suchfeld.focus_set()

    # -- Tabelle -------------------------------------------------------------
    def _refresh(self):
        for zeile in self.tree.get_children():
            self.tree.delete(zeile)
        suche = self.suche.get().strip().lower()
        treffer = 0
        for eintrag in dbinit.list_all_passwords():
            werte = [eintrag["url"], eintrag["username"] or "", eintrag["password"], eintrag["note"] or ""]
            if suche and not any(suche in w.lower() for w in werte):
                continue
            if self.verbergen.get():
                werte[2] = "•" * 8
            self.tree.insert("", "end", values=werte)
            treffer += 1
        self.anzahl.set(f"{treffer} Eintrag/Einträge")

    def _auswahl_geladen(self, _ereignis=None):
        auswahl = self.tree.selection()
        if not auswahl:
            return
        url, benutzer, _pw, notiz = self.tree.item(auswahl[0], "values")
        self.felder["url"].set(url)
        self.felder["username"].set(benutzer)
        self.felder["note"].set(notiz)
        eintrag = dbinit.search_password_by_url(url)
        if eintrag:
            self.felder["password"].set(eintrag[0]["password"])

    # -- Aktionen ------------------------------------------------------------
    def _speichern(self):
        url = self.felder["url"].get().strip()
        if not url:
            messagebox.showwarning(TITEL, "Bitte eine URL eingeben.", parent=self)
            return
        dbinit.save_password_entry(
            url,
            self.felder["username"].get().strip(),
            self.felder["password"].get(),
            self.felder["note"].get().strip(),
        )
        self.status.set(f"Gespeichert: {url}")
        self._refresh()
        self._form_leeren(behalte_status=True)

    def _loeschen(self):
        auswahl = self.tree.selection()
        url = self.felder["url"].get().strip()
        if not auswahl and not url:
            messagebox.showinfo(TITEL, "Bitte zuerst einen Eintrag auswählen.", parent=self)
            return
        url = url or self.tree.item(auswahl[0], "values")[0]
        if not messagebox.askyesno(TITEL, f"'{url}' wirklich löschen?", parent=self):
            return
        dbinit.delete_password_entry(url)
        self.status.set(f"Gelöscht: {url}")
        self._form_leeren(behalte_status=True)
        self._refresh()

    def _kopieren(self):
        auswahl = self.tree.selection()
        if not auswahl:
            messagebox.showinfo(TITEL, "Bitte zuerst einen Eintrag auswählen.", parent=self)
            return
        url = self.tree.item(auswahl[0], "values")[0]
        eintrag = dbinit.search_password_by_url(url)
        if not eintrag:
            return
        self.clipboard_clear()
        self.clipboard_append(eintrag[0]["password"])
        self.status.set(f"Passwort von {url} in der Zwischenablage")

    def _form_leeren(self, behalte_status=False):
        for var in self.felder.values():
            var.set("")
        if not behalte_status:
            self.status.set("")
        if self.tree.selection():
            self.tree.selection_remove(self.tree.selection())

    # -- Sperren / Beenden ---------------------------------------------------
    def _sperren(self):
        dbinit.lock()
        self._start()

    def _beenden(self):
        dbinit.lock()
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
