#!/usr/bin/env python3
"""
Pylontech US2000C - Console Port
115200 Baud, /dev/ttyUSB1
"""

import serial, time, re
from datetime import datetime

PORT     = '/dev/pylontech'
BAUDRATE = 115200

def send_cmd(ser, cmd, wait=1.0):
    ser.reset_input_buffer()
    ser.write((cmd + '\r\n').encode())
    time.sleep(wait)
    return ser.read(4096).decode('ascii', errors='replace')

def parse_pwr(raw):
    modules = []
    for line in raw.splitlines():
        m = re.match(r'^\s*(\d+)\s+(\d+)\s+(-?\d+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+\S+\s+(\w+)\s+\S+\s+\S+\s+\S+\s+(\d+)%', line)
        if m:
            modules.append({
                'module':    int(m.group(1)),
                'voltage_v': round(int(m.group(2)) / 1000, 2),
                'current_a': round(int(m.group(3)) / 1000, 2),
                'temp_c':    round(int(m.group(4)) / 1000, 1),
                'status':    m.group(5),
                'soc_pct':   int(m.group(6)),
            })
    return modules

def parse_bat(raw):
    cells = []
    for line in raw.splitlines():
        m = re.match(r'^\s*(\d+)\s+(\d+)\s+(-?\d+)\s+(\d+)\s+(\w+)', line)
        if m:
            cells.append({
                'cell':      int(m.group(1)),
                'voltage_v': round(int(m.group(2)) / 1000, 3),
                'current_a': round(int(m.group(3)) / 1000, 2),
                'temp_c':    round(int(m.group(4)) / 1000, 1),
                'status':    m.group(5),
            })
    return cells

def read_all():
    try:
        ser = serial.Serial(port=PORT, baudrate=BAUDRATE,
                            bytesize=8, parity='N', stopbits=1, timeout=2)
        pwr_raw = send_cmd(ser, 'pwr')
        bat_raw = send_cmd(ser, 'bat')
        ser.close()
    except serial.SerialException as e:
        print(f"Pylontech Serial Exception: {e}")
        return {}
    except Exception as e:
        print(f"Pylontech error: {e}")
        return {}


    modules = parse_pwr(pwr_raw)
    cells   = parse_bat(bat_raw)

    # Deduplizierung - Pylontech gibt Module manchmal doppelt aus
    seen = set()
    unique = []
    for m in modules:
        if m['module'] not in seen:
            seen.add(m['module'])
            unique.append(m)
    modules = unique

    if not modules:
        return {}

    avg_soc       = round(sum(m['soc_pct']   for m in modules) / len(modules), 1)
    total_current = round(sum(m['current_a'] for m in modules), 2)
    avg_voltage   = round(sum(m['voltage_v'] for m in modules) / len(modules), 2)

    return {
        'modules':         modules,
        'cells':           cells,
        'avg_soc':         avg_soc,
        'avg_voltage_v':   avg_voltage,
        'total_current_a': total_current,
        'module_count':    len(modules),
    }

if __name__ == "__main__":
    print(f"=== Pylontech US2000C ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
    data = read_all()

    print(f"  Module im Stack : {data['module_count']}")
    print(f"  Ø SOC           : {data['avg_soc']}%")
    print(f"  Ø Spannung      : {data['avg_voltage_v']} V")
    print(f"  Gesamtstrom     : {data['total_current_a']} A")
    print()

    print(f"{'Mod':>4} {'Spannung':>10} {'Strom':>8} {'Temp':>8} {'SOC':>6}  Status")
    print("-" * 55)
    for m in data['modules']:
        print(f"  {m['module']:2d}  {m['voltage_v']:8.3f}V  "
              f"{m['current_a']:6.3f}A  {m['temp_c']:5.1f}°C  "
              f"{m['soc_pct']:4d}%  {m['status']}")

    if data['cells']:
        print(f"\n  Zellen Modul 1:")
        for c in data['cells']:
            print(f"    Zelle {c['cell']:2d}: {c['voltage_v']:.3f}V  {c['temp_c']:.1f}°C")
