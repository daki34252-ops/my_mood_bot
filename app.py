import os
import json
import random
import time
import re
import requests
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# ========== ЗАГЛУШКА ДЛЯ RENDER ==========
app_web = Flask(__name__)

@app_web.route('/')
def hello():
    return "🤖 Дневник эмоций работает!"

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
HF_TOKEN = os.environ.get("HF_TOKEN")  # токен из переменной окружения!
# =================================

DATA_FILE = "diary.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def analyze_with_ai(text: str):
    if not HF_TOKEN:
        # Если нет токена, используем fallback
        moods = ["радость", "грусть", "спокойствие", "усталость", "вдохновение"]
        return random.choice(moods), "Спасибо, что поделилась. Твои чувства важны 💚"
    
    try:
        API_URL = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        
        prompt = f"""Ты — заботливый друг. Прочитай запись и определи настроение (радость, грусть, злость, спокойствие, тревога, вдохновение, усталость, любовь). Напиши короткий поддерживающий ответ.

Запись: "{text}"

Формат ответа:
Настроение: [слово]
Поддержка: [твой ответ]"""

        response = requests.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                ai_text = result[0].get("generated_text", "")
                mood_match = re.search(r'Настроение:\s*(.+)', ai_text)
                support_match = re.search(r'Поддержка:\s*(.+)', ai_text)
                mood = mood_match.group(1).strip() if mood_match else "не определено"
                support = support_match.group(1).strip() if support_match else "Ты молодец! Я рядом 💚"
                return mood, support
    except Exception as e:
        print(f"Ошибка: {e}")
    
    moods = ["радость", "грусть", "спокойствие", "усталость", "вдохновение"]
    return random.choice(moods), "Спасибо, что поделилась. Твои чувства важны 💚"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        await update.message.reply_text("Это личный дневник 🙈")
        return
    await update.message.reply_text(
        "📔 **Твой дневник эмоций**\n\n"
        "/note [текст] — написать заметку\n"
        "/mood — быстро отметить настроение\n"
        "/week — итоги недели\n"
        "/stats — статистика\n"
        "/history — последние записи\n"
        "/advice — получить поддержку\n\n"
        "Я анализирую твои записи и поддерживаю тебя 💚",
        parse_mode="Markdown"
    )

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("Пример: `/note Сегодня был хороший день`", parse_mode="Markdown")
        return
    
    text = " ".join(context.args)
    status_msg = await update.message.reply_text("📖 Анализирую...")
    
    mood, support = analyze_with_ai(text)
    
    data = load_data()
    data["entries"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "text": text,
        "mood": mood,
        "ai_response": support
    })
    save_data(data)
    
    await status_msg.delete()
    await update.message.reply_text(
        f"📔 **Запись сохранена!**\n"
        f"😊 Настроение: {mood}\n\n"
        f"💚 {support}",
        parse_mode="Markdown"
    )

async def quick_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    keyboard = [
        [InlineKeyboardButton("😊 Радость", callback_data="mood_радость")],
        [InlineKeyboardButton("😢 Грусть", callback_data="mood_грусть")],
        [InlineKeyboardButton("🤬 Злость", callback_data="mood_злость")],
        [InlineKeyboardButton("😌 Спокойствие", callback_data="mood_спокойствие")],
        [InlineKeyboardButton("😰 Тревога", callback_data="mood_тревога")],
    ]
    await update.message.reply_text("Как ты себя чувствуешь?", reply_markup=InlineKeyboardMarkup(keyboard))

async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != YOUR_USER_ID:
        return
    
    mood = query.data.replace("mood_", "")
    
    data = load_data()
    data["entries"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "text": "",
        "mood": mood,
        "ai_response": f"Ты отметила {mood}. Я рядом 💚"
    })
    save_data(data)
    
    await query.edit_message_text(f"✅ Отметка сохранена! Настроение: {mood}")

async def week_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    data = load_data()
    week_ago = datetime.now() - timedelta(days=7)
    week_entries = []
    for e in data["entries"]:
        try:
            if datetime.strptime(e["date"], "%Y-%m-%d") >= week_ago:
                week_entries.append(e)
        except:
            pass
    
    if not week_entries:
        await update.message.reply_text("За эту неделю нет записей.")
        return
    
    mood_count = {}
    for e in week_entries:
        mood_count[e["mood"]] = mood_count.get(e["mood"], 0) + 1
    
    report = f"📊 **Неделя в цифрах**\n\n"
    for mood, count in mood_count.items():
        bar = "█" * min(count, 10)
        report += f"{mood}: {bar} {count}\n"
    
    await update.message.reply_text(report, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    data = load_data()
    entries = data["entries"]
    if not entries:
        await update.message.reply_text("Дневник пуст.")
        return
    
    mood_count = {}
    for e in entries:
        mood_count[e["mood"]] = mood_count.get(e["mood"], 0) + 1
    
    report = f"📊 **Всего записей:** {len(entries)}\n\n"
    for mood, count in mood_count.items():
        report += f"{mood}: {count}\n"
    
    await update.message.reply_text(report, parse_mode="Markdown")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    data = load_data()
    last_five = data["entries"][-5:][::-1]
    
    if not last_five:
        await update.message.reply_text("Дневник пуст.")
        return
    
    text = "📜 **Последние записи:**\n\n"
    for e in last_five:
        preview = e["text"][:80] + "..." if len(e["text"]) > 80 else e["text"] if e["text"] else "Быстрая отметка"
        text += f"📅 {e['date']} — {e['mood']}\n   {preview}\n\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def advice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💚 **Совет дня:**\n\n"
        "Твои чувства — это не хорошо и не плохо. Они просто есть.\n"
        "Позволь себе быть любой. Ты уже делаешь большой шаг, записывая их 💚"
    )

def keep_alive():
    url = f"https://{os.environ.get('RENDER_SERVICE_NAME', 'my-diary-bot')}.onrender.com/ping"
    while True:
        time.sleep(14 * 60)
        try:
            requests.get(url, timeout=10)
            print("🔄 Пинг")
        except:
            pass

def run_flask():
    app_web.run(host='0.0.0.0', port=10000)

def main():
    if not BOT_TOKEN:
        print("❌ Нет TELEGRAM_TOKEN!")
        return
    
    if not HF_TOKEN:
        print("⚠️ Нет HF_TOKEN! Нейросеть не будет работать, но бот запустится.")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("mood", quick_mood))
    app.add_handler(CommandHandler("week", week_report))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("advice", advice_command))
    app.add_handler(CallbackQueryHandler(mood_callback, pattern="^mood_"))
    
    print("🤖 Дневник эмоций запущен!")
    
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    ping_thread = Thread(target=keep_alive, daemon=True)
    ping_thread.start()
    
    app.run_polling()

if __name__ == "__main__":
    main()
