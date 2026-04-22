#!/usr/bin/env python3
"""
SDM630 Stromzähler - RS485 Modbus
Aktives Lesen mit Kollisions-Toleranz und Plausibilitätsprüfung.
Energiezähler werden gegen DB-Werte validiert - keine Sprünge möglich.
"""

import serial
import serial.serialutil
import struct, time, os
from datetime import datetime

PORT     = '/dev/ttyUSB1'
BAUDRATE = 19200
SDM_ADDR = 1

# DB Pfad für Cache-Initialisierung
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'ems.db')

REGISTERS = [
    (0x0000, "L1 Spannung",          "V"),
    (0x0002, "L2 Spannung",          "V"),
    (0x0004, "L3 Spannung",          "V"),
    (0x0006, "L1 Strom",             "A"),
    (0x0008, "L2 Strom",             "A"),
    (0x000A, "L3 Strom",             "A"),
    (0x000C, "L1 Wirkleistung",      "W"),
    (0x000E, "L2 Wirkleistung",      "W"),
    (0x0010, "L3 Wirkleistung",      "W"),
    (0x0034, "Gesamt Aktivleistung", "W"),
    (0x0046, "Frequenz",             "Hz"),
    (0x0048, "Import Energie",       "kWh"),
    (0x004A, "Export Energie",       "kWh"),
    (0x0156, "Gesamt Energie",       "kWh"),
]

# Plausibilitätsgrenzen pro Register
PLAUSIBILITY = {
    "L1 Spannung":          (100,   280),
    "L2 Spannung":          (100,   280),
    "L3 Spannung":          (100,   280),
    "L1 Strom":             (-100,  100),
    "L2 Strom":             (-100,  100),
    "L3 Strom":             (-100,  100),
    "L1 Wirkleistung":      (-15000, 15000),
    "L2 Wirkleistung":      (-15000, 15000),
    "L3 Wirkleistung":      (-15000, 15000),
    "Gesamt Aktivleistung": (-15000, 15000),
    "Frequenz":             (45,    55),
    "Import Energie":       (1000,  25000),   # Import nie > 25000 kWh
    "Export Energie":       (1000,  45000),   # Export nie > 45000 kWh
    "Gesamt Energie":       (1000,  70000),
}

# Letzter bekannter gültiger Wert je Register
_last_good = {}
_cache_initialized = False

def init_cache_from_db():
    """Beim Start letzten bekannten guten Wert aus DB laden"""
    global _cache_initialized
    if _cache_initialized:
        return
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        r = conn.execute("""
            SELECT import_kwh, export_kwh FROM sdm630_data
            WHERE import_kwh > 1000 AND import_kwh < 25000
              AND export_kwh > 1000 AND export_kwh < 45000
            ORDER BY ts DESC LIMIT 1
        """).fetchone()
        if r:
            _last_good['Import Energie'] = (r[0], 'kWh')
            _last_good['Export Energie'] = (r[1], 'kWh')
            print(f'SDM630 Cache: Import={r[0]:.2f}, Export={r[1]:.2f}')
        conn.close()
    except Exception as e:
        print(f'SDM630 Cache-Init Fehler: {e}')
    _cache_initialized = True

def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc

def is_plausible(name, value):
    if name not in PLAUSIBILITY:
        return True
    lo, hi = PLAUSIBILITY[name]
    if not (lo <= value <= hi):
        print(f'SDM630: {name}={value} außerhalb [{lo},{hi}] → verwerfen')
        return False
    # Energiezähler dürfen nur steigen, nie fallen
    if name in ('Import Energie', 'Export Energie', 'Gesamt Energie'):
        last = _last_good.get(name)
        if last and value < last[0] * 0.99:
            print(f'SDM630: {name} fällt ab! {value} < {last[0]} → verwerfen')
            return False
    return True

def read_register(ser, reg):
    req = struct.pack('>BBHH', SDM_ADDR, 4, reg, 2)
    req += struct.pack('<H', crc16(req))
    ser.reset_input_buffer()
    ser.write(req)
    time.sleep(0.15)
    resp = b''
    deadline = time.time() + 0.5
    while len(resp) < 9 and time.time() < deadline:
        chunk = ser.read(9 - len(resp))
        if chunk:
            resp += chunk
    if len(resp) == 9 and resp[1] == 4 and resp[2] == 4:
        if crc16(resp[:7]) == struct.unpack('<H', resp[7:9])[0]:
            return struct.unpack('>f', resp[3:7])[0]
    return None

def read_all():
    init_cache_from_db()
    try:
        ser = serial.Serial(port=PORT, baudrate=BAUDRATE,
                            bytesize=8, parity='N', stopbits=1, timeout=0.5)
        time.sleep(0.2)
        ser.reset_input_buffer()
        results = {}

        for reg, name, unit in REGISTERS:
            try:
                val = read_register(ser, reg)
                if val is not None:
                    val = round(val, 2)
                    if is_plausible(name, val):
                        results[name] = (val, unit)
                        _last_good[name] = (val, unit)
                    elif name in _last_good:
                        results[name] = _last_good[name]
                elif name in _last_good:
                    results[name] = _last_good[name]
            except serial.serialutil.SerialException:
                if name in _last_good:
                    results[name] = _last_good[name]
            time.sleep(0.1)

        ser.close()
        return results

    except serial.serialutil.SerialException:
        if _last_good:
            return dict(_last_good)
        return {}
    except Exception as e:
        print(f'SDM630 Fehler: {e}')
        if _last_good:
            return dict(_last_good)
        return {}

if __name__ == "__main__":
    print(f"=== SDM630 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
    data = read_all()
    if not data:
        print("  Keine Daten")
    else:
        for name, (val, unit) in data.items():
            print(f"  {name:25s} = {val:10.2f} {unit}")
