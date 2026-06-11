import os
import json
import random
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== ЗАГЛУШКА ДЛЯ RENDER (ВЕБ-СЕРВЕР) ==========
app_web = Flask(__name__)

@app_web.route('/')
def hello():
    return "🤖 Бот работает!"
# =======================================================

# ========== ТВОИ ДАННЫЕ ==========
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
YOUR_USER_ID = 8420827188
# =================================

DATA_FILE = "mood_diary.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "tracks": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_track_to_library(title: str):
    data = load_data()
    if not any(t["title"] == title for t in data["tracks"]):
        data["tracks"].append({"title": title})
        save_data(data)
        return True
    return False

def get_random_track():
    data = load_data()
    if not data["tracks"]:
        return None
    return random.choice(data["tracks"])

def get_random_caption(mood: str, track_title: str) -> str:
    captions = {
        "грустный": [
            f"🍂 Под грустинку — {track_title}. Выдохни.",
            f"😔 Грусть — это нормально. {track_title} — твой саундтрек.",
            f"🌧️ {track_title} для тихого вечера. Держись!",
        ],
        "весёлый": [
            f"🎉 {track_title} — энергия зашкаливает!",
            f"😄 Этот трек про тебя сегодня! {track_title}",
            f"💃 Танцуй под {track_title}!",
        ],
        "злой": [
            f"🤬 Выпусти пар под {track_title}. Громкость на максимум.",
            f"⚡ Злость — топливо. {track_title} в помощь.",
            f"🔥 {track_title} — выруби звук и проорись.",
        ],
        "спокойный": [
            f"😌 {track_title} — музыка для внутреннего равновесия.",
            f"🌊 Расслабься. {track_title} тебя ждёт.",
            f"🍃 {track_title} как тёплый ветер.",
        ],
        "влюблённый": [
            f"💘 {track_title} — это про тебя и твои чувства.",
            f"🌸 Весна в душе? {track_title} подтверждает.",
            f"💕 {track_title} для двоих.",
        ],
        "уставший": [
            f"🛌 {track_title} — ложись и слушай.",
            f"😴 Устал? {track_title} обнимет звуком.",
            f"🛋️ {track_title} для восстановления сил.",
        ],
        "случайное": [
            f"🎲 Держи случайный трек: {track_title}",
            f"🎧 Бот выбрал за тебя — {track_title}",
        ],
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
        "/stats — статистика\n"
        "/history — последние записи\n"
        "/add — добавить трек в библиотеку\n"
        "/tracks — показать все треки\n\n"
        "📝 Сначала добавь пару треков через /add!",
        parse_mode="Markdown"
    )

async def add_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("📝 Пример: `/add Название трека`")
        return
    title = " ".join(context.args)
    if add_track_to_library(title):
        await update.message.reply_text(f"✅ Трек «{title}» добавлен!")
    else:
        await update.message.reply_text(f"⚠️ Трек «{title}» уже есть.")

async def list_tracks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    data = load_data()
    if not data["tracks"]:
        await update.message.reply_text("📭 Библиотека пуста. /add")
        return
    tracks_list = "\n".join([f"• {t['title']}" for t in data["tracks"]])
    await update.message.reply_text(f"🎵 Твоя библиотека:\n{tracks_list}")

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
    track = get_random_track()
    if not track:
        await query.edit_message_text("📭 Библиотека пуста. Добавь треки через /add")
        return
    
    caption = get_random_caption(mood, track["title"])
    save_mood_entry(YOUR_USER_ID, mood, track["title"])
    await query.edit_message_text(f"🎵 **Настроение: {mood}**\n\n{caption}")

async def random_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    track = get_random_track()
    if not track:
        await update.message.reply_text("Библиотека пуста. /add")
        return
    caption = get_random_caption("случайное", track["title"])
    await update.message.reply_text(f"🎲 **Случайный трек**\n\n{caption}")

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

def run_flask():
    app_web.run(host='0.0.0.0', port=10000)

def main():
    if not BOT_TOKEN:
        print("❌ Ошибка: TELEGRAM_TOKEN не найден!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_track))
    app.add_handler(CommandHandler("tracks", list_tracks))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("random", random_track))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CallbackQueryHandler(mood_callback, pattern="^mood_"))
    
    print("🤖 Бот запущен на Render!")
    app.run_polling()

if __name__ == "__main__":
    # Запускаем Flask-сервер в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    # Запускаем Telegram-бота
    main()
