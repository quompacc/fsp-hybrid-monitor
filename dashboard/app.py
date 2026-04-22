"""
Hybrid Energy Monitor - Flask Web App (Read-Only)
"""
import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, jsonify, request
from db import init_db, get_history
from scheduler import start_scheduler, latest
from mqtt_client import publish_ha_discovery
from config import HOST, PORT, DEBUG

app = Flask(__name__)

# ── Echtzeit ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    rec, reason = latest['recommendation']
    return jsonify({
        'inverter':       latest['inverter'],
        'sdm630':         latest['sdm630'],
        'pylontech':      latest['pylontech'],
        'weather':        latest['weather'],
        'recommendation': {'action': rec, 'reason': reason},
        'last_update':    latest['last_update'],
    })

@app.route('/api/weather')
def api_weather():
    from weather import get_forecast, get_solar_recommendation
    forecast = get_forecast()
    if forecast:
        soc = latest['pylontech'].get('avg_soc', 50)
        rec, reason = get_solar_recommendation(forecast, soc)
        return jsonify({'forecast': forecast, 'recommendation': rec, 'reason': reason})
    return jsonify({'error': 'Keine Wetterdaten'}), 503

@app.route('/api/mqtt/discovery', methods=['POST'])
def api_mqtt_discovery():
    try:
        publish_ha_discovery()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── History / Analytics ───────────────────────────────────────────────────────

def get_time_filter(hours_param):
    """Zeitfilter und strftime Format für einen Zeitraum"""
    if hours_param == 'today':
        return "date(ts, 'localtime') = date('now', 'localtime')", '%Y-%m-%dT%H:%M:00'
    hours = int(hours_param)
    if hours <= 168:
        fmt = '%Y-%m-%dT%H:%M:00'
    elif hours <= 720:
        fmt = '%Y-%m-%dT%H:00:00'
    else:
        fmt = '%Y-%m-%dT00:00:00'
    return f"ts > datetime('now', '-{hours} hours')", fmt


@app.route('/api/analytics/energy')
def api_analytics_energy():
    """Energie-Verlauf: Solar, Hausverbrauch, Netzbezug, Einspeisung, SOC"""
    from db import get_db

    hours_param = request.args.get('hours', 'today')
    time_filter, strftime = get_time_filter(hours_param)

    conn = get_db()

    inv_rows = conn.execute(f"""
        SELECT
            strftime('{strftime}', ts, 'localtime') as t,
            AVG((solar1_v * solar1_a) + (solar2_v * solar2_a)) as solar_w,
            AVG(batt_pct) as soc,
            AVG(batt_v)   as batt_v,
            AVG(batt_a)   as batt_a
        FROM inverter_data
        WHERE {time_filter}
        GROUP BY t ORDER BY t ASC
    """).fetchall()

    sdm_rows = conn.execute(f"""
        SELECT
            strftime('{strftime}', ts, 'localtime') as t,
            AVG(total_w) as net_w
        FROM sdm630_data
        WHERE {time_filter}
          AND l1_v BETWEEN 100 AND 280
          AND ABS(total_w) < 15000
        GROUP BY t ORDER BY t ASC
    """).fetchall()

    conn.close()

    inv_map   = {r['t']: dict(r) for r in inv_rows}
    sdm_map   = {r['t']: dict(r) for r in sdm_rows}
    all_times = sorted(set(list(inv_map.keys()) + list(sdm_map.keys())))

    result = []
    for t in all_times:
        inv    = inv_map.get(t, {})
        sdm    = sdm_map.get(t, {})
        solar  = inv.get('solar_w') or 0
        batt_a = inv.get('batt_a') or 0
        batt_v = inv.get('batt_v') or 49
        net_w  = sdm.get('net_w') or 0
        batt_w = batt_v * batt_a
        bezug  = max(0, net_w)
        einsp  = max(0, -net_w)
        batt_charge_w    = max(0, batt_w)
        batt_discharge_w = max(0, -batt_w)
        # Leistungsbilanz:
        # Haus = PV + Netz(mit Vorzeichen) - Akkuleistung (Akku laden = +W, entladen = -W)
        house = max(0, solar + net_w - batt_w)

        result.append({
            't':             t,
            'solar_w':       round(solar, 1)  if solar  > 0 else 0,
            'house_w':       round(house, 1)  if house  > 0 else 0,
            'bezug_w':       round(bezug, 1)  if bezug  > 5 else 0,
            'einspeisung_w': round(einsp, 1)  if einsp  > 5 else 0,
            'soc':           round(inv['soc'], 1) if inv.get('soc') else None,
            'batt_w':        round(batt_w, 1) if batt_a else 0,
            'batt_charge_w': round(batt_charge_w, 1) if batt_charge_w > 5 else 0,
            'batt_discharge_w': round(batt_discharge_w, 1) if batt_discharge_w > 5 else 0,
            'batt_to_house_w': round(-batt_w, 1) if abs(batt_w) > 5 else 0,
        })

    return jsonify(result)


@app.route('/api/analytics/daily')
def api_analytics_daily():
    """Tages-kWh für die letzten N Tage"""
    from db import get_db

    days = int(request.args.get('days', 30))
    conn = get_db()

    days_rows = conn.execute(f"""
        SELECT DISTINCT date(ts, 'localtime') as day
        FROM sdm630_data
        WHERE ts > datetime('now', '-{days} days')
        ORDER BY day ASC
    """).fetchall()

    sol_rows = conn.execute(f"""
        SELECT
            date(ts, 'localtime') as day,
            MAX(pv_total_energy) - MIN(pv_total_energy) as solar_kwh,
            AVG(batt_pct) as avg_soc
        FROM inverter_data
        WHERE ts > datetime('now', '-{days} days')
          AND pv_total_energy > 0
        GROUP BY day ORDER BY day ASC
    """).fetchall()

    conn.close()

    sol_map = {r['day']: dict(r) for r in sol_rows}
    result  = []

    conn2 = get_db()
    for row in days_rows:
        day = row['day']

        sdm = conn2.execute(f"""
            SELECT
                (SELECT import_kwh FROM sdm630_data
                 WHERE date(ts,'localtime')='{day}' AND import_kwh > 1000
                 ORDER BY ts ASC LIMIT 1) as imp_first,
                (SELECT import_kwh FROM sdm630_data
                 WHERE date(ts,'localtime')='{day}' AND import_kwh > 1000
                 ORDER BY ts DESC LIMIT 1) as imp_last,
                (SELECT export_kwh FROM sdm630_data
                 WHERE date(ts,'localtime')='{day}' AND export_kwh > 1000
                 ORDER BY ts ASC LIMIT 1) as exp_first,
                (SELECT export_kwh FROM sdm630_data
                 WHERE date(ts,'localtime')='{day}' AND export_kwh > 1000
                 ORDER BY ts DESC LIMIT 1) as exp_last
        """).fetchone()

        bez  = max(0, (sdm['imp_last'] or 0) - (sdm['imp_first'] or 0))
        ein  = max(0, (sdm['exp_last'] or 0) - (sdm['exp_first'] or 0))
        sol  = sol_map.get(day, {})
        skwh = max(0, sol.get('solar_kwh') or 0)

        if bez > 150 or ein > 150 or skwh > 150:
            continue

        result.append({
            'day':             day,
            'bezug_kwh':       round(bez,  2),
            'einspeisung_kwh': round(ein,  2),
            'solar_kwh':       round(skwh, 2),
            'avg_soc':         round(sol.get('avg_soc') or 0, 1),
        })

    conn2.close()
    return jsonify(result)


@app.route('/api/analytics/totals')
def api_analytics_totals():
    """Energie-Summen: Heute, Woche, Monat, Jahr"""
    from db import get_db
    conn = get_db()

    def _integrate_kwh(points):
        """
        Integriert eine Zeitreihe [(datetime, watt), ...] zu kWh.
        Nutzt den linken Stützpunkt; große Lücken werden verworfen.
        """
        if len(points) < 2:
            return 0.0
        total_wh = 0.0
        for i in range(len(points) - 1):
            t0, w0 = points[i]
            t1, _ = points[i + 1]
            dt_h = (t1 - t0).total_seconds() / 3600.0
            if dt_h <= 0 or dt_h > 2:
                continue
            total_wh += max(0.0, float(w0 or 0.0)) * dt_h
        return total_wh / 1000.0

    def totals_for(hours, use_today=False):
        if use_today:
            time_filter = "date(ts, 'localtime') = date('now', 'localtime')"
        else:
            time_filter = f"ts > datetime('now', '-{hours} hours')"

        sdm = conn.execute(f"""
            SELECT
                (SELECT import_kwh FROM sdm630_data
                 WHERE {time_filter} AND import_kwh > 1000
                 ORDER BY ts ASC LIMIT 1) as imp_first,
                (SELECT import_kwh FROM sdm630_data
                 WHERE {time_filter} AND import_kwh > 1000
                 ORDER BY ts DESC LIMIT 1) as imp_last,
                (SELECT export_kwh FROM sdm630_data
                 WHERE {time_filter} AND export_kwh > 1000
                 ORDER BY ts ASC LIMIT 1) as exp_first,
                (SELECT export_kwh FROM sdm630_data
                 WHERE {time_filter} AND export_kwh > 1000
                 ORDER BY ts DESC LIMIT 1) as exp_last
        """).fetchone()

        sol = conn.execute(f"""
            SELECT
                (SELECT pv_total_energy FROM inverter_data
                 WHERE {time_filter} AND pv_total_energy > 0
                 ORDER BY ts ASC LIMIT 1) as sol_first,
                (SELECT pv_total_energy FROM inverter_data
                 WHERE {time_filter} AND pv_total_energy > 0
                 ORDER BY ts DESC LIMIT 1) as sol_last,
                SUM((solar1_v * solar1_a + solar2_v * solar2_a) * 15.0 / 3600000.0) as sol_integrated,
                SUM(CASE WHEN batt_a > 0 THEN (COALESCE(batt_v, 0) * batt_a) * 15.0 / 3600000.0 ELSE 0 END) as batt_charge_kwh,
                SUM(CASE WHEN batt_a < 0 THEN (-COALESCE(batt_v, 0) * batt_a) * 15.0 / 3600000.0 ELSE 0 END) as batt_discharge_kwh,
                SUM((COALESCE(batt_v, 0) * COALESCE(batt_a, 0)) * 15.0 / 3600000.0) as batt_net_kwh
            FROM inverter_data WHERE {time_filter}
        """).fetchone()

        inv_power_rows = conn.execute(f"""
            SELECT
                strftime('%Y-%m-%dT%H:%M:00', ts, 'localtime') as t,
                AVG((COALESCE(solar1_v, 0) * COALESCE(solar1_a, 0)) + (COALESCE(solar2_v, 0) * COALESCE(solar2_a, 0))) as solar_w,
                AVG(COALESCE(batt_v, 49) * COALESCE(batt_a, 0)) as batt_w
            FROM inverter_data
            WHERE {time_filter}
            GROUP BY t
            ORDER BY t ASC
        """).fetchall()

        sdm_power_rows = conn.execute(f"""
            SELECT
                strftime('%Y-%m-%dT%H:%M:00', ts, 'localtime') as t,
                AVG(total_w) as net_w
            FROM sdm630_data
            WHERE {time_filter}
              AND l1_v BETWEEN 100 AND 280
              AND ABS(total_w) < 15000
            GROUP BY t
            ORDER BY t ASC
        """).fetchall()

        bez  = max(0, (sdm['imp_last'] or 0) - (sdm['imp_first'] or 0))
        ein  = max(0, (sdm['exp_last'] or 0) - (sdm['exp_first'] or 0))
        et_delta   = max(0, (sol['sol_last'] or 0) - (sol['sol_first'] or 0))
        integrated = max(0, sol['sol_integrated'] or 0)
        skwh  = et_delta if et_delta > 0.5 else integrated
        batt_charge_fallback = max(0, sol['batt_charge_kwh'] or 0)
        batt_discharge_fallback = max(0, sol['batt_discharge_kwh'] or 0)
        batt_net_fallback = sol['batt_net_kwh'] or 0

        # Hausverbrauch robust aus Leistungsbilanz integrieren:
        # house_w = PV + Netz(mit Vorzeichen) - Akkuleistung
        inv_map = {r['t']: dict(r) for r in inv_power_rows}
        sdm_map = {r['t']: dict(r) for r in sdm_power_rows}
        all_times = sorted(set(list(inv_map.keys()) + list(sdm_map.keys())))

        house_points = []
        batt_charge_points = []
        batt_discharge_points = []
        batt_net_points = []

        for t in all_times:
            try:
                dt = datetime.strptime(t, '%Y-%m-%dT%H:%M:00')
            except Exception:
                continue

            inv_row = inv_map.get(t, {})
            sdm_row = sdm_map.get(t, {})
            solar_w = inv_row.get('solar_w') or 0.0
            batt_w = inv_row.get('batt_w') or 0.0
            net_w = sdm_row.get('net_w') or 0.0

            house_w = max(0.0, solar_w + net_w - batt_w)
            house_points.append((dt, house_w))
            batt_charge_points.append((dt, max(0.0, batt_w)))
            batt_discharge_points.append((dt, max(0.0, -batt_w)))
            batt_net_points.append((dt, batt_w))

        house_integrated = _integrate_kwh(house_points)
        batt_charge = _integrate_kwh(batt_charge_points)
        batt_discharge = _integrate_kwh(batt_discharge_points)
        batt_net = 0.0
        if len(batt_net_points) >= 2:
            for i in range(len(batt_net_points) - 1):
                t0, w0 = batt_net_points[i]
                t1, _ = batt_net_points[i + 1]
                dt_h = (t1 - t0).total_seconds() / 3600.0
                if dt_h <= 0 or dt_h > 2:
                    continue
                batt_net += (w0 or 0.0) * dt_h
            batt_net /= 1000.0

        # Fallback nur bei zu wenig Leistungsdaten
        if house_integrated > 0.05:
            house = house_integrated
            house_method = 'power_integrated'
        else:
            house = max(0, skwh + bez - ein - batt_net_fallback)
            batt_charge = batt_charge_fallback
            batt_discharge = batt_discharge_fallback
            batt_net = batt_net_fallback
            house_method = 'balance_fallback'

        autarkie = round(100 * max(0, house - bez) / house, 1) if house > 0 else 0

        return {
            'bezug_kwh':       round(bez,  2),
            'einspeisung_kwh': round(ein,  2),
            'solar_kwh':       round(skwh, 2),
            'house_kwh':       round(house, 2),
            'autarkie_pct':    autarkie,
            'batt_charge_kwh': round(batt_charge, 2),
            'batt_discharge_kwh': round(batt_discharge, 2),
            'batt_net_kwh':    round(batt_net, 2),
            'house_method':    house_method,
        }

    result = {
        'today': totals_for(24,   use_today=True),
        'week':  totals_for(168),
        'month': totals_for(720),
        'year':  totals_for(8760),
    }
    conn.close()
    return jsonify(result)


if __name__ == '__main__':
    init_db()
    scheduler = start_scheduler()
    try:
        publish_ha_discovery()
    except Exception as e:
        print(f'MQTT Discovery Fehler beim Start: {e}')
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
