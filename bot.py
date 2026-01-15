import telebot
from telebot import types
import sqlite3
import json
import threading
from flask import Flask

# --- НАСТРОЙКИ FLASK (для Render) ---
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!" # Ответ для Render, чтобы сервис считался живым

def run_flask():
    # Render передает порт в переменную окружения PORT
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- НАСТРОЙКИ BOT ---
TOKEN = '8412845441:AAFmwd_UCsGNlbsab1z6Q0FnRMof8NIf6pI'
OWNER_ID = 8292372344
ADMINS = [8292372344]
OWNER_USERNAME = "@crollow"

bot = telebot.TeleBot(TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS accounts 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, country TEXT, otlega TEXT, price TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect('shop.db', check_same_thread=False)

def add_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# --- КЛАВИАТУРЫ ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📦 Купить ФИЗ", "🆘 Связь с владельцем")
    return markup

def admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Добавить ФИЗ", "📢 Рассылка")
    markup.add("📊 Статистика", "👤 Добавить админа")
    markup.add("🏠 В главное меню")
    return markup

# --- ОБРАБОТКА КОМАНД ---
@bot.message_handler(commands=['start'])
def start(message):
    add_user(message.from_user.id)
    text = "Добро пожаловать в магазин ФИЗ аккаунтов!"
    bot.send_message(message.chat.id, text, reply_markup=main_menu())
    if message.from_user.id in ADMINS:
        bot.send_message(message.chat.id, "Вы вошли как администратор.", reply_markup=admin_menu())

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id in ADMINS:
        bot.send_message(message.chat.id, "Админ-панель открыта.", reply_markup=admin_menu())

# --- ЛОГИКА ПОКУПАТЕЛЯ ---
@bot.message_handler(func=lambda m: m.text == "📦 Купить ФИЗ")
def list_accounts(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM accounts')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "В данный момент нет доступных аккаунтов.")
        return

    for row in rows:
        text = f"🌍 Страна: {row[1]}\n⏳ Отлега: {row[2]}\n💰 Цена: {row[3]}\n\n✅ Купить можно у: {OWNER_USERNAME}"
        bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🆘 Связь с владельцем")
def support(message):
    msg = bot.send_message(message.chat.id, "Напишите ваше сообщение, и владелец вам ответит:")
    bot.register_next_step_handler(msg, forward_to_owner)

def forward_to_owner(message):
    for admin in ADMINS:
        bot.send_message(admin, f"📩 НОВОЕ СООБЩЕНИЕ ОТ @{message.from_user.username} (ID: {message.from_user.id}):\n\n{message.text}")
    bot.send_message(message.chat.id, "✅ Ваше сообщение отправлено! Ожидайте ответа.")

# --- ЛОГИКА АДМИНА ---
@bot.message_handler(func=lambda m: m.text == "➕ Добавить ФИЗ" and m.from_user.id in ADMINS)
def add_fiz_start(message):
    msg = bot.send_message(message.chat.id, "Введите страну:")
    bot.register_next_step_handler(msg, process_country)

def process_country(message):
    country = message.text
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Дни", callback_data=f"type_дни_{country}"),
               types.InlineKeyboardButton("Года", callback_data=f"type_года_{country}"))
    bot.send_message(message.chat.id, "Выберите тип отлеги:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('type_'))
def process_otlega_type(call):
    _, o_type, country = call.data.split('_')
    msg = bot.send_message(call.message.chat.id, f"Введите количество ({o_type}):")
    bot.register_next_step_handler(msg, lambda m: process_otlega_value(m, country, o_type))

def process_otlega_value(message, country, o_type):
    otlega = f"{message.text} {o_type}"
    msg = bot.send_message(message.chat.id, "Введите цену:")
    bot.register_next_step_handler(msg, lambda m: finish_adding(m, country, otlega))

def finish_adding(message, country, otlega):
    price = message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO accounts (country, otlega, price) VALUES (?, ?, ?)', (country, otlega, price))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "✅ Аккаунт успешно добавлен!", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in ADMINS)
def stats(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    count = cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    bot.send_message(message.chat.id, f"👥 Всего пользователей: {count}")

@bot.message_handler(func=lambda m: m.text == "📢 Рассылка" and m.from_user.id in ADMINS)
def broadcast_start(message):
    msg = bot.send_message(message.chat.id, "Введите сообщение для рассылки:")
    bot.register_next_step_handler(msg, run_broadcast)

def run_broadcast(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    users = cursor.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    
    count = 0
    for user in users:
        try:
            bot.send_message(user[0], message.text)
            count += 1
        except:
            pass
    bot.send_message(message.chat.id, f"✅ Рассылка завершена! Получили: {count}")

@bot.message_handler(func=lambda m: m.reply_to_message is not None and m.from_user.id in ADMINS)
def reply_to_user(message):
    try:
        original_text = message.reply_to_message.text
        target_user_id = int(original_text.split("ID: ")[1].split("):")[0])
        bot.send_message(target_user_id, f"👨‍💻 Ответ от владельца:\n\n{message.text}")
        bot.send_message(message.chat.id, "✅ Ответ отправлен!")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка при ответе.")

# --- ЗАПУСК ---
if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask).start()
    
    # Запускаем бота
    print("Бот запущен...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
