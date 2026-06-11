import os
import json
import random
import threading
import time
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError
import requests

# ========== ЗАГЛУШКА ДЛЯ RENDER ==========
app_web = Flask(__name__)

@app_web.route('/')
def hello():
    return "🤖 Бот с музыкой работает!"

@app_web.route('/health')
def health():
    return "OK", 200

@app_web.route('/ping')
def ping():
    return "pong", 200
# ========================================

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
YOUR_USER_ID = 8420827188
# =================================

DATA_FILE = "mood_diary.json"
pending_tracks = {}
pending_rating = {}  # {user_id: {"track_title": "...", "track_file_id": "...", "mood": "..."}}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {},
        "tracks": {"грустный": [], "весёлый": [], "злой": [], "спокойный": [], "влюблённый": [], "уставший": []},
        "ratings": {}  # {track_title: [1,2,3,4,5]}
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_random_track_by_mood(mood: str):
    data = load_data()
    tracks = data["tracks"].get(mood, [])
    if not tracks:
        return None
    return random.choice(tracks)

def add_rating(track_title: str, rating: int):
    data = load_data()
    if track_title not in data["ratings"]:
        data["ratings"][track_title] = []
    data["ratings"][track_title].append(rating)
    save_data(data)

def get_track_rating_stats(track_title: str) -> str:
    data = load_data()
    ratings = data["ratings"].get(track_title, [])
    if not ratings:
        return "⭐ Нет оценок"
    avg = sum(ratings) / len(ratings)
    return f"⭐ Средняя оценка: {avg:.1f}/5 ({len(ratings)} оценок)"

def get_random_caption(mood: str, track_title: str) -> str:
    captions = {
        "грустный": [f"🍂 Под грустинку — {track_title}. Выдохни.", f"😔 Грусть — это нормально. {track_title} — твой саундтрек."],
        "весёлый": [f"🎉 {track_title} — энергия зашкаливает!", f"😄 Этот трек про тебя сегодня! {track_title}"],
        "злой": [f"🤬 Выпусти пар под {track_title}. Громкость на максимум.", f"⚡ Злость — топливо. {track_title} в помощь."],
        "спокойный": [f"😌 {track_title} — музыка для внутреннего равновесия.", f"🌊 Расслабься. {track_title} тебя ждёт."],
        "влюблённый": [f"💘 {track_title} — это про тебя и твои чувства.", f"🌸 Весна в душе? {track_title} подтверждает."],
        "уставший": [f"🛌 {track_title} — ложись и слушай.", f"😴 Устал? {track_title} обнимет звуком."],
        "случайное": [f"🎲 Держи случайный трек: {track_title}", f"🎧 Бот выбрал за тебя — {track_title}"],
    }
    return random.choice(captions.get(mood, captions["случайное"]))

def save_mood_entry(user_id: int, mood: str, track_title: str):
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"entries": []}
    
    data["users"][uid]["entries"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "mood": mood,
        "track_title": track_title
    })
    save_data(data)

def get_stats(user_id: int) -> str:
    data = load_data()
    entries = data["users"].get(str(user_id), {}).get("entries", [])
    if not entries:
        return "📭 Дневник пуст. Нажми /mood"
    
    moods = {}
    for e in entries:
        moods[e["mood"]] = moods.get(e["mood"], 0) + 1
    
    most_common = max(moods, key=moods.get)
    mood_list = ", ".join([f"{k}: {v}" for k, v in moods.items()])
    return f"📊 Записей: {len(entries)}\n❤️ Чаще всего: {most_common} ({moods[most_common]} раз)\n{mood_list}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        await update.message.reply_text("Это личный бот 🙈")
        return
    await update.message.reply_text(
        "🎧 **Твой дневник настроения с музыкой**\n\n"
        "/mood — записать настроение + получить трек\n"
        "/random — случайный трек\n"
        "/addfile — добавить новую песню\n"
        "/stats — статистика дневника\n"
        "/ratings — статистика оценок треков\n"
        "/history — последние записи\n"
        "/library — сколько треков в каждом настроении\n\n"
        "📝 После прослушивания трека — оцени его звёздочками!",
        parse_mode="Markdown"
    )

async def addfile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    keyboard = [
        [InlineKeyboardButton("😢 Грустный", callback_data="addmood_грустный")],
        [InlineKeyboardButton("😄 Весёлый", callback_data="addmood_весёлый")],
        [InlineKeyboardButton("🤬 Злой", callback_data="addmood_злой")],
        [InlineKeyboardButton("😌 Спокойный", callback_data="addmood_спокойный")],
        [InlineKeyboardButton("💘 Влюблённый", callback_data="addmood_влюблённый")],
        [InlineKeyboardButton("🛌 Уставший", callback_data="addmood_уставший")],
    ]
    await update.message.reply_text(
        "🎵 **Добавляем новую песню**\n\nВыбери настроение:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def addmood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != YOUR_USER_ID:
        await query.edit_message_text("Это не твой бот 🙈")
        return
    
    mood = query.data.replace("addmood_", "")
    pending_tracks[query.from_user.id] = mood
    await query.edit_message_text(
        f"✅ Выбрано настроение: **{mood}**\n\n"
        f"📤 Теперь **отправь аудиофайл песни** (mp3, m4a...)\n\n"
        f"Просто отправь файл в этот чат.",
        parse_mode="Markdown"
    )

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    user_id = update.effective_user.id
    if user_id not in pending_tracks:
        await update.message.reply_text("❌ Сначала используй /addfile")
        return
    
    mood = pending_tracks[user_id]
    audio = update.message.audio
    
    if not audio:
        await update.message.reply_text("❌ Это не аудиофайл. Отправь песню как **аудио**.")
        return
    
    title = audio.title or audio.file_name or "Без названия"
    performer = audio.performer or ""
    full_title = f"{performer} - {title}" if performer else title
    
    data = load_data()
    track_info = {
        "file_id": audio.file_id,
        "title": full_title,
        "performer": performer,
        "file_name": audio.file_name
    }
    data["tracks"][mood].append(track_info)
    save_data(data)
    
    del pending_tracks[user_id]
    
    # ПОДТВЕРЖДЕНИЕ - вот то, чего не хватало!
    await update.message.reply_text(
        f"✅ **Песня успешно добавлена!**\n\n"
        f"🎵 {full_title}\n"
        f"😊 Настроение: {mood}\n\n"
        f"Теперь эта песня будет играть, когда ты выберешь «{mood}» в /mood",
        parse_mode="Markdown"
    )

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    keyboard = [
        [InlineKeyboardButton("😢 Грустный", callback_data="mood_грустный")],
        [InlineKeyboardButton("😄 Весёлый", callback_data="mood_весёлый")],
        [InlineKeyboardButton("🤬 Злой", callback_data="mood_злой")],
        [InlineKeyboardButton("😌 Спокойный", callback_data="mood_спокойный")],
        [InlineKeyboardButton("💘 Влюблённый", callback_data="mood_влюблённый")],
        [InlineKeyboardButton("🛌 Уставший", callback_data="mood_уставший")],
    ]
    await update.message.reply_text("Какое у тебя настроение?", reply_markup=InlineKeyboardMarkup(keyboard))

async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != YOUR_USER_ID:
        await query.edit_message_text("Это не твой бот 🙈")
        return
    
    mood = query.data.replace("mood_", "")
    track = get_random_track_by_mood(mood)
    if not track:
        await query.edit_message_text(f"📭 Нет песен для настроения **{mood}**.\n\nДобавь через /addfile", parse_mode="Markdown")
        return
    
    caption = get_random_caption(mood, track["title"])
    save_mood_entry(YOUR_USER_ID, mood, track["title"])
    
    # Сохраняем информацию для оценки
    pending_rating[YOUR_USER_ID] = {
        "track_title": track["title"],
        "track_file_id": track["file_id"],
        "mood": mood
    }
    
    # КНОПКИ ОЦЕНКИ (после отправки музыки)
    rating_keyboard = [
        [
            InlineKeyboardButton("⭐ 1", callback_data=f"rate_1_{track['title']}"),
            InlineKeyboardButton("⭐⭐ 2", callback_data=f"rate_2_{track['title']}"),
            InlineKeyboardButton("⭐⭐⭐ 3", callback_data=f"rate_3_{track['title']}"),
            InlineKeyboardButton("⭐⭐⭐⭐ 4", callback_data=f"rate_4_{track['title']}"),
            InlineKeyboardButton("⭐⭐⭐⭐⭐ 5", callback_data=f"rate_5_{track['title']}")
        ]
    ]
    
    try:
        await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=track["file_id"],
            caption=f"{caption}\n\n🎵 {track['title']}\n\n⭐ **Оцени песню после прослушивания:**",
            performer=track.get("performer", ""),
            title=track.get("title", ""),
            reply_markup=InlineKeyboardMarkup(rating_keyboard)
        )
        await query.message.delete()
    except TelegramError as e:
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != YOUR_USER_ID:
        await query.edit_message_text("Это не твой бот 🙈")
        return
    
    data_parts = query.data.split("_")
    rating = int(data_parts[1])
    track_title = "_".join(data_parts[2:])  # Восстанавливаем название с пробелами
    
    # Сохраняем оценку
    add_rating(track_title, rating)
    
    await query.edit_message_text(
        f"✅ **Оценка сохранена!**\n\n"
        f"🎵 {track_title}\n"
        f"⭐ Твоя оценка: {rating}/5\n\n"
        f"Спасибо! ❤️",
        parse_mode="Markdown"
    )

async def ratings_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    data = load_data()
    if not data["ratings"]:
        await update.message.reply_text("📭 Пока нет оценок. Послушай музыку и оцени через /mood")
        return
    
    # Собираем статистику по трекам
    stats = []
    for track, ratings in data["ratings"].items():
        avg = sum(ratings) / len(ratings)
        stats.append(f"• {track}: {avg:.1f}/5 ({len(ratings)} оценок)")
    
    # Сортируем по средней оценке
    stats.sort(key=lambda x: float(x.split(": ")[1].split("/")[0]), reverse=True)
    
    # Берём топ-10
    top_stats = stats[:10]
    
    await update.message.reply_text(
        "📊 **Топ треков по оценкам:**\n\n" + "\n".join(top_stats),
        parse_mode="Markdown"
    )

async def random_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    data = load_data()
    all_tracks = []
    for mood_tracks in data["tracks"].values():
        all_tracks.extend(mood_tracks)
    
    if not all_tracks:
        await update.message.reply_text("📭 Библиотека пуста. Добавь песни через /addfile")
        return
    
    track = random.choice(all_tracks)
    caption = get_random_caption("случайное", track["title"])
    
    rating_keyboard = [
        [
            InlineKeyboardButton("⭐ 1", callback_data=f"rate_1_{track['title']}"),
            InlineKeyboardButton("⭐⭐ 2", callback_data=f"rate_2_{track['title']}"),
            InlineKeyboardButton("⭐⭐⭐ 3", callback_data=f"rate_3_{track['title']}"),
            InlineKeyboardButton("⭐⭐⭐⭐ 4", callback_data=f"rate_4_{track['title']}"),
            InlineKeyboardButton("⭐⭐⭐⭐⭐ 5", callback_data=f"rate_5_{track['title']}")
        ]
    ]
    
    try:
        await context.bot.send_audio(
            chat_id=update.message.chat_id,
            audio=track["file_id"],
            caption=f"{caption}\n\n🎵 {track['title']}\n\n⭐ **Оцени песню:**",
            performer=track.get("performer", ""),
            title=track.get("title", ""),
            reply_markup=InlineKeyboardMarkup(rating_keyboard)
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def library_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    data = load_data()
    stats = []
    for mood, tracks in data["tracks"].items():
        if tracks:
            stats.append(f"• {mood}: {len(tracks)} треков")
    
    if not stats:
        await update.message.reply_text("📭 Библиотека пуста. /addfile")
        return
    
    await update.message.reply_text(
        "📚 **Твоя библиотека:**\n\n" + "\n".join(stats),
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    await update.message.reply_text(get_stats(YOUR_USER_ID))

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    data = load_data()
    entries = data["users"].get(str(YOUR_USER_ID), {}).get("entries", [])[-5:]
    if not entries:
        await update.message.reply_text("Дневник пуст")
        return
    text = "📜 **Последние 5 записей:**\n"
    for e in reversed(entries):
        text += f"\n• {e['date']} {e['time']} — {e['mood']}\n  🎵 {e['track_title']}"
    await update.message.reply_text(text, parse_mode="Markdown")

def keep_alive():
    url = f"https://{os.environ.get('RENDER_SERVICE_NAME', 'my-mood-bot')}.onrender.com/ping"
    while True:
        time.sleep(14 * 60)
        try:
            requests.get(url, timeout=10)
            print("🔄 Автопинг: бот разбужен")
        except Exception as e:
            print(f"❌ Ошибка автопинга: {e}")

def run_flask():
    app_web.run(host='0.0.0.0', port=10000)

def main():
    if not BOT_TOKEN:
        print("❌ Ошибка: TELEGRAM_TOKEN не найден!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addfile", addfile_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("random", random_track))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("ratings", ratings_stats_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("library", library_command))
    app.add_handler(CallbackQueryHandler(addmood_callback, pattern="^addmood_"))
    app.add_handler(CallbackQueryHandler(mood_callback, pattern="^mood_"))
    app.add_handler(CallbackQueryHandler(rating_callback, pattern="^rate_"))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    
    print("🤖 Бот запущен на Render!")
    print("🛡️ Автопинг каждые 14 минут включён")
    print("⭐ Оценки треков через звёздочки — активны")
    
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    ping_thread = Thread(target=keep_alive, daemon=True)
    ping_thread.start()
    
    app.run_polling()

if __name__ == "__main__":
    main()
