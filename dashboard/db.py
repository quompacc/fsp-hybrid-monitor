"""
SQLite Datenbankmodul für EMS
"""
import sqlite3
import os
from datetime import datetime
from config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS inverter_data (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        DATETIME DEFAULT CURRENT_TIMESTAMP,
            solar1_v  REAL, solar2_v  REAL,
            solar1_a  REAL, solar2_a  REAL,
            batt_v    REAL, batt_pct  INTEGER, batt_a REAL,
            ac_in_v_r REAL, ac_in_v_s REAL, ac_in_v_t REAL,
            ac_in_hz  REAL,
            ac_out_v_r REAL, ac_out_v_s REAL, ac_out_v_t REAL,
            ac_out_hz  REAL,
            temp_inner INTEGER, temp_max INTEGER,
            mode TEXT
        );

        CREATE TABLE IF NOT EXISTS sdm630_data (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         DATETIME DEFAULT CURRENT_TIMESTAMP,
            l1_v REAL, l2_v REAL, l3_v REAL,
            l1_a REAL, l2_a REAL, l3_a REAL,
            l1_w REAL, l2_w REAL, l3_w REAL,
            total_w    REAL, freq REAL,
            import_kwh REAL, export_kwh REAL
        );

        CREATE TABLE IF NOT EXISTS pylontech_data (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
            module_count INTEGER,
            avg_soc      REAL,
            avg_v        REAL,
            total_a      REAL,
            modules_json TEXT
        );

        CREATE TABLE IF NOT EXISTS weather_data (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         DATETIME DEFAULT CURRENT_TIMESTAMP,
            today_sun  REAL,
            tomorrow_sun REAL,
            temp_max   REAL,
            description TEXT,
            raw_json   TEXT
        );

        CREATE TABLE IF NOT EXISTS control_log (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      DATETIME DEFAULT CURRENT_TIMESTAMP,
            action  TEXT,
            command TEXT,
            result  TEXT,
            source  TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_inverter_ts  ON inverter_data(ts);
        CREATE INDEX IF NOT EXISTS idx_sdm630_ts    ON sdm630_data(ts);
        CREATE INDEX IF NOT EXISTS idx_pylontech_ts ON pylontech_data(ts);
    ''')
    conn.commit()
    conn.close()

def insert_inverter(d):
    conn = get_db()
    conn.execute('''INSERT INTO inverter_data
        (solar1_v,solar2_v,solar1_a,solar2_a,batt_v,batt_pct,batt_a,
         ac_in_v_r,ac_in_v_s,ac_in_v_t,ac_in_hz,
         ac_out_v_r,ac_out_v_s,ac_out_v_t,ac_out_hz,
         temp_inner,temp_max,mode)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (d.get('solar_input_voltage_1'), d.get('solar_input_voltage_2'),
         d.get('solar_input_current_1'), d.get('solar_input_current_2'),
         d.get('battery_voltage'), d.get('battery_capacity'), d.get('battery_current'),
         d.get('ac_input_voltage_r'), d.get('ac_input_voltage_s'), d.get('ac_input_voltage_t'),
         d.get('ac_input_frequency'),
         d.get('ac_output_voltage_r'), d.get('ac_output_voltage_s'), d.get('ac_output_voltage_t'),
         d.get('ac_output_frequency'),
         d.get('inner_temperature'), d.get('component_max_temperature'),
         d.get('working_mode', '')))
    conn.commit()
    conn.close()

def insert_sdm630(d):
    conn = get_db()
    conn.execute('''INSERT INTO sdm630_data
        (l1_v,l2_v,l3_v,l1_a,l2_a,l3_a,l1_w,l2_w,l3_w,total_w,freq,import_kwh,export_kwh)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (d.get('L1 Spannung'), d.get('L2 Spannung'), d.get('L3 Spannung'),
         d.get('L1 Strom'), d.get('L2 Strom'), d.get('L3 Strom'),
         d.get('L1 Wirkleistung'), d.get('L2 Wirkleistung'), d.get('L3 Wirkleistung'),
         d.get('Gesamt Aktivleistung'), d.get('Frequenz'),
         d.get('Import Energie'), d.get('Export Energie')))
    conn.commit()
    conn.close()

def insert_pylontech(d):
    import json
    conn = get_db()
    conn.execute('''INSERT INTO pylontech_data
        (module_count,avg_soc,avg_v,total_a,modules_json)
        VALUES (?,?,?,?,?)''',
        (d.get('module_count'), d.get('avg_soc'),
         d.get('avg_voltage_v'), d.get('total_current_a'),
         json.dumps(d.get('modules', []))))
    conn.commit()
    conn.close()

def get_latest(table, n=1):
    conn = get_db()
    rows = conn.execute(
        f'SELECT * FROM {table} ORDER BY ts DESC LIMIT ?', (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_history(table, hours=24):
    conn = get_db()
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE ts > datetime('now', '-{hours} hours') ORDER BY ts ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def log_control(action, command, result, source='manual'):
    conn = get_db()
    conn.execute('INSERT INTO control_log (action,command,result,source) VALUES (?,?,?,?)',
                 (action, command, result, source))
    conn.commit()
    conn.close()
