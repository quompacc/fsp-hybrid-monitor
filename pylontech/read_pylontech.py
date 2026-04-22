#!/usr/bin/env python3
"""
Pylontech US2000C - Console Port
115200 Baud, /dev/pylontech
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

def parse_bat_soh(raw):
    """State of Health aus bat Ausgabe berechnen - Coulomb / SOC × 100 / 50000 mAh Nenn"""
    NOMINAL_MAH = 50000  # US2000C Nennkapazität pro Zelle = 50 Ah
    coulombs = []
    socs     = []
    for line in raw.splitlines():
        # Zeile mit Coulomb: "0  3285  -1014  25600  Dischg  Normal  Normal  Normal  41%  20302 mAH  N"
        m = re.search(r'(\d+)%\s+(\d+)\s+mAH', line)
        if m:
            socs.append(int(m.group(1)))
            coulombs.append(int(m.group(2)))
    if not coulombs or not socs:
        return None
    avg_coulomb = sum(coulombs) / len(coulombs)
    avg_soc     = sum(socs) / len(socs)
    if avg_soc <= 0:
        return None
    # Hochrechnen auf 100% SOC
    full_capacity_mah = avg_coulomb / (avg_soc / 100)
    soh = round(min(100, full_capacity_mah / NOMINAL_MAH * 100), 1)
    return soh

def parse_stat(raw):
    """Ladezyklen und Statistiken aus 'stat N' Ausgabe parsen"""
    result = {}
    for line in raw.splitlines():
        m = re.search(r'Charge Cnt\.\s*:\s*(\d+)', line)
        if m: result['charge_cnt'] = int(m.group(1))
        m = re.search(r'Discharge Cnt\.\s*:\s*(\d+)', line)
        if m: result['discharge_cnt'] = int(m.group(1))
        m = re.search(r'Charge Times\s*:\s*(\d+)', line)
        if m: result['charge_minutes'] = int(m.group(1))
        m = re.search(r'COC Times\s*:\s*(\d+)', line)
        if m: result['coc_times'] = int(m.group(1))
    # Gesamtzyklen = max von Charge/Discharge (je nach aktuellem Zustand ist einer 0)
    charge   = result.get('charge_cnt', 0)
    discharge = result.get('discharge_cnt', 0)
    result['charge_cycles'] = max(charge, discharge)
    return result

def read_fast():
    """Schneller Abruf - nur pwr und bat (ohne stat/SOH) - für 60s Intervall"""
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
        'avg_soh_pct':     None,
    }


def read_all():
    try:
        ser = serial.Serial(port=PORT, baudrate=BAUDRATE,
                            bytesize=8, parity='N', stopbits=1, timeout=2)
        pwr_raw = send_cmd(ser, 'pwr')
        bat_raw = send_cmd(ser, 'bat')

        # SOH pro Modul aus bat N
        soh_data = {}
        for i in range(1, 7):
            raw = send_cmd(ser, f'bat {i}', wait=0.8)
            soh = parse_bat_soh(raw)
            if soh is not None:
                soh_data[i] = soh

        # Stat für alle 6 Module lesen
        stat_data = {}
        for i in range(1, 7):
            raw = send_cmd(ser, f'stat {i}', wait=0.8)
            parsed = parse_stat(raw)
            if parsed:
                stat_data[i] = parsed

        ser.close()
    except serial.SerialException as e:
        print(f"Pylontech Serial Exception: {e}")
        return {}
    except Exception as e:
        print(f"Pylontech error: {e}")
        return {}

    modules = parse_pwr(pwr_raw)
    cells   = parse_bat(bat_raw)

    # Deduplizierung
    seen = set()
    unique = []
    for m in modules:
        if m['module'] not in seen:
            seen.add(m['module'])
            unique.append(m)
    modules = unique

    if not modules:
        return {}

    # Ladezyklen und SOH zu Modulen hinzufügen
    for m in modules:
        idx = m['module']
        m['soh_pct'] = soh_data.get(idx, None)
        if idx in stat_data:
            m['charge_cycles']   = stat_data[idx].get('charge_cycles', 0)
            m['discharge_cycles']= stat_data[idx].get('discharge_cycles', 0)
            m['charge_minutes']  = stat_data[idx].get('charge_minutes', 0)
            m['coc_times']       = stat_data[idx].get('coc_times', 0)
            # Lebensdauer in % (US2000C = 2500 Zyklen)
            cycles = m['charge_cycles']
            m['life_pct'] = round(max(0, 100 - (cycles / 2500 * 100)), 1)
        else:
            m['charge_cycles']    = None
            m['discharge_cycles'] = None
            m['charge_minutes']   = None
            m['coc_times']        = None
            m['life_pct']         = None

    avg_soc       = round(sum(m['soc_pct']   for m in modules) / len(modules), 1)
    total_current = round(sum(m['current_a'] for m in modules), 2)
    avg_voltage   = round(sum(m['voltage_v'] for m in modules) / len(modules), 2)
    avg_cycles    = round(sum(m['charge_cycles'] for m in modules if m['charge_cycles']) / max(1, sum(1 for m in modules if m['charge_cycles'])))
    avg_life      = round(sum(m['life_pct'] for m in modules if m['life_pct'] is not None) / len(modules), 1)
    soh_values    = [m['soh_pct'] for m in modules if m['soh_pct'] is not None]
    avg_soh       = round(sum(soh_values) / len(soh_values), 1) if soh_values else None

    return {
        'modules':         modules,
        'cells':           cells,
        'avg_soc':         avg_soc,
        'avg_voltage_v':   avg_voltage,
        'total_current_a': total_current,
        'module_count':    len(modules),
        'avg_cycles':      avg_cycles,
        'avg_life_pct':    avg_life,
        'avg_soh_pct':     avg_soh,
    }

if __name__ == "__main__":
    print(f"=== Pylontech US2000C ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
    data = read_all()
    if not data:
        print("Keine Daten")
        exit(1)

    print(f"  Module im Stack : {data['module_count']}")
    print(f"  Ø SOC           : {data['avg_soc']}%")
    print(f"  Ø Spannung      : {data['avg_voltage_v']} V")
    print(f"  Gesamtstrom     : {data['total_current_a']} A")
    print(f"  Ø SOH           : {data['avg_soh_pct']}% (State of Health)")
    print()
    print(f"{'Mod':>4} {'Spannung':>10} {'Strom':>8} {'Temp':>8} {'SOC':>6}  {'SOH':>8}  Status")
    print("-" * 65)
    for m in data['modules']:
        soh = f"{m['soh_pct']:.1f}%" if m['soh_pct'] else "–"
        print(f"  {m['module']:2d}  {m['voltage_v']:8.3f}V  "
              f"{m['current_a']:6.3f}A  {m['temp_c']:5.1f}°C  "
              f"{m['soc_pct']:4d}%  {soh:>8}  {m['status']}")
