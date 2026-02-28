"""
Open-Meteo Wettervorhersage für Painten
Kein API Key nötig
"""
import requests
from config import LATITUDE, LONGITUDE

def get_forecast():
    try:
        url = 'https://api.open-meteo.com/v1/forecast'
        params = {
            'latitude':  LATITUDE,
            'longitude': LONGITUDE,
            'daily': [
                'sunshine_duration',
                'temperature_2m_max',
                'temperature_2m_min',
                'precipitation_sum',
                'weathercode'
            ],
            'hourly': ['shortwave_radiation'],
            'timezone': 'Europe/Berlin',
            'forecast_days': 3
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        daily = data['daily']

        def sun_hours(idx):
            # sunshine_duration ist in Sekunden
            return round(daily['sunshine_duration'][idx] / 3600, 1)

        def wmo_description(code):
            codes = {
                0: 'Sonnig', 1: 'Überwiegend klar', 2: 'Teilweise bewölkt',
                3: 'Bedeckt', 45: 'Neblig', 48: 'Reifnebel',
                51: 'Leichter Nieselregen', 53: 'Nieselregen', 55: 'Starker Nieselregen',
                61: 'Leichter Regen', 63: 'Regen', 65: 'Starker Regen',
                71: 'Leichter Schnee', 73: 'Schnee', 75: 'Starker Schnee',
                80: 'Leichte Schauer', 81: 'Schauer', 82: 'Starke Schauer',
                95: 'Gewitter', 96: 'Gewitter mit Hagel', 99: 'Starkes Gewitter'
            }
            return codes.get(code, f'Code {code}')

        result = {
            'today': {
                'date':        daily['time'][0],
                'sun_hours':   sun_hours(0),
                'temp_max':    daily['temperature_2m_max'][0],
                'temp_min':    daily['temperature_2m_min'][0],
                'precip':      daily['precipitation_sum'][0],
                'description': wmo_description(daily['weathercode'][0]),
                'weathercode': daily['weathercode'][0],
            },
            'tomorrow': {
                'date':        daily['time'][1],
                'sun_hours':   sun_hours(1),
                'temp_max':    daily['temperature_2m_max'][1],
                'temp_min':    daily['temperature_2m_min'][1],
                'precip':      daily['precipitation_sum'][1],
                'description': wmo_description(daily['weathercode'][1]),
                'weathercode': daily['weathercode'][1],
            },
            'day_after': {
                'date':        daily['time'][2],
                'sun_hours':   sun_hours(2),
                'temp_max':    daily['temperature_2m_max'][2],
                'description': wmo_description(daily['weathercode'][2]),
                'weathercode': daily['weathercode'][2],
            }
        }
        return result

    except Exception as e:
        print(f'Wetterfehler: {e}')
        return None

def get_solar_recommendation(forecast, soc):
    """Empfehlung ob AC-Laden sinnvoll ist"""
    if not forecast:
        return 'unknown', 'Keine Wetterdaten verfügbar'

    tomorrow_sun = forecast['tomorrow']['sun_hours']
    today_sun    = forecast['today']['sun_hours']

    from config import SOC_LOW, SOC_HIGH, SUN_HOURS_MIN

    if soc < SOC_LOW:
        return 'charge', f'SOC {soc}% zu niedrig – AC-Laden empfohlen'

    if soc > SOC_HIGH:
        return 'no_charge', f'SOC {soc}% hoch genug – kein AC-Laden nötig'

    if tomorrow_sun >= SUN_HOURS_MIN:
        return 'no_charge', f'Morgen {tomorrow_sun}h Sonne – Solar reicht'

    if tomorrow_sun < SUN_HOURS_MIN and today_sun < SUN_HOURS_MIN:
        return 'charge', f'Heute {today_sun}h, morgen {tomorrow_sun}h Sonne – AC-Laden empfohlen'

    return 'no_charge', f'Morgen {tomorrow_sun}h Sonne – abwarten'
