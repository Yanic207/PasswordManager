#!/bin/bash
# Doppelklick im Finder startet die Oberfläche (ohne Terminal-Tippen).
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo "Die virtuelle Umgebung fehlt. Bitte einmal im Terminal ausführen:"
  echo "  cd \"$(pwd)\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  read -r -p "Enter zum Schließen..." _
  exit 1
fi

if ! .venv/bin/python -c "import tkinter" 2>/dev/null; then
  echo "tkinter fehlt. Bitte einmal ausführen:"
  echo "  brew install python-tk@3.13"
  read -r -p "Enter zum Schließen..." _
  exit 1
fi

exec .venv/bin/python gui.py
