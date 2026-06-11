import os
import json
import random
import time
import asyncio
import yt_dlp
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
LIBRARY_FILE = "library.json"  # отдельный файл для библиотеки треков
pending_ratings = {}

def load_library():
    if os.path.exists(LIBRARY_FILE):
        with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []  # список треков: [{"title": "...", "file_id": "...", "performer": "..."}]

def save_library(library):
    with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2)

def load_diary():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "ratings": {}}

def save_diary(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_to_library(title: str, performer: str, file_id: str):
    library = load_library()
    # Проверяем, нет ли уже такого файла
    for track in library:
        if track.get("file_id") == file_id:
            return False
    library.append({
        "title": title,
        "performer": performer,
        "file_id": file_id,
        "date_added": datetime.now().strftime("%Y-%m-%d")
    })
    save_library(library)
    return True

def get_random_track():
    library = load_library()
    if not library:
        return None
    return random.choice(library)

def add_rating(track_title: str, rating: int):
    data = load_diary()
    if "ratings" not in data:
        data["ratings"] = {}
    if track_title not in data["ratings"]:
        data["ratings"][track_title] = []
    data["ratings"][track_title].append(rating)
    save_diary(data)

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
    data = load_diary()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {"entries": []}
    
    data["users"][uid]["entries"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "mood": mood,
        "track_title": track_title
    })
    save_diary(data)

def get_stats(user_id: int) -> str:
    data = load_diary()
    entries = data["users"].get(str(user_id), {}).get("entries", [])
    if not entries:
        return "📭 Дневник пуст. Нажми /mood"
    
    moods = {}
    for e in entries:
        moods[e["mood"]] = moods.get(e["mood"], 0) + 1
    
    most_common = max(moods, key=moods.get)
    mood_list = ", ".join([f"{k}: {v}" for k, v in moods.items()])
    return f"📊 Записей: {len(entries)}\n❤️ Чаще всего: {most_common} ({moods[most_common]} раз)\n{mood_list}"

# ========== СКАЧИВАНИЕ С YOUTUBE ==========
async def download_audio(url: str):
    """Скачивает аудио с YouTube и возвращает путь к файлу и информацию"""
    downloads_dir = "downloads"
    os.makedirs(downloads_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(downloads_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    loop = asyncio.get_event_loop()
    
    def download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Если файл .webm, переименуем в .m4a для лучшей совместимости
            if filename.endswith('.webm'):
                new_filename = filename.replace('.webm', '.m4a')
                os.rename(filename, new_filename)
                filename = new_filename
            return filename, info.get('title', 'Без названия'), info.get('uploader', 'Неизвестный исполнитель')
    
    return await loop.run_in_executor(None, download)

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        await update.message.reply_text("Это личный бот 🙈")
        return
    await update.message.reply_text(
        "🎧 **Твой дневник настроения с музыкой**\n\n"
        "/mood — записать настроение + получить трек\n"
        "/random — случайный трек\n"
        "/yt <ссылка> — скачать трек с YouTube\n"
        "/library — количество треков в библиотеке\n"
        "/ratings — топ треков по оценкам\n"
        "/stats — статистика дневника\n"
        "/history — последние записи\n\n"
        "🎵 Просто отправь аудиофайл — бот сохранит его в библиотеку!\n"
        "⭐ После прослушивания трека — оцени его звёздочками!",
        parse_mode="Markdown"
    )

async def yt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: `/yt https://youtu.be/...`", parse_mode="Markdown")
        return
    
    url = context.args[0]
    status_msg = await update.message.reply_text("⏳ Скачиваю аудио с YouTube... Это может занять до минуты.")
    
    try:
        filename, title, performer = await download_audio(url)
        
        # Отправляем аудио прямо в чат
        with open(filename, 'rb') as audio_file:
            message = await context.bot.send_audio(
                chat_id=update.message.chat_id,
                audio=audio_file,
                title=title[:64],  # ограничение Telegram
                performer=performer[:64],
                caption=f"🎵 **Скачано с YouTube**\n{title}\n{performer}\n\n💾 Трек сохранён в библиотеку!",
                parse_mode='Markdown'
            )
        
        # Сохраняем в библиотеку
        file_id = message.audio.file_id
        add_to_library(title, performer, file_id)
        
        # Удаляем временный файл
        os.remove(filename)
        
        await status_msg.delete()
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при скачивании: {e}")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    audio = update.message.audio
    if not audio:
        return
    
    title = audio.title or audio.file_name or "Без названия"
    performer = audio.performer or "Неизвестный исполнитель"
    file_id = audio.file_id
    
    if add_to_library(title, performer, file_id):
        await update.message.reply_text(f"✅ Трек сохранён в библиотеку!\n🎵 {title} — {performer}")
    else:
        await update.message.reply_text(f"⚠️ Трек уже есть в библиотеке")

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
        await query.edit_message_text("📭 Библиотека пуста. Добавь треки через /yt или отправь аудиофайл.")
        return
    
    caption = get_random_caption(mood, track["title"])
    save_mood_entry(YOUR_USER_ID, mood, track["title"])
    
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
            caption=f"{caption}\n\n⭐ **Оцени песню после прослушивания:**",
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
    track_title = "_".join(data_parts[2:])
    
    add_rating(track_title, rating)
    
    await query.edit_message_text(
        f"✅ **Оценка сохранена!**\n\n"
        f"🎵 {track_title}\n"
        f"⭐ Твоя оценка: {rating}/5\n\n"
        f"Спасибо! ❤️",
        parse_mode="Markdown"
    )

async def random_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    track = get_random_track()
    if not track:
        await update.message.reply_text("📭 Библиотека пуста. Добавь треки через /yt или отправь аудиофайл.")
        return
    
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
            caption=f"{caption}\n\n⭐ **Оцени песню:**",
            performer=track.get("performer", ""),
            title=track.get("title", ""),
            reply_markup=InlineKeyboardMarkup(rating_keyboard)
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def library_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    library = load_library()
    count = len(library)
    await update.message.reply_text(f"📚 **Твоя библиотека:**\n\nВсего треков: {count}", parse_mode="Markdown")

async def ratings_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    data = load_diary()
    if not data.get("ratings"):
        await update.message.reply_text("📭 Пока нет оценок.")
        return
    
    stats = []
    for track, ratings in data["ratings"].items():
        avg = sum(ratings) / len(ratings)
        stats.append(f"• {track}: {avg:.1f}/5 ({len(ratings)} оценок)")
    
    stats.sort(key=lambda x: float(x.split(": ")[1].split("/")[0]), reverse=True)
    top_stats = stats[:10]
    
    await update.message.reply_text(
        "📊 **Топ треков по оценкам:**\n\n" + "\n".join(top_stats),
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    await update.message.reply_text(get_stats(YOUR_USER_ID))

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    data = load_diary()
    entries = data["users"].get(str(YOUR_USER_ID), {}).get("entries", [])[-5:]
    if not entries:
        await update.message.reply_text("Дневник пуст")
        return
    text = "📜 **Последние 5 записей:**\n"
    for e in reversed(entries):
        text += f"\n• {e['date']} {e['time']} — {e['mood']}\n  🎵 {e['track_title']}"
    await update.message.reply_text(text, parse_mode="Markdown")

# ========== АВТОПИНГ ==========
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

# ========== ЗАПУСК ==========
def main():
    if not BOT_TOKEN:
        print("❌ Ошибка: TELEGRAM_TOKEN не найден!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("yt", yt_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("random", random_track))
    app.add_handler(CommandHandler("library", library_command))
    app.add_handler(CommandHandler("ratings", ratings_stats_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CallbackQueryHandler(mood_callback, pattern="^mood_"))
    app.add_handler(CallbackQueryHandler(rating_callback, pattern="^rate_"))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    
    print("🤖 Бот запущен на Render!")
    print("🛡️ Автопинг каждые 14 минут включён")
    print("🎵 Поддержка YouTube через /yt")
    print("📁 Сохранение аудиофайлов в библиотеку")
    
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    ping_thread = Thread(target=keep_alive, daemon=True)
    ping_thread.start()
    
    app.run_polling()

if __name__ == "__main__":
    main()
