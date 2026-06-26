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

# ======= 1. ЗАГРУЗКА МОДЕЛИ =======
model_loaded = False
model = None
scaler = None

try:
    # Проверяем наличие файлов модели
    if os.path.exists('mlb_model.pkl') and os.path.exists('mlb_scaler.pkl'):
        with open('mlb_model.pkl', 'rb') as f:
            model = pickle.load(f)
        with open('mlb_scaler.pkl', 'rb') as f:
            scaler = pickle.load(f)
        model_loaded = True
        print("✅ Модель MLB загружена")
    else:
        print("⚠️ Файлы модели не найдены. Используем упрощённую логику.")
except Exception as e:
    print(f"⚠️ Ошибка загрузки модели: {e}")

# ======= 2. ПОЛУЧЕНИЕ МАТЧЕЙ И ПИТЧЕРОВ =======
def get_mlb_games():
    """Получает матчи MLB и информацию о питчерах"""
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
            game_id = event.get('id')
            start_date = event.get('date')
            
            # Получаем питчеров
            pitchers = get_pitchers_info(game_id)
            
            if start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                hours_until = (start_dt - datetime.now(timezone.utc)).total_seconds() / 3600
                if hours_until < -2:
                    continue
            else:
                hours_until = 6
            
            games.append({
                'home': home['displayName'],
                'away': away['displayName'],
                'home_abbr': home['abbreviation'],
                'away_abbr': away['abbreviation'],
                'game_id': game_id,
                'hours_until': hours_until,
                'status': '🔴 LIVE' if status == 'in' else '⏳ Ожидается',
                'home_pitcher': pitchers.get('home_pitcher', 'Неизвестно'),
                'away_pitcher': pitchers.get('away_pitcher', 'Неизвестно'),
                'home_era': pitchers.get('home_era', 4.00),
                'away_era': pitchers.get('away_era', 4.00),
                'home_avg': pitchers.get('home_avg', 0.250),
                'away_avg': pitchers.get('away_avg', 0.250),
                'home_obp': pitchers.get('home_obp', 0.320),
                'away_obp': pitchers.get('away_obp', 0.320),
                'home_slg': pitchers.get('home_slg', 0.400),
                'away_slg': pitchers.get('away_slg', 0.400),
            })
        return games
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

def get_pitchers_info(game_id):
    """Получает информацию о питчерах через ESPN API"""
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard/event/{game_id}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return {}
        
        data = response.json()
        pitchers = {}
        
        # Ищем питчеров в boxscore
        for team in data.get('boxscore', {}).get('players', []):
            for player in team.get('players', []):
                if player.get('status', {}).get('description') == 'P':
                    athlete = player.get('athlete', {})
                    team_home_away = team.get('team', {}).get('homeAway', '')
                    
                    # Получаем статистику питчера
                    stats = player.get('stats', {})
                    era = stats.get('era', 4.00)
                    avg = stats.get('avg', 0.250)
                    obp = stats.get('obp', 0.320)
                    slg = stats.get('slg', 0.400)
                    
                    if team_home_away == 'home':
                        pitchers['home_pitcher'] = athlete.get('displayName', 'Неизвестно')
                        pitchers['home_era'] = era if era else 4.00
                        pitchers['home_avg'] = avg if avg else 0.250
                        pitchers['home_obp'] = obp if obp else 0.320
                        pitchers['home_slg'] = slg if slg else 0.400
                    else:
                        pitchers['away_pitcher'] = athlete.get('displayName', 'Неизвестно')
                        pitchers['away_era'] = era if era else 4.00
                        pitchers['away_avg'] = avg if avg else 0.250
                        pitchers['away_obp'] = obp if obp else 0.320
                        pitchers['away_slg'] = slg if slg else 0.400
        
        return pitchers
    except Exception as e:
        print(f"  Ошибка получения питчеров: {e}")
        return {}

# ======= 3. ПРОГНОЗ =======
def make_prediction(game):
    """Делает прогноз на основе модели или простой логики"""
    home_era = game.get('home_era', 4.00)
    away_era = game.get('away_era', 4.00)
    home_avg = game.get('home_avg', 0.250)
    away_avg = game.get('away_avg', 0.250)
    home_obp = game.get('home_obp', 0.320)
    away_obp = game.get('away_obp', 0.320)
    home_slg = game.get('home_slg', 0.400)
    away_slg = game.get('away_slg', 0.400)
    
    # Если модель загружена — используем её
    if model_loaded and scaler is not None:
        try:
            # Создаём признаки
            features = pd.DataFrame([{
                'home_avg': home_avg,
                'away_avg': away_avg,
                'home_obp': home_obp,
                'away_obp': away_obp,
                'home_slg': home_slg,
                'away_slg': away_slg,
                'home_era': home_era,
                'away_era': away_era,
                'home_win_rate': home_avg / (home_avg + away_avg),
                'away_win_rate': away_avg / (home_avg + away_avg),
                'home_obp_diff': home_obp - away_obp,
                'home_slg_diff': home_slg - away_slg,
                'home_era_diff': away_era - home_era,
                'avg_diff': home_avg - away_avg
            }])
            X_scaled = scaler.transform(features)
            prob_home = model.predict_proba(X_scaled)[0][1]
            
            if prob_home > 0.55:
                return 'ставка на хозяев', prob_home
            elif prob_home < 0.45:
                return 'ставка на гостей', prob_home
            else:
                return 'пропустить', prob_home
        except Exception as e:
            print(f"  Ошибка модели: {e}")
    
    # Упрощённая логика на основе ERA (без модели)
    era_diff = away_era - home_era
    home_advantage = 0.54 + (era_diff * 0.02)
    prob_home = max(0.30, min(0.70, home_advantage))
    
    if prob_home > 0.55:
        return 'ставка на хозяев', prob_home
    elif prob_home < 0.45:
        return 'ставка на гостей', prob_home
    else:
        return 'пропустить', prob_home

# ======= 4. ОСНОВНАЯ ЛОГИКА =======
print("🔍 Поиск матчей MLB...")
games = get_mlb_games()

if not games:
    send_message('⚾ Сегодня матчей MLB не найдено.')
    exit()

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
    
    if hours > 0:
        time_text = f"через {hours:.1f} ч"
    else:
        time_text = "начался"
    
    # Показываем модель, если загружена
    model_note = " 🤖" if model_loaded else ""
    
    pred_text = (
        f"{status}{model_note} {home} vs {away}\n"
        f"  ⏰ {time_text}\n"
        f"  ⚾ {home_pitcher} (ERA {home_era:.2f}) vs {away_pitcher} (ERA {away_era:.2f})\n"
        f"  📊 {win_rec} ({prob:.0%})"
    )
    predictions.append(pred_text)

msg = "⚾ ПРОГНОЗЫ MLB НА СЕГОДНЯ\n" + "="*30 + "\n\n" + "\n\n".join(predictions[:20])
send_message(msg)
print("✅ Прогнозы отправлены")
