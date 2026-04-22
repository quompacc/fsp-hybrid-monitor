#!/bin/bash
# EMS Dashboard sauber starten

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/dashboard"

# Alle alten Prozesse killen
pkill -9 -f "app.py" 2>/dev/null
pkill -9 -f "python.*app" 2>/dev/null
fuser -k 5000/tcp 2>/dev/null

sleep 2

# Starten
if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
  source "$SCRIPT_DIR/venv/bin/activate"
elif [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

python app.py
