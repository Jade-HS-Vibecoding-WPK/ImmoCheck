#!/bin/bash
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3 fehlt: https://www.python.org/downloads/"; read -r; exit 1; }
if [ ! -d .venv ]; then
  echo "Erste Einrichtung, das dauert einige Minuten ..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/streamlit run app.py
