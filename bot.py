import telebot
from telebot import types
import sqlite3
import threading
import os
import time
from flask import Flask
import re  # Добавлен импорт

# --- КОНФИГУРАЦИЯ ---
TOKEN = '8412845441:AAFUh9QiSOp0ivuWSBA6MHCw3lqHKwrd2uE'
OWNER_ID = 8292372344  # ВАШ ID (Его нельзя удалить)
OWNER_USERNAME = "@crollow"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Глобальный список админов (кэш для быстрого доступа)
ADMIN_CACHE = set()
ADMIN_CACHE.add(OWNER_ID)

# --- FLASK (ДЛЯ RENDER) ---
@app.route('/')
def index():
    return "Bot is alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- БАЗА ДАННЫХ ---
def get_db_connection():
    # check_same_thread=False нужен, так как бот и фласк работают в разных потоках
    return sqlite3.connect('shop.db', check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица товаров
    cursor.execute('''CREATE TABLE IF NOT EXISTS accounts 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, country TEXT, otlega TEXT, price TEXT)''')
    
    # Таблица пользователей
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    
    # Таблица админов (Новая!)
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    
    # Добавляем владельца в БД, если его нет
    cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
    
    conn.commit()
    conn.close()
    update_admin_cache()

def update_admin_cache():
    """Обновляет глобальный список админов из БД"""
    global ADMIN_CACHE
    conn = get_db_connection()
    cursor = conn.cursor()
    admins = cursor.execute('SELECT user_id FROM admins').fetchall()
    conn.close()
    ADMIN_CACHE = {admin[0] for admin in admins}
    ADMIN_CACHE.add(OWNER_ID)  # Владелец всегда админ

def add_user_to_db(user_id):
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
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Добавить товар", "❌ Удалить товар")
    markup.add("📢 Рассылка", "📊 Статистика")
    markup.add("👤 Добавить админа", "🗑 Удалить админа")
    markup.add("🏠 В главное меню")
    return markup

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def start(message):
    add_user_to_db(message.from_user.id)
    bot.send_message(message.chat.id, "Добро пожаловать в магазин ФИЗ аккаунтов!", reply_markup=main_menu())
    
    # Если пишет админ, уведомляем его
    if message.from_user.id in ADMIN_CACHE:
        bot.send_message(message.chat.id, "👑 Вы опознаны как администратор. Введите /admin для меню.", reply_markup=main_menu())

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id in ADMIN_CACHE:
        bot.send_message(message.chat.id, "🛠 Админ-панель открыта.", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id, "⛔ У вас нет прав администратора.")

# --- ЛОГИКА ПОКУПАТЕЛЯ ---

@bot.message_handler(func=lambda m: m.text == "📦 Купить ФИЗ")
def list_accounts(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM accounts')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "😔 В данный момент товары закончились. Загляните позже!")
        return

    # Вывод товаров
    for row in rows:
        # row: (id, country, otlega, price)
        text = (f"🆔 ID товара: {row[0]}\n"
                f"🌍 Страна: {row[1]}\n"
                f"⏳ Отлега: {row[2]}\n"
                f"💰 Цена: {row[3]}\n\n"
                f"👉 Для покупки пишите: {OWNER_USERNAME}")
        bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🆘 Связь с владельцем")
def support(message):
    msg = bot.send_message(message.chat.id, "📝 Напишите ваше сообщение одним текстом, и я перешлю его владельцу:")
    bot.register_next_step_handler(msg, forward_to_admins)

def forward_to_admins(message):
    if message.text in ["📦 Купить ФИЗ", "🆘 Связь с владельцем", "🏠 В главное меню"]:
        bot.send_message(message.chat.id, "Отменено.")
        return

    # Отправляем всем админам
    for admin_id in ADMIN_CACHE:
        try:
            bot.send_message(admin_id, 
                             f"📩 <b>Новое сообщение от поддержки!</b>\n"
                             f"От: @{message.from_user.username or 'нет username'} (ID: <code>{message.from_user.id}</code>)\n\n"
                             f"Текст: {message.text}", parse_mode="HTML")
        except Exception as e:
            print(f"Не удалось отправить сообщение админу {admin_id}: {e}")
            pass  # Если админ заблокировал бота
            
    bot.send_message(message.chat.id, "✅ Сообщение отправлено! Ожидайте ответа.", reply_markup=main_menu())

# --- АДМИН: УПРАВЛЕНИЕ АДМИНАМИ ---

@bot.message_handler(func=lambda m: m.text == "👤 Добавить админа" and m.from_user.id in ADMIN_CACHE)
def add_admin_step(message):
    msg = bot.send_message(message.chat.id, "✍ Введите <b>цифровой ID</b> нового администратора:", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(message):
    try:
        new_admin_id = int(message.text.strip())
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже такой
        exists = cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (new_admin_id,)).fetchone()
        
        if exists:
            bot.send_message(message.chat.id, "⚠ Этот пользователь уже администратор.")
        else:
            cursor.execute('INSERT INTO admins (user_id) VALUES (?)', (new_admin_id,))
            conn.commit()
            update_admin_cache()  # Обновляем кэш
            bot.send_message(message.chat.id, f"✅ Пользователь <code>{new_admin_id}</code> добавлен в админы.", parse_mode="HTML")
            
        conn.close()
    except ValueError:
        bot.send_message(message.chat.id, "❌ Ошибка! ID должен состоять только из цифр. Попробуйте снова.")

@bot.message_handler(func=lambda m: m.text == "🗑 Удалить админа" and m.from_user.id in ADMIN_CACHE)
def del_admin_step(message):
    # Показываем список текущих админов
    conn = get_db_connection()
    admins = conn.cursor().execute('SELECT user_id FROM admins').fetchall()
    conn.close()
    
    if not admins:
        bot.send_message(message.chat.id, "⚠ Список админов пуст.")
        return
        
    text_list = "Список админов:\n" + "\n".join([f"<code>{a[0]}</code>" for a in admins])
    msg = bot.send_message(message.chat.id, f"{text_list}\n\n✍ Введите ID админа, которого нужно удалить:", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_del_admin)

def process_del_admin(message):
    try:
        del_id = int(message.text.strip())
        
        if del_id == OWNER_ID:
            bot.send_message(message.chat.id, "⛔ Вы не можете удалить Главного Владельца!")
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM admins WHERE user_id = ?', (del_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            update_admin_cache()
            bot.send_message(message.chat.id, f"✅ Админ <code>{del_id}</code> удален.", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, "⚠ Такого ID нет в списке админов.")
        
        conn.close()
    except ValueError:
        bot.send_message(message.chat.id, "❌ Ошибка! Нужен цифровой ID.")

# --- АДМИН: ТОВАРЫ ---

@bot.message_handler(func=lambda m: m.text == "➕ Добавить товар" and m.from_user.id in ADMIN_CACHE)
def add_item_start(message):
    msg = bot.send_message(message.chat.id, "1️⃣ Введите страну (например: 🇰🇿 Казахстан):")
    bot.register_next_step_handler(msg, process_country)

def process_country(message):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "🆘 Связь с владельцем"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=admin_menu())
        return
        
    country = message.text
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Дни", callback_data=f"type_дн_{country.replace(' ', '_')}"),
        types.InlineKeyboardButton("Года", callback_data=f"type_г_{country.replace(' ', '_')}")
    )
    bot.send_message(message.chat.id, "2️⃣ Выберите тип отлеги:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('type_'))
def process_type_callback(call):
    bot.answer_callback_query(call.id)
    data = call.data.split('_')
    
    if len(data) < 3:
        bot.send_message(call.message.chat.id, "❌ Ошибка в данных.")
        return
        
    o_type = data[1]
    # Восстанавливаем страну из callback_data (заменяем _ на пробелы)
    country = " ".join(data[2:]).replace('_', ' ')
    
    msg = bot.send_message(call.message.chat.id, f"3️⃣ Введите количество ({o_type}):")
    bot.register_next_step_handler(msg, lambda m: process_otlega_val(m, country, o_type))

def process_otlega_val(message, country, o_type):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "🆘 Связь с владельцем"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=admin_menu())
        return
        
    otlega_val = message.text
    full_otlega = f"{otlega_val} {o_type}"
    msg = bot.send_message(message.chat.id, "4️⃣ Введите цену (например: 500₽):")
    bot.register_next_step_handler(msg, lambda m: finish_item_add(m, country, full_otlega))

def finish_item_add(message, country, full_otlega):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "🆘 Связь с владельцем"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=admin_menu())
        return
        
    price = message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO accounts (country, otlega, price) VALUES (?, ?, ?)', (country, full_otlega, price))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ Товар добавлен!\n🌍 Страна: {country}\n⏳ Отлега: {full_otlega}\n💰 Цена: {price}", reply_markup=admin_menu())

# --- АДМИН: УДАЛЕНИЕ ТОВАРА ---
@bot.message_handler(func=lambda m: m.text == "❌ Удалить товар" and m.from_user.id in ADMIN_CACHE)
def delete_item_start(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM accounts')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "😔 Товаров нет для удаления.")
        return

    # Вывод товаров с кнопками для удаления
    for row in rows:
        text = (f"🆔 ID товара: {row[0]}\n"
                f"🌍 Страна: {row[1]}\n"
                f"⏳ Отлега: {row[2]}\n"
                f"💰 Цена: {row[3]}")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{row[0]}"))
        
        bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def process_delete_item(call):
    bot.answer_callback_query(call.id)
    item_id = int(call.data.split('_')[1])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM accounts WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    
    bot.edit_message_text(f"✅ Товар с ID {item_id} удален!", 
                          call.message.chat.id, 
                          call.message.message_id)

# --- АДМИН: ПРОЧЕЕ ---

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in ADMIN_CACHE)
def stats(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    users_count = cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    goods_count = cursor.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
    admins_count = cursor.execute('SELECT COUNT(*) FROM admins').fetchone()[0]
    conn.close()
    
    text = (f"📊 <b>Статистика бота:</b>\n\n"
            f"👤 Пользователей: {users_count}\n"
            f"📦 Товаров в наличии: {goods_count}\n"
            f"👮 Админов: {admins_count}")
    bot.send_message(message.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📢 Рассылка" and m.from_user.id in ADMIN_CACHE)
def broadcast_start(message):
    msg = bot.send_message(message.chat.id, "Введите текст (или фото с подписью) для рассылки:")
    bot.register_next_step_handler(msg, run_broadcast)

def run_broadcast(message):
    if message.text == "🏠 В главное меню":
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=admin_menu())
        return
        
    conn = get_db_connection()
    users = conn.cursor().execute('SELECT user_id FROM users').fetchall()
    conn.close()
    
    sent = 0
    blocked = 0
    
    status_msg = bot.send_message(message.chat.id, "⏳ Рассылка началась...")
    
    for user in users:
        user_id = user[0]
        try:
            # Копируем сообщение (поддерживает текст, фото, видео)
            bot.copy_message(user_id, message.chat.id, message.message_id)
            sent += 1
            time.sleep(0.05)  # Небольшая задержка, чтобы не словить лимиты ТГ
        except Exception as e:
            print(f"Не удалось отправить пользователю {user_id}: {e}")
            blocked += 1
            
    bot.edit_message_text(f"✅ Рассылка завершена!\n\nПолучили: {sent}\nЗаблокировали бота: {blocked}", 
                          message.chat.id, status_msg.message_id)

@bot.message_handler(func=lambda m: m.text == "🏠 В главное меню")
def back_home(message):
    if message.from_user.id in ADMIN_CACHE:
        bot.send_message(message.chat.id, "Главное меню", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id, "Главное меню", reply_markup=main_menu())

# --- ОТВЕТ АДМИНА (Reply) ---
@bot.message_handler(func=lambda m: m.reply_to_message is not None and m.from_user.id in ADMIN_CACHE)
def admin_reply(message):
    try:
        # Пытаемся достать ID из текста исходного сообщения
        original_text = message.reply_to_message.text or message.reply_to_message.caption
        if not original_text:
            bot.reply_to(message, "❌ В сообщении нет текста с ID пользователя.")
            return
            
        # Ищем кусок текста "ID: 123456"
        match = re.search(r'ID: <code>(\d+)</code>', original_text)
        if not match:
            match = re.search(r'ID: (\d+)', original_text)
        
        if match:
            target_id = int(match.group(1))
            bot.send_message(target_id, f"🔔 <b>Ответ от поддержки:</b>\n\n{message.text}", parse_mode="HTML")
            bot.reply_to(message, "✅ Ответ доставлен пользователю.")
        else:
            bot.reply_to(message, "❌ Не удалось найти ID пользователя в сообщении, на которое вы ответили.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка отправки: {e}")

# --- ЗАПУСК ---
if __name__ == '__main__':
    # Инициализация БД
    init_db()
    
    # Запуск Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🚀 Бот запущен...")
    # Бесконечный полинг с авто-перезапуском при ошибках
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Ошибка полинга: {e}")
            time.sleep(5)
