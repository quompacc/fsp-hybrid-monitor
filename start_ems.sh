#!/bin/bash
# EMS Dashboard sauber starten

cd /home/eduard/ems/dashboard

# Alle alten Prozesse killen
pkill -9 -f "app.py" 2>/dev/null
pkill -9 -f "python.*app" 2>/dev/null
fuser -k 5000/tcp 2>/dev/null

sleep 2

# Starten
source /home/eduard/ems/venv/bin/activate
python app.py
