#!/bin/bash
# VolleyStat — Script di installazione per Ubuntu/Linux
# Esegui con: bash install.sh

set -e
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   VolleyStat — Installazione         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Controlla Python3
if ! command -v python3 &>/dev/null; then
  echo "❌ Python3 non trovato."
  echo "   Installa con: sudo apt install python3 python3-venv"
  exit 1
fi
echo "✓ Python3: $(python3 --version)"

# Controlla che il modulo venv sia disponibile
if ! python3 -m venv --help &>/dev/null; then
  echo "📦 Installo python3-venv..."
  sudo apt-get install -y python3-venv python3-pip python3-full
fi

# Controlla che ensurepip sia disponibile (manca su alcune distro)
if ! python3 -m ensurepip --version &>/dev/null 2>&1; then
  echo "📦 Installo python3-pip (necessario per il venv)..."
  sudo apt-get install -y python3-pip python3-full 2>/dev/null || true
fi

# Crea ambiente virtuale nella cartella .venv
if [ ! -d ".venv" ]; then
  echo "📦 Creo ambiente virtuale (.venv)..."
  python3 -m venv .venv
else
  echo "✓ Ambiente virtuale già presente"
fi

# Verifica che pip funzioni nel venv, altrimenti ricrea
if ! .venv/bin/pip --version &>/dev/null 2>&1; then
  echo "⚠ pip non funziona nel venv, lo ricreo..."
  rm -rf .venv
  python3 -m venv .venv
fi

# Installa Flask nell'ambiente virtuale
echo "📦 Installo Flask..."
.venv/bin/pip install --quiet flask

echo ""
echo "✅ Installazione completata!"
echo ""
echo "Per avviare VolleyStat:"
echo "   bash run.sh"
echo ""
