"""
Hintergrund-Scheduler für Datenabruf und Automatik
"""
import sys
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(_BASE_DIR, 'inverter'))
sys.path.insert(0, os.path.join(_BASE_DIR, 'sdm630'))
sys.path.insert(0, os.path.join(_BASE_DIR, 'pylontech'))

_mpp_solar_path = os.getenv('MPP_SOLAR_PATH')
if _mpp_solar_path:
    sys.path.insert(0, _mpp_solar_path)

# Shared state
latest = {
    'inverter':       {},
    'sdm630':         {},
    'pylontech':      {},
    'weather':        None,
    'recommendation': ('unknown', 'Noch kein Wetter geladen'),
    'last_update':    {}
}

# SOH Zähler - beim ersten Aufruf und dann jede Stunde (60x60s)
_pylontech_counter = 0

def collect_inverter():
    try:
        import read_inverter
        data     = read_inverter.run_command('GS')
        mod_data = read_inverter.run_command('MOD')
        et_data  = read_inverter.run_command('ET')
        if not data:
            return
        if not data.get('ac_input_voltage_r') and not data.get('battery_voltage'):
            print('Inverter: ungültige Daten, überspringe')
            return
        if mod_data:
            data.update(mod_data)
        if et_data:
            data['pv_total_energy'] = et_data.get('generated_energy_total', 0)

        # SOC Plausibilitätsprüfung - max 5% Sprung pro Messung (alle 15s)
        new_soc  = data.get('battery_capacity')
        last_soc = latest['inverter'].get('battery_capacity')
        if new_soc is not None and last_soc is not None:
            try:
                if abs(int(new_soc) - int(last_soc)) > 5:
                    print(f'Inverter: SOC Sprung {last_soc}% → {new_soc}% → verwerfe')
                    data['battery_capacity'] = last_soc
            except (ValueError, TypeError):
                pass

        latest['inverter'] = data
        from datetime import datetime
        latest['last_update']['inverter'] = datetime.now().isoformat()
        from db import insert_inverter
        insert_inverter(data)
        from mqtt_client import publish_inverter
        publish_inverter(data)
    except Exception as e:
        print(f'Inverter Fehler: {e}')

def collect_sdm630():
    try:
        import read_sdm630
        data = read_sdm630.read_all()
        if not data:
            return
        result = {k: v for k, (v, u) in data.items()}
        pw = result.get('Gesamt Aktivleistung')
        if pw is None:
            return
        latest['sdm630'] = result
        from datetime import datetime
        latest['last_update']['sdm630'] = datetime.now().isoformat()
        from db import insert_sdm630
        insert_sdm630(result)
        from mqtt_client import publish_sdm630
        publish_sdm630(result)
    except Exception as e:
        print(f'SDM630 Fehler: {e}')

def collect_pylontech():
    global _pylontech_counter
    _pylontech_counter += 1
    # Ersten Aufruf und dann jede Stunde vollständig mit SOH
    use_full = (_pylontech_counter == 1 or _pylontech_counter % 60 == 0)
    try:
        import read_pylontech
        data = read_pylontech.read_all() if use_full else read_pylontech.read_fast()
        if not data:
            return
        v   = data.get('avg_voltage_v', 0)
        soc = data.get('avg_soc', 0)
        if not v or float(v) < 40 or float(v) > 60:
            print(f'Pylontech: ungültige Spannung {v}V, überspringe')
            return
        if soc is not None and float(soc) == 0 and data.get('module_count', 0) > 0:
            print('Pylontech: SOC=0 bei aktiven Modulen, überspringe')
            return
        # SOH aus letztem vollständigen Abruf übernehmen wenn nicht neu geladen
        if not use_full and latest['pylontech'].get('avg_soh_pct'):
            data['avg_soh_pct'] = latest['pylontech']['avg_soh_pct']
            for i, m in enumerate(data.get('modules', [])):
                if i < len(latest['pylontech'].get('modules', [])):
                    m['soh_pct'] = latest['pylontech']['modules'][i].get('soh_pct')
        if use_full:
            print(f"Pylontech SOH: {data.get('avg_soh_pct')}%")
        latest['pylontech'] = data
        from datetime import datetime
        latest['last_update']['pylontech'] = datetime.now().isoformat()
        from db import insert_pylontech
        insert_pylontech(data)
        from mqtt_client import publish_pylontech
        publish_pylontech(data)
    except Exception as e:
        print(f'Pylontech Fehler: {e}')

def collect_weather():
    try:
        from weather import get_forecast, get_solar_recommendation
        forecast = get_forecast()
        if forecast:
            latest['weather'] = forecast
            soc = latest['pylontech'].get('avg_soc', 50)
            rec, reason = get_solar_recommendation(forecast, soc)
            latest['recommendation'] = (rec, reason)
            from db import get_db
            conn = get_db()
            conn.execute('''INSERT INTO weather_data
                (today_sun, tomorrow_sun, temp_max, description)
                VALUES (?,?,?,?)''',
                (forecast['today']['sun_hours'],
                 forecast['tomorrow']['sun_hours'],
                 forecast['tomorrow']['temp_max'],
                 forecast['tomorrow']['description']))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f'Wetter Fehler: {e}')

def start_scheduler():
    scheduler = BackgroundScheduler(timezone='Europe/Berlin')

    scheduler.add_job(collect_inverter,  IntervalTrigger(seconds=15), id='inverter',  replace_existing=True)
    scheduler.add_job(collect_sdm630,    IntervalTrigger(seconds=30), id='sdm630',    replace_existing=True)
    scheduler.add_job(collect_pylontech, IntervalTrigger(seconds=60), id='pylontech', replace_existing=True)
    scheduler.add_job(collect_weather,   IntervalTrigger(minutes=30), id='weather',   replace_existing=True)

    scheduler.start()

    import time
    time.sleep(1)

    collect_weather()
    collect_inverter()
    collect_sdm630()
    collect_pylontech()  # Erster Aufruf lädt vollständige Daten inkl. SOH

    return scheduler
