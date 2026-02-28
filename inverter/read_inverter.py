#!/usr/bin/env python3
"""
FSP 15kW 3-Phasen Wechselrichter - USB HID Kommunikation
Protokoll: PI17INFINI (InfiniSolar OEM)
Hardware:  Cypress USB 0665:5161 → /dev/hidraw0
"""

import subprocess
import json
import sys
from datetime import datetime

DEVICE   = "/dev/hidraw0"
PROTOCOL = "PI17INFINI"

COMMANDS = {
    "GS":   "General Status (Spannung, Strom, Frequenz, Temp)",
    "PIRI": "Rated Information (Nennwerte)",
    "MOD":  "Working Mode",
    "ID":   "Serial Number",
    "PI":   "Protocol Version",
    "VFW":  "Firmware Version",
    "WS":   "Warning Status",
    "FLAG": "Flag Status",
}

def run_command(cmd: str) -> dict:
    result = subprocess.run(
        ["mpp-solar", "-p", DEVICE, "-P", PROTOCOL, "-c", cmd, "-o", "json"],
        capture_output=True, text=True, timeout=15
    )
    # mpp-solar gibt raw_response + JSON gemischt aus → nur letzten JSON-Block nehmen
    output = result.stdout.strip()
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return {"error": result.stderr.strip() or "Kein JSON in Antwort", "raw": output}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "GS"

    if cmd == "all":
        print(f"=== FSP 15kW Status ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
        all_data = {}
        for c, desc in COMMANDS.items():
            print(f"--- {c}: {desc} ---")
            data = run_command(c)
            # _command und _command_description rausfiltern
            clean = {k: v for k, v in data.items() if not k.startswith("_") and k != "raw_response"}
            for key, val in clean.items():
                print(f"  {key}: {val}")
            all_data[c] = clean
            print()
        return all_data
    else:
        data = run_command(cmd)
        clean = {k: v for k, v in data.items() if not k.startswith("_") and k != "raw_response"}
        print(json.dumps(clean, indent=2, ensure_ascii=False))
        return clean

if __name__ == "__main__":
    main()
