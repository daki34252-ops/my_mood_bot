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
    return "🤖 Дневник эмоций с питомцем работает!"

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
HF_TOKEN = os.environ.get("HF_TOKEN")
# =================================

DIARY_FILE = "diary.json"
PET_FILE = "pet.json"
JOY_FILE = "joy.json"

# ========== ЗАГРУЗКА/СОХРАНЕНИЕ ==========
def load_diary():
    if os.path.exists(DIARY_FILE):
        with open(DIARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}

def save_diary(data):
    with open(DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_pet():
    if os.path.exists(PET_FILE):
        with open(PET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "hunger": 50,      # 0-100, чем выше, тем голоднее
        "boredom": 50,     # скука
        "dirt": 50,        # грязь
        "tiredness": 50,   # усталость
        "diamonds": 3,     # алмазы
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def save_pet(data):
    with open(PET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_joy():
    if os.path.exists(JOY_FILE):
        with open(JOY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}

def save_joy(data):
    with open(JOY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========== АНАЛИЗ НАСТРОЕНИЯ ==========
def analyze_mood(text: str):
    """Анализирует текст и возвращает настроение"""
    try:
        API_URL = "https://api-inference.huggingface.co/models/cointegrated/rubert-tiny-toxicity"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        
        response = requests.post(API_URL, headers=headers, json={"inputs": text}, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            positivity = result[0].get('positive', 0)
            negativity = result[0].get('negative', 0)
            toxicity = result[0].get('toxicity', 0)
            
            if positivity > 0.7:
                return "радость"
            elif negativity > 0.7:
                return "грусть"
            elif toxicity > 0.6:
                return "злость"
            else:
                return "спокойствие"
    except Exception as e:
        print(f"Ошибка анализа: {e}")
    
    return "нейтральное"

# ========== ПОДДЕРЖИВАЮЩИЕ ОТВЕТЫ ==========
def get_support(mood: str) -> str:
    support_messages = {
        "радость": [
            "😊 Я так рада за тебя! Сохрани этот свет в сердечке 💛",
            "🌸 Твоя радость греет и моего питомца!",
            "✨ Великолепно! Запомни это чувство."
        ],
        "грусть": [
            "🍂 Обнимаю тебя мысленно. Питомец тоже грустит с тобой, но верит, что всё наладится 💚",
            "😔 Твои чувства важны. Позволь себе побыть в них. Я рядом.",
            "💚 Грусть приходит и уходит. А я всегда здесь."
        ],
        "злость": [
            "🤬 Выдохни. Мощный выдох. Питомец прыгает рядом, чтобы отвлечь!",
            "🔥 Это чувство имеет право быть. Но не позволяй ему управлять тобой. Ты сильнее.",
            "💪 Злость — это энергия. Направь её на что-то полезное!"
        ],
        "спокойствие": [
            "😌 Спокойствие — это суперсила. Питомец довольно мурчит 🐱",
            "🌊 Гармония внутри тебя. Продолжай в том же духе.",
            "🍃 Тишина и баланс. Как приятно это читать."
        ],
        "нейтральное": [
            "📝 Спасибо за запись. Каждая заметка делает тебя ближе к себе 💚",
            "✨ Твой дневник — пространство без осуждения. Пиши всё, что чувствуешь.",
            "🤍 Я здесь, чтобы слушать и поддерживать."
        ]
    }
    return random.choice(support_messages.get(mood, support_messages["нейтральное"]))

# ========== ПИТОМЕЦ (ЭМОДЗИ) ==========
def get_pet_emoji(pet):
    """Возвращает смайлик котика в зависимости от состояния"""
    if pet["hunger"] > 75:
        return "🍽️😿"  # голодный
    elif pet["boredom"] > 75:
        return "😿💤"  # скучающий
    elif pet["dirt"] > 75:
        return "🫧😾"  # грязный
    elif pet["tiredness"] > 75:
        return "😴🐱"  # сонный
    elif pet["hunger"] < 30 and pet["boredom"] < 30 and pet["dirt"] < 30:
        return "😻✨"  # счастливый
    else:
        return "🐱"    # обычный

def update_pet_state():
    """Обновляет состояние питомца (голод, скука и т.д.) со временем"""
    pet = load_pet()
    
    # Сколько времени прошло с последнего обновления
    last = datetime.strptime(pet["last_update"], "%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    hours_passed = (now - last).total_seconds() / 3600
    
    if hours_passed > 0:
        # Состояния ухудшаются со временем
        pet["hunger"] = min(100, pet["hunger"] + int(hours_passed * 3))
        pet["boredom"] = min(100, pet["boredom"] + int(hours_passed * 2))
        pet["dirt"] = min(100, pet["dirt"] + int(hours_passed * 1.5))
        pet["tiredness"] = min(100, pet["tiredness"] + int(hours_passed * 2))
        pet["last_update"] = now.strftime("%Y-%m-%d %H:%M:%S")
        save_pet(pet)
    
    return pet

def pet_action(action: str) -> tuple:
    """Выполняет действие с питомцем. Возвращает (успех, сообщение, новый смайлик)"""
    pet = update_pet_state()
    
    if pet["diamonds"] <= 0:
        return False, "💎 У тебя нет алмазов! Выполни /tasks, чтобы получить алмазы.", None
    
    success = False
    message = ""
    
    if action == "feed":
        if pet["hunger"] > 0:
            pet["hunger"] = max(0, pet["hunger"] - 30)
            pet["diamonds"] -= 1
            success = True
            message = "🍽️ Покормила котика! Он довольно мурчит 😻"
    elif action == "play":
        if pet["boredom"] > 0:
            pet["boredom"] = max(0, pet["boredom"] - 30)
            pet["diamonds"] -= 1
            success = True
            message = "🎮 Поиграла с котиком! Он прыгает от счастья 🐱✨"
    elif action == "clean":
        if pet["dirt"] > 0:
            pet["dirt"] = max(0, pet["dirt"] - 30)
            pet["diamonds"] -= 1
            success = True
            message = "🧼 Помыла котика! Он стал чистым и пушистым 🫧"
    elif action == "sleep":
        if pet["tiredness"] > 0:
            pet["tiredness"] = max(0, pet["tiredness"] - 30)
            pet["diamonds"] -= 1
            success = True
            message = "🛌 Уложила котика спать. Он свернулся калачиком и мурчит 😴"
    
    if success:
        pet["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_pet(pet)
        new_emoji = get_pet_emoji(pet)
        return True, f"{message}\n\n💎 Алмазов осталось: {pet['diamonds']}\n🐱 Состояние: {new_emoji}", new_emoji
    else:
        return False, f"❌ Нечего делать! {message if message else 'Питомец уже сыт/чист/выспался'}", None

def add_diamonds(amount: int, reason: str):
    pet = load_pet()
    pet["diamonds"] += amount
    save_pet(pet)
    return pet["diamonds"]

# ========== КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        await update.message.reply_text("Это личный дневник 🙈")
        return
    
    pet = update_pet_state()
    pet_emoji = get_pet_emoji(pet)
    
    await update.message.reply_text(
        f"📔 **Твой дневник эмоций**\n\n"
        f"🐱 **Твой питомец:** {pet_emoji}\n"
        f"💎 Алмазов: {pet['diamonds']}\n\n"
        f"/note [текст] — записать день (анализ эмоций)\n"
        f"/mood — быстро отметить настроение\n"
        f"/joy [текст] — записать маленькую радость (+1💎)\n"
        f"/pet — покормить, поиграть, помыть, уложить спать\n"
        f"/tasks — задания для получения алмазов\n"
        f"/week — итоги недели\n"
        f"/stats — статистика\n"
        f"/history — последние записи\n\n"
        f"💚 Заботься о питомце, и он будет радовать тебя!",
        parse_mode="Markdown"
    )

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("📝 Пример: `/note Сегодня был хороший день`")
        return
    
    text = " ".join(context.args)
    status_msg = await update.message.reply_text("📖 Анализирую...")
    
    mood = analyze_mood(text)
    support = get_support(mood)
    
    # Сохраняем в дневник
    diary = load_diary()
    diary["entries"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "text": text,
        "mood": mood,
        "ai_response": support
    })
    save_diary(diary)
    
    # Награда за запись
    new_balance = add_diamonds(1, f"запись в дневнике ({mood})")
    
    await status_msg.delete()
    await update.message.reply_text(
        f"📔 **Запись сохранена!**\n"
        f"😊 Настроение: **{mood}**\n\n"
        f"💚 {support}\n\n"
        f"✨ +1 алмаз! 💎 Всего: {new_balance}",
        parse_mode="Markdown"
    )
    
    # Обновляем питомца (грустная запись влияет на скуку)
    pet = load_pet()
    if mood == "грусть":
        pet["boredom"] = min(100, pet["boredom"] + 5)
        save_pet(pet)

async def joy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("🌸 Пример: `/joy Сегодня пила вкусный чай`")
        return
    
    text = " ".join(context.args)
    
    joy_data = load_joy()
    joy_data["entries"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "text": text
    })
    save_joy(joy_data)
    
    # Награда за радость
    new_balance = add_diamonds(1, "маленькая радость")
    
    await update.message.reply_text(
        f"🌸 **Радость сохранена!**\n"
        f"📝 {text}\n\n"
        f"✨ +1 алмаз! 💎 Всего: {new_balance}\n\n"
        f"Твой питомец довольно мурчит 🐱",
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
    ]
    await update.message.reply_text("Как ты себя чувствуешь?", reply_markup=InlineKeyboardMarkup(keyboard))

async def mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != YOUR_USER_ID:
        return
    
    mood = query.data.replace("mood_", "")
    support = get_support(mood)
    
    # Сохраняем в дневник
    diary = load_diary()
    diary["entries"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "text": "",
        "mood": mood,
        "ai_response": support
    })
    save_diary(diary)
    
    # Награда
    new_balance = add_diamonds(1, f"отметка настроения ({mood})")
    
    await query.edit_message_text(
        f"✅ Отметка сохранена!\n"
        f"😊 Настроение: {mood}\n\n"
        f"💚 {support}\n\n"
        f"✨ +1 алмаз! 💎 Всего: {new_balance}"
    )

async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    pet = update_pet_state()
    pet_emoji = get_pet_emoji(pet)
    
    keyboard = [
        [
            InlineKeyboardButton("🍽️ Покормить (1💎)", callback_data="pet_feed"),
            InlineKeyboardButton("🎮 Погулять (1💎)", callback_data="pet_play")
        ],
        [
            InlineKeyboardButton("🧼 Помыть (1💎)", callback_data="pet_clean"),
            InlineKeyboardButton("🛌 Уложить спать (1💎)", callback_data="pet_sleep")
        ]
    ]
    
    status = ""
    if pet["hunger"] > 70:
        status += "🍽️ Питомец голоден! "
    if pet["boredom"] > 70:
        status += "😿 Питомец скучает! "
    if pet["dirt"] > 70:
        status += "🫧 Питомец грязный! "
    if pet["tiredness"] > 70:
        status += "😴 Питомец хочет спать! "
    
    if not status:
        status = "✨ Питомец счастлив и доволен!"
    
    await update.message.reply_text(
        f"🐱 **Твой питомец** {pet_emoji}\n\n"
        f"🍽️ Голод: {pet['hunger']}%\n"
        f"🎮 Скука: {pet['boredom']}%\n"
        f"🧼 Грязь: {pet['dirt']}%\n"
        f"😴 Усталость: {pet['tiredness']}%\n\n"
        f"💎 Алмазов: {pet['diamonds']}\n\n"
        f"{status}\n\n"
        f"Выбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def pet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != YOUR_USER_ID:
        return
    
    action = query.data.replace("pet_", "")
    success, message, new_emoji = pet_action(action)
    
    if success:
        pet = load_pet()
        await query.edit_message_text(
            f"{message}\n\n"
            f"🐱 Состояние: {new_emoji}\n"
            f"💎 Алмазов осталось: {pet['diamonds']}\n\n"
            f"Хочешь ещё заботы? Напиши /pet"
        )
    else:
        await query.edit_message_text(
            f"{message}\n\n"
            f"Выполни /tasks, чтобы получить алмазы и помочь питомцу!"
        )

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    diary = load_diary()
    joy_data = load_joy()
    pet = load_pet()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Считаем, что сделано сегодня
    today_notes = sum(1 for e in diary["entries"] if e["date"] == today and e["text"])
    today_moods = sum(1 for e in diary["entries"] if e["date"] == today and not e["text"])
    today_joys = sum(1 for e in joy_data["entries"] if e["date"] == today)
    
    tasks = [
        f"{'✅' if today_notes > 0 else '❌'} Запись в дневнике (/note) — +1💎",
        f"{'✅' if today_moods > 0 else '❌'} Отметка настроения (/mood) — +1💎",
        f"{'✅' if today_joys > 0 else '❌'} Маленькая радость (/joy) — +1💎",
        f"{'❌'} Выполнить квест дня (/daily) — +2💎",
        f"{'✅' if len(diary['entries']) >= 3 else '❌'} 3 записи за день — +1💎 бонус"
    ]
    
    await update.message.reply_text(
        f"📋 **Ежедневные задания**\n\n"
        + "\n".join(tasks) +
        f"\n\n💎 Всего алмазов: {pet['diamonds']}\n\n"
        f"🌸 Каждое задание даёт алмазы для заботы о питомце!",
        parse_mode="Markdown"
    )

async def daily_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    quests = [
        "Напиши 3 вещи, за которые ты благодарна себе",
        "Сделай 5 глубоких вдохов и выдохов",
        "Напиши комплимент себе",
        "Вспомни момент, когда ты помогла кому-то",
        "Скажи вслух: 'Я справлюсь'",
        "Напиши, что сегодня заставило тебя улыбнуться"
    ]
    
    quest = random.choice(quests)
    
    await update.message.reply_text(
        f"🎯 **Квест дня**\n\n"
        f"{quest}\n\n"
        f"✨ Награда: +2 алмаза\n"
        f"✅ Когда сделаешь — напиши /done",
        parse_mode="Markdown"
    )
    
    # Сохраняем квест для проверки
    context.user_data["daily_quest"] = quest
    context.user_data["quest_date"] = datetime.now().strftime("%Y-%m-%d")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    if not context.user_data.get("daily_quest"):
        await update.message.reply_text("Сначала получи квест дня: /daily")
        return
    
    new_balance = add_diamonds(2, "квест дня выполнен")
    del context.user_data["daily_quest"]
    
    await update.message.reply_text(
        f"🎉 **Молодец! Квест выполнен!**\n\n"
        f"✨ +2 алмаза! 💎 Всего: {new_balance}\n\n"
        f"Твой питомец гордится тобой 🐱💚"
    )

async def week_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    diary = load_diary()
    week_ago = datetime.now() - timedelta(days=7)
    week_entries = []
    for e in diary["entries"]:
        try:
            if datetime.strptime(e["date"], "%Y-%m-%d") >= week_ago:
                week_entries.append(e)
        except:
            pass
    
    if not week_entries:
        await update.message.reply_text("📭 За эту неделю нет записей.")
        return
    
    mood_count = {}
    for e in week_entries:
        mood_count[e["mood"]] = mood_count.get(e["mood"], 0) + 1
    
    report = f"📊 **Твоя неделя в цифрах**\n\n"
    for mood, count in mood_count.items():
        bar = "█" * min(count, 10)
        report += f"{mood}: {bar} {count}\n"
    
    if mood_count.get("грусть", 0) > mood_count.get("радость", 0):
        report += "\n💚 Непростая неделя. Но ты справляешься!"
    elif mood_count.get("радость", 0) > 2:
        report += "\n✨ Отличная неделя! Ты сияешь."
    
    await update.message.reply_text(report, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    diary = load_diary()
    entries = diary["entries"]
    if not entries:
        await update.message.reply_text("📭 Дневник пуст.")
        return
    
    mood_count = {}
    for e in entries:
        mood_count[e["mood"]] = mood_count.get(e["mood"], 0) + 1
    
    report = f"📊 **Всего записей:** {len(entries)}\n\n"
    for mood, count in mood_count.items():
        report += f"{mood}: {count}\n"
    
    pet = load_pet()
    report += f"\n🐱 Питомец: {get_pet_emoji(pet)}\n💎 Алмазов: {pet['diamonds']}"
    
    await update.message.reply_text(report, parse_mode="Markdown")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    diary = load_diary()
    last_five = diary["entries"][-5:][::-1]
    
    if not last_five:
        await update.message.reply_text("📭 Дневник пуст.")
        return
    
    text = "📜 **Последние записи:**\n\n"
    for e in last_five:
        preview = e["text"][:80] + "..." if len(e["text"]) > 80 else e["text"] if e["text"] else "✏️ Быстрая отметка"
        text += f"📅 {e['date']} — {e['mood']}\n   {preview}\n\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def joys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    
    joy_data = load_joy()
    last_joys = joy_data["entries"][-5:][::-1]
    
    if not last_joys:
        await update.message.reply_text("🌸 Пока нет записанных радостей. Напиши /joy текст")
        return
    
    text = "🌸 **Твои маленькие радости:**\n\n"
    for j in last_joys:
        text += f"📅 {j['date']}: {j['text']}\n\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ========== АВТОПИНГ ==========
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

# ========== ЗАПУСК ==========
def main():
    if not BOT_TOKEN:
        print("❌ Нет TELEGRAM_TOKEN!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("joy", joy_command))
    app.add_handler(CommandHandler("mood", quick_mood))
    app.add_handler(CommandHandler("pet", pet_command))
    app.add_handler(CommandHandler("tasks", tasks_command))
    app.add_handler(CommandHandler("daily", daily_quest))
    app.add_handler(CommandHandler("done", done_command))
    app.add_handler(CommandHandler("week", week_report))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("joys", joys_command))
    app.add_handler(CallbackQueryHandler(mood_callback, pattern="^mood_"))
    app.add_handler(CallbackQueryHandler(pet_callback, pattern="^pet_"))
    
    print("🤖 Дневник эмоций с питомцем запущен!")
    print("🐱 Питомец-котик ждёт заботы!")
    print("💎 Система алмазов и заданий активна!")
    
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    ping_thread = Thread(target=keep_alive, daemon=True)
    ping_thread.start()
    
    app.run_polling()

if __name__ == "__main__":
    main()
