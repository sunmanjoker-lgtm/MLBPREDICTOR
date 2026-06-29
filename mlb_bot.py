import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import re

TOKEN = '8917243606:AAHojdm5VMfKCasorA05zVtVphYXyNb4n5k'
CHAT_ID = 328619258

def send_message(text):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    params = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    return requests.post(url, json=params).json()

def send_large_message(text):
    max_len = 4000
    if len(text) <= max_len:
        send_message(text)
        return
    parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for part in parts:
        send_message(part)
        time.sleep(0.5)

# ======= 1. ПОЛУЧЕНИЕ СТАТИСТИКИ КОМАНДЫ =======
def get_team_stats(team_abbr):
    """Получает статистику команды за сезон с ESPN"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/{team_abbr}/statistics"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        stats = {}
        for stat in data.get('statistics', []):
            stats[stat.get('name')] = stat.get('value')
        return stats
    except:
        return None

# ======= 2. ПОЛУЧЕНИЕ МАТЧЕЙ =======
def get_mlb_games():
    today = datetime.now().strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={today}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return []
        data = response.json()
        games = []
        for event in data.get('events', []):
            status = event.get('status', {}).get('type', {}).get('state', '')
            if status == 'postponed':
                continue
            comp = event.get('competitions', [{}])[0]
            competitors = comp.get('competitors', [])
            if len(competitors) < 2:
                continue
            home = competitors[0]['team']
            away = competitors[1]['team']
            start_date = event.get('date')
            if start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                hours_until = (start_dt - datetime.now(timezone.utc)).total_seconds() / 3600
                if hours_until < -2:
                    continue
            else:
                hours_until = 6
            
            # Получаем статистику команд
            home_stats = get_team_stats(home['abbreviation']) or {}
            away_stats = get_team_stats(away['abbreviation']) or {}
            
            games.append({
                'home': home['displayName'],
                'away': away['displayName'],
                'home_abbr': home['abbreviation'],
                'away_abbr': away['abbreviation'],
                'hours_until': hours_until,
                'status': '🔴 LIVE' if status == 'in' else '⏳ Ожидается',
                'home_win_pct': home_stats.get('winPercent', 0.500),
                'away_win_pct': away_stats.get('winPercent', 0.500),
                'home_era': home_stats.get('era', 4.00),
                'away_era': away_stats.get('era', 4.00),
                'home_avg': home_stats.get('avg', 0.250),
                'away_avg': away_stats.get('avg', 0.250),
                'home_runs': home_stats.get('runs', 400),
                'away_runs': away_stats.get('runs', 400),
            })
        return games
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

# ======= 3. ПРОГНОЗ =======
def make_prediction(game):
    home_win_pct = game.get('home_win_pct', 0.500)
    away_win_pct = game.get('away_win_pct', 0.500)
    home_era = game.get('home_era', 4.00)
    away_era = game.get('away_era', 4.00)
    home_avg = game.get('home_avg', 0.250)
    away_avg = game.get('away_avg', 0.250)
    
    # Считаем силу команды
    home_strength = (home_win_pct * 0.4) + (1 - (home_era / 5) * 0.3) + (home_avg * 0.3)
    away_strength = (away_win_pct * 0.4) + (1 - (away_era / 5) * 0.3) + (away_avg * 0.3)
    
    # Домашнее преимущество (+5%)
    prob_home = home_strength / (home_strength + away_strength) + 0.05
    prob_home = max(0.30, min(0.70, prob_home))
    
    if prob_home > 0.55:
        return 'ставка на хозяев', prob_home, 'высокая'
    elif prob_home < 0.45:
        return 'ставка на гостей', prob_home, 'высокая'
    else:
        return 'пропустить', prob_home, 'низкая'

# ======= 4. ОСНОВНАЯ ЛОГИКА =======
print("🔍 Поиск матчей MLB...")
games = get_mlb_games()

if not games:
    send_message('⚾ Сегодня матчей MLB не найдено.')
    exit()

# Сортируем по времени
games.sort(key=lambda x: x['hours_until'])

predictions = []
for game in games:
    home = game['home']
    away = game['away']
    hours = game['hours_until']
    status = game.get('status', '⏳')
    
    win_rec, prob, confidence = make_prediction(game)
    
    if hours > 0:
        time_text = f"через {hours:.1f} ч"
    else:
        time_text = "начался"
    
    pred_text = (
        f"{status} {home} vs {away}\n"
        f"  ⏰ {time_text}\n"
        f"  📊 {win_rec} ({prob:.0%}, уверенность {confidence})"
    )
    predictions.append(pred_text)

msg = "⚾ ПРОГНОЗЫ MLB НА СЕГОДНЯ\n" + "="*30 + "\n\n" + "\n\n".join(predictions[:20])
send_large_message(msg)
print("✅ Прогнозы отправлены")
