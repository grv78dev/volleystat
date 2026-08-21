#!/bin/bash
# VolleyStat — Avvia l'applicazione
cd "$(dirname "$0")"

# Controlla che l'installazione sia stata eseguita
if [ ! -d ".venv" ]; then
  echo "⚠ Ambiente virtuale non trovato. Esegui prima: bash install.sh"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   VolleyStat — Avvio...                      ║"
echo "║   Locale:  http://127.0.0.1:8000             ║"
echo "║   Tablet:  vedi IP mostrato all'avvio        ║"
echo "║   Ctrl+C per uscire                          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

.venv/bin/python3 app.py
