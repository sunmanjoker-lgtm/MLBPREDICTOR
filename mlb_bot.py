import requests
import pandas as pd
import numpy as np
import pickle
import os
import json
from datetime import datetime, timedelta, timezone
import time

TOKEN = '8917243606:AAHojdm5VMfKCasorA05zVtVphYXyNb4n5k'
CHAT_ID = 328619258
DATA_FILE = 'mlb_matches_data.json'

def send_message(text):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    params = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'HTML'}
    return requests.post(url, json=params).json()

def send_large_message(text):
    """Отправляет длинные сообщения по частям"""
    max_len = 4000
    if len(text) <= max_len:
        send_message(text)
        return
    parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for part in parts:
        send_message(part)
        time.sleep(0.5)

# ======= 1. МОДЕЛЬ =======
model_loaded = False
model = None
scaler = None
try:
    with open('mlb_model.pkl', 'rb') as f:
        model = pickle.load(f)
    with open('mlb_scaler.pkl', 'rb') as f:
        scaler = pickle.load(f)
    model_loaded = True
    print("✅ Модель MLB загружена")
except:
    print("⚠️ Модель не загружена — работаем в режиме теста")

# ======= 2. ПОЛУЧЕНИЕ МАТЧЕЙ MLB =======
def get_mlb_games_from_espn():
    """Получает все матчи MLB на сегодня с ESPN"""
    today = datetime.now().strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={today}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"  ESPN ошибка: {response.status_code}")
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
            home = competitors[0]['team']['displayName']
            away = competitors[1]['team']['displayName']
            start_date = event.get('date')
            game_id = event.get('id')
            if start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                hours_until = (start_dt - datetime.now(timezone.utc)).total_seconds() / 3600
                if hours_until < -2:
                    continue
            else:
                start_dt = datetime.now(timezone.utc) + timedelta(hours=6)
                hours_until = 6
            
            # Получаем информацию о питчерах (составы) через ESPN API
            pitchers = get_pitchers_info(game_id) if game_id else {}
            
            games.append({
                'home': home,
                'away': away,
                'game_id': game_id,
                'start_dt': start_dt,
                'hours_until': hours_until,
                'status': '🔴 LIVE' if status == 'in' else '⏳ Ожидается',
                'home_pitcher': pitchers.get('home_pitcher', 'Неизвестно'),
                'away_pitcher': pitchers.get('away_pitcher', 'Неизвестно'),
                'home_era': pitchers.get('home_era', 4.00),
                'away_era': pitchers.get('away_era', 4.00),
            })
        return games
    except Exception as e:
        print(f"  ESPN ошибка: {e}")
        return []

def get_pitchers_info(game_id):
    """Получает информацию о стартовых питчерах"""
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard/event/{game_id}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return {}
        data = response.json()
        pitchers = {}
        for team in data.get('boxscore', {}).get('players', []):
            if team.get('status', {}).get('description') == 'P':
                if team.get('team', {}).get('homeAway') == 'home':
                    pitchers['home_pitcher'] = team.get('athlete', {}).get('displayName')
                    pitchers['home_era'] = team.get('stats', {}).get('era', 4.00)
                else:
                    pitchers['away_pitcher'] = team.get('athlete', {}).get('displayName')
                    pitchers['away_era'] = team.get('stats', {}).get('era', 4.00)
        return pitchers
    except:
        return {}

# ======= 3. КОРРЕКТИРОВКА ЗА 30 МИНУТ =======
def check_lineups(game):
    """Проверяет составы за 30 минут до игры и корректирует прогноз"""
    now = datetime.now(timezone.utc)
    minutes_until = (game['start_dt'] - now).total_seconds() / 60
    
    # Если до игры меньше 30 минут — проверяем составы
    if 0 <= minutes_until <= 30:
        # Получаем актуальные составы (через API)
        pitchers = get_pitchers_info(game.get('game_id'))
        if pitchers:
            game['home_pitcher'] = pitchers.get('home_pitcher', game.get('home_pitcher', 'Неизвестно'))
            game['away_pitcher'] = pitchers.get('away_pitcher', game.get('away_pitcher', 'Неизвестно'))
            game['home_era'] = pitchers.get('home_era', game.get('home_era', 4.00))
            game['away_era'] = pitchers.get('away_era', game.get('away_era', 4.00))
            return True
    return False

# ======= 4. ФОРМИРОВАНИЕ ПРОГНОЗА =======
def make_prediction(game):
    """Делает прогноз на основе ERA питчеров и других факторов"""
    home = game['home']
    away = game['away']
    home_era = game.get('home_era', 4.00)
    away_era = game.get('away_era', 4.00)
    
    # Преимущество хозяев на основе ERA
    era_diff = away_era - home_era
    
    # Базовая вероятность (домашнее преимущество ~54%)
    prob_home = 0.54 + (era_diff * 0.02)
    prob_home = max(0.3, min(0.7, prob_home))
    
    if prob_home > 0.60:
        return 'ставка на хозяев', prob_home
    elif prob_home < 0.40:
        return 'ставка на гостей', prob_home
    else:
        return 'пропустить', prob_home

# ======= 5. ОСНОВНАЯ ЛОГИКА =======
print("🔍 Поиск матчей MLB...")
games = get_mlb_games_from_espn()

if not games:
    send_message('⚾ Сегодня матчей MLB не найдено.')
    exit()

# Проверяем составы для всех матчей
for game in games:
    check_lineups(game)

# Сортируем по времени
games.sort(key=lambda x: x['hours_until'])

# Формируем прогнозы
predictions = []
for game in games:
    home = game['home']
    away = game['away']
    hours = game['hours_until']
    status = game.get('status', '⏳')
    home_pitcher = game.get('home_pitcher', 'Неизвестно')
    away_pitcher = game.get('away_pitcher', 'Неизвестно')
    home_era = game.get('home_era', 4.00)
    away_era = game.get('away_era', 4.00)
    
    win_rec, prob = make_prediction(game)
    
    # Определяем, есть ли корректировка составов
    lineup_note = ""
    if check_lineups(game):
        lineup_note = " ✅ Составы проверены"
    
    if hours > 0:
        time_text = f"через {hours:.1f} ч"
    else:
        time_text = "начался"
    
    pred_text = (
        f"{status} {home} vs {away}{lineup_note}\n"
        f"  ⏰ {time_text}\n"
        f"  ⚾ Питчеры: {home_pitcher} (ERA {home_era:.2f}) vs {away_pitcher} (ERA {away_era:.2f})\n"
        f"  📊 {win_rec} ({prob:.0%})"
    )
    predictions.append(pred_text)

msg = "⚾ ПРОГНОЗЫ MLB НА СЕГОДНЯ\n" + "="*30 + "\n\n" + "\n\n".join(predictions)
send_large_message(msg)
print("✅ Прогнозы отправлены")
