import requests
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime, timedelta, timezone

TOKEN = '8917243606:AAHojdm5VMfKCasorA05zVtVphYXyNb4n5k'
CHAT_ID = 328619258

def send_message(text):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    params = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    return requests.post(url, json=params).json()

# ======= 1. ПОЛУЧЕНИЕ МАТЧЕЙ MLB =======
def get_mlb_matches():
    """Получает матчи MLB на сегодня с ESPN"""
    today = datetime.now().strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={today}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return []
        data = response.json()
        matches = []
        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {}).get('state', '')
            if status == 'postponed':
                continue
            comp = event.get('competitions', [{}])[0]
            competitors = comp.get('competitors', [])
            if len(competitors) < 2:
                continue
            home = competitors[0]['team']['displayName']
            away = competitors[1]['team']['displayName']
            start_date = event.get('date')
            if start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                hours_until = (start_dt - datetime.now(timezone.utc)).total_seconds() / 3600
                if hours_until < 0 or hours_until > 12:
                    continue
            else:
                hours_until = 6
            matches.append({
                'home': home,
                'away': away,
                'league': 'MLB',
                'hours_until': hours_until,
                'status': '🔴 LIVE' if status == 'in' else '⏳'
            })
        return matches
    except Exception as e:
        print(f"  ESPN ошибка: {e}")
        return []

# ======= 2. ФОРМИРОВАНИЕ ПРОГНОЗА =======
def make_prediction(home, away):
    # Упрощённая логика (позже заменим на модель)
    prob = 0.5 + np.random.uniform(-0.15, 0.15)
    if prob > 0.60:
        return 'ставка на хозяев', prob
    elif prob < 0.40:
        return 'ставка на гостей', prob
    else:
        return 'пропустить', prob

# ======= 3. ОСНОВНАЯ ЛОГИКА =======
print("🔍 Поиск матчей MLB...")
matches = get_mlb_matches()

if not matches:
    send_message('⚾ Сегодня матчей MLB не найдено.')
    exit()

matches.sort(key=lambda x: x['hours_until'])

predictions = []
for match in matches:
    home = match['home']
    away = match['away']
    hours = match['hours_until']
    status = match.get('status', '⏳')
    
    win_rec, prob = make_prediction(home, away)
    
    if hours > 0:
        time_text = f"через {hours:.1f} ч"
    else:
        time_text = "начался"
    
    pred_text = (
        f"{status} {home} vs {away}\n"
        f"  ⏰ {time_text}\n"
        f"  📊 {win_rec} ({prob:.0%})"
    )
    predictions.append(pred_text)

msg = "⚾ ПРОГНОЗЫ MLB НА СЕГОДНЯ\n" + "="*30 + "\n\n" + "\n\n".join(predictions)
send_message(msg)
print("✅ Прогнозы отправлены")
