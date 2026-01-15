import telebot
from telebot import types
import sqlite3
import threading
import os
import time
from flask import Flask
import re
from datetime import datetime

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
    return sqlite3.connect('shop.db', check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица товаров
    cursor.execute('''CREATE TABLE IF NOT EXISTS accounts 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       country TEXT, 
                       otlega TEXT, 
                       price TEXT,
                       added_by INTEGER DEFAULT 0,
                       added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица пользователей
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY,
                       username TEXT,
                       join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица админов
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins 
                      (user_id INTEGER PRIMARY KEY,
                       added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица отзывов (НОВАЯ!)
    cursor.execute('''CREATE TABLE IF NOT EXISTS reviews
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER,
                       rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                       comment TEXT,
                       status TEXT DEFAULT 'pending', -- pending/approved/rejected
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    
    # Таблица предложок скупа (НОВАЯ!)
    cursor.execute('''CREATE TABLE IF NOT EXISTS buy_offers
                      (id INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id INTEGER,
                       country TEXT,
                       otlega TEXT,
                       price TEXT,
                       contacts TEXT,
                       status TEXT DEFAULT 'pending', -- pending/accepted/rejected
                       admin_comment TEXT,
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                       FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    
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
    ADMIN_CACHE.add(OWNER_ID)

def add_user_to_db(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    username = None
    try:
        user = bot.get_chat(user_id)
        username = user.username
    except:
        pass
    
    cursor.execute('''INSERT OR IGNORE INTO users (user_id, username) 
                      VALUES (?, ?)''', (user_id, username))
    conn.commit()
    conn.close()

# --- КЛАВИАТУРЫ ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📦 Купить ФИЗ", "💰 Предложить на продажу")
    markup.add("⭐ Оставить отзыв", "📝 Мои отзывы")
    markup.add("🆘 Связь с владельцем")
    return markup

def admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Добавить товар", "❌ Удалить товар")
    markup.add("📢 Рассылка", "📊 Статистика")
    markup.add("👤 Управление админами", "📋 Предложки скупа")
    markup.add("⭐ Модерация отзывов", "🏠 В главное меню")
    return markup

def admin_management_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("👤 Добавить админа", "🗑 Удалить админа")
    markup.add("📋 Список админов", "🔙 Назад в админку")
    return markup

def rating_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=5)
    ratings = []
    for i in range(1, 6):
        ratings.append(types.InlineKeyboardButton(str(i) + "⭐", callback_data=f"rate_{i}"))
    markup.add(*ratings)
    return markup

# --- ОБРАБОТЧИКИ КОМАНД ---
@bot.message_handler(commands=['start'])
def start(message):
    add_user_to_db(message.from_user.id)
    welcome_text = (
        "👋 Добро пожаловать в магазин ФИЗ аккаунтов!\n\n"
        "📦 <b>Купить ФИЗ</b> - просмотр доступных товаров\n"
        "💰 <b>Предложить на продажу</b> - продать свой аккаунт\n"
        "⭐ <b>Оставить отзыв</b> - поделиться впечатлениями\n"
        "📝 <b>Мои отзывы</b> - история ваших отзывов\n"
        "🆘 <b>Связь с владельцем</b> - техподдержка\n\n"
        "Мы ценим каждого клиента! 🤝"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=main_menu())
    
    if message.from_user.id in ADMIN_CACHE:
        bot.send_message(message.chat.id, "👑 Вы опознаны как администратор. Введите /admin для меню.")

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
    cursor.execute('SELECT * FROM accounts ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "😔 В данный момент товары закончились. Загляните позже!")
        return

    # Показываем первые 10 товаров, чтобы не спамить
    for row in rows[:10]:
        text = (f"🆔 ID товара: {row[0]}\n"
                f"🌍 Страна: {row[1]}\n"
                f"⏳ Отлега: {row[2]}\n"
                f"💰 Цена: {row[3]}\n"
                f"📅 Добавлен: {row[5].split()[0] if row[5] else 'Неизвестно'}\n\n"
                f"👉 Для покупки пишите: {OWNER_USERNAME}")
        bot.send_message(message.chat.id, text)
    
    if len(rows) > 10:
        bot.send_message(message.chat.id, f"📄 Показано 10 из {len(rows)} товаров. Используйте поиск по ID для конкретного товара.")

# --- СИСТЕМА СКУПА (ПРЕДЛОЖКА) ---
@bot.message_handler(func=lambda m: m.text == "💰 Предложить на продажу")
def start_buy_offer(message):
    msg = bot.send_message(message.chat.id, 
                         "💰 <b>Предложить аккаунт на продажу</b>\n\n"
                         "1️⃣ Введите страну аккаунта (например: 🇰🇿 Казахстан):",
                         parse_mode="HTML")
    bot.register_next_step_handler(msg, process_offer_country)

def process_offer_country(message):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "💰 Предложить на продажу", "⭐ Оставить отзыв"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=main_menu())
        return
    
    country = message.text
    bot.session_data = {'country': country}
    
    msg = bot.send_message(message.chat.id, "2️⃣ Введите отлегу аккаунта (например: 30 дней, 1 год):")
    bot.register_next_step_handler(msg, process_offer_otlega)

def process_offer_otlega(message):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "💰 Предложить на продажу", "⭐ Оставить отзыв"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=main_menu())
        return
    
    otlega = message.text
    bot.session_data['otlega'] = otlega
    
    msg = bot.send_message(message.chat.id, "3️⃣ Введите желаемую цену (например: 500₽):")
    bot.register_next_step_handler(msg, process_offer_price)

def process_offer_price(message):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "💰 Предложить на продажу", "⭐ Оставить отзыв"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=main_menu())
        return
    
    price = message.text
    bot.session_data['price'] = price
    
    msg = bot.send_message(message.chat.id, 
                         "4️⃣ Введите контакты для связи (Telegram @username или номер телефона):\n"
                         "<i>Эта информация будет видна только администратору</i>",
                         parse_mode="HTML")
    bot.register_next_step_handler(msg, finish_offer)

def finish_offer(message):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "💰 Предложить на продажу", "⭐ Оставить отзыв"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=main_menu())
        return
    
    contacts = message.text
    
    # Сохраняем предложку в БД
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO buy_offers 
                      (user_id, country, otlega, price, contacts) 
                      VALUES (?, ?, ?, ?, ?)''',
                   (message.from_user.id, 
                    bot.session_data['country'],
                    bot.session_data['otlega'],
                    bot.session_data['price'],
                    contacts))
    offer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Отправляем уведомление админам
    offer_text = (
        f"🆕 <b>Новая предложка скупа!</b>\n\n"
        f"🆔 ID: {offer_id}\n"
        f"👤 От: @{message.from_user.username or 'нет'} (ID: {message.from_user.id})\n"
        f"🌍 Страна: {bot.session_data['country']}\n"
        f"⏳ Отлега: {bot.session_data['otlega']}\n"
        f"💰 Цена: {bot.session_data['price']}\n"
        f"📞 Контакты: {contacts}\n\n"
        f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    
    for admin_id in ADMIN_CACHE:
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Принять", callback_data=f"offer_accept_{offer_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"offer_reject_{offer_id}")
            )
            bot.send_message(admin_id, offer_text, parse_mode="HTML", reply_markup=markup)
        except:
            pass
    
    bot.send_message(message.chat.id, 
                     "✅ Ваше предложение отправлено администраторам!\n"
                     "Мы рассмотрим его в ближайшее время и свяжемся с вами.",
                     reply_markup=main_menu())

# --- ОБРАБОТКА РЕШЕНИЙ ПО ПРЕДЛОЖКАМ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('offer_'))
def handle_offer_decision(call):
    bot.answer_callback_query(call.id)
    data = call.data.split('_')
    action = data[1]  # accept или reject
    offer_id = int(data[2])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем информацию о предложке
    cursor.execute('SELECT * FROM buy_offers WHERE id = ?', (offer_id,))
    offer = cursor.fetchone()
    
    if not offer:
        bot.send_message(call.message.chat.id, "❌ Предложка не найдена.")
        return
    
    user_id = offer[1]
    status = 'accepted' if action == 'accept' else 'rejected'
    
    # Обновляем статус
    cursor.execute('UPDATE buy_offers SET status = ? WHERE id = ?', (status, offer_id))
    conn.commit()
    
    # Уведомляем пользователя
    if action == 'accept':
        user_msg = (f"🎉 <b>Ваше предложение принято!</b>\n\n"
                   f"Скоро с вами свяжется администратор для уточнения деталей.\n"
                   f"🆔 ID предложки: {offer_id}\n"
                   f"💰 Ваша цена: {offer[4]}")
    else:
        user_msg = (f"😔 <b>Ваше предложение отклонено</b>\n\n"
                   f"К сожалению, ваше предложение не подошло нам по критериям.\n"
                   f"🆔 ID предложки: {offer_id}")
    
    try:
        bot.send_message(user_id, user_msg, parse_mode="HTML")
    except:
        pass
    
    # Обновляем сообщение админу
    new_text = call.message.text + f"\n\n✅ <b>Решение: {'ПРИНЯТО' if action == 'accept' else 'ОТКЛОНЕНО'} администратором @{call.from_user.username}</b>"
    bot.edit_message_text(new_text, 
                         call.message.chat.id, 
                         call.message.message_id,
                         parse_mode="HTML")
    
    conn.close()

# --- СИСТЕМА ОТЗЫВОВ ---
@bot.message_handler(func=lambda m: m.text == "⭐ Оставить отзыв")
def start_review(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем, не оставлял ли пользователь сегодня отзыв
    cursor.execute('''SELECT COUNT(*) FROM reviews 
                      WHERE user_id = ? AND date(created_at) = date('now')''',
                   (message.from_user.id,))
    today_reviews = cursor.fetchone()[0]
    
    if today_reviews >= 3:
        bot.send_message(message.chat.id, 
                        "⚠️ Вы можете оставлять не более 3 отзывов в день.\n"
                        "Загляните завтра! 😊",
                        reply_markup=main_menu())
        conn.close()
        return
    
    conn.close()
    
    bot.send_message(message.chat.id,
                    "⭐ <b>Оставить отзыв</b>\n\n"
                    "Пожалуйста, оцените наш сервис от 1 до 5 звезд:",
                    parse_mode="HTML",
                    reply_markup=rating_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_'))
def process_rating(call):
    bot.answer_callback_query(call.id)
    rating = int(call.data.split('_')[1])
    
    msg = bot.send_message(call.message.chat.id,
                         f"Вы выбрали {rating}⭐\n\n"
                         f"Теперь напишите ваш отзыв (максимум 500 символов):")
    
    bot.register_next_step_handler(msg, save_review, rating, call.from_user.id)

def save_review(message, rating, user_id):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "💰 Предложить на продажу", "⭐ Оставить отзыв"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=main_menu())
        return
    
    if len(message.text) > 500:
        bot.send_message(message.chat.id, "❌ Отзыв слишком длинный (максимум 500 символов). Попробуйте снова.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''INSERT INTO reviews (user_id, rating, comment) 
                      VALUES (?, ?, ?)''',
                   (user_id, rating, message.text))
    conn.commit()
    
    # Получаем статистику отзывов пользователя
    cursor.execute('''SELECT COUNT(*), AVG(rating) FROM reviews 
                      WHERE user_id = ? AND status = 'approved' ''',
                   (user_id,))
    stats = cursor.fetchone()
    
    conn.close()
    
    bot.send_message(message.chat.id,
                    f"✅ Ваш отзыв сохранен и отправлен на модерацию!\n\n"
                    f"📊 Ваша статистика:\n"
                    f"• Одобренных отзывов: {stats[0] or 0}\n"
                    f"• Средний рейтинг: {stats[1] or 'Нет'}\n\n"
                    f"Спасибо за обратную связь! 💖",
                    reply_markup=main_menu())
    
    # Уведомляем админов
    for admin_id in ADMIN_CACHE:
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Одобрить", callback_data=f"review_approve_{cursor.lastrowid}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"review_reject_{cursor.lastrowid}")
            )
            
            review_text = (
                f"🆕 <b>Новый отзыв на модерацию!</b>\n\n"
                f"👤 Пользователь: @{message.from_user.username or 'нет'} (ID: {user_id})\n"
                f"⭐ Рейтинг: {rating}/5\n"
                f"📝 Текст: {message.text[:200]}...\n\n"
                f"🆔 ID отзыва: {cursor.lastrowid}"
            )
            bot.send_message(admin_id, review_text, parse_mode="HTML", reply_markup=markup)
        except:
            pass

@bot.message_handler(func=lambda m: m.text == "📝 Мои отзывы")
def my_reviews(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''SELECT rating, comment, status, created_at 
                      FROM reviews 
                      WHERE user_id = ? 
                      ORDER BY created_at DESC 
                      LIMIT 10''',
                   (message.from_user.id,))
    reviews = cursor.fetchall()
    
    if not reviews:
        bot.send_message(message.chat.id, 
                        "📭 У вас пока нет отзывов.\n"
                        "Нажмите '⭐ Оставить отзыв', чтобы поделиться впечатлениями!",
                        reply_markup=main_menu())
        conn.close()
        return
    
    # Получаем статистику
    cursor.execute('''SELECT 
                      COUNT(*) as total,
                      COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                      COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                      COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                      AVG(rating) as avg_rating
                      FROM reviews 
                      WHERE user_id = ?''',
                   (message.from_user.id,))
    stats = cursor.fetchone()
    
    response = f"📊 <b>Ваша статистика отзывов:</b>\n\n"
    response += f"📈 Всего отзывов: {stats[0]}\n"
    response += f"✅ Одобрено: {stats[1]}\n"
    response += f"⏳ На модерации: {stats[2]}\n"
    response += f"❌ Отклонено: {stats[3]}\n"
    response += f"⭐ Средний рейтинг: {stats[4]:.1f} из 5\n\n"
    response += f"<b>Последние отзывы:</b>\n"
    
    for i, review in enumerate(reviews, 1):
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌'
        }.get(review[2], '❓')
        
        date_str = review[3].split()[0] if review[3] else "Неизвестно"
        response += f"\n{i}. {status_emoji} {review[0]}⭐ ({date_str})\n"
        if review[1]:
            response += f"   {review[1][:50]}..."
    
    conn.close()
    bot.send_message(message.chat.id, response, parse_mode="HTML")

# --- МОДЕРАЦИЯ ОТЗЫВОВ (АДМИН) ---
@bot.message_handler(func=lambda m: m.text == "⭐ Модерация отзывов" and m.from_user.id in ADMIN_CACHE)
def review_moderation(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''SELECT r.id, r.user_id, u.username, r.rating, r.comment, r.created_at
                      FROM reviews r
                      LEFT JOIN users u ON r.user_id = u.user_id
                      WHERE r.status = 'pending'
                      ORDER BY r.created_at ASC
                      LIMIT 10''')
    pending_reviews = cursor.fetchall()
    
    if not pending_reviews:
        bot.send_message(message.chat.id, 
                        "✅ Нет отзывов на модерацию!",
                        reply_markup=admin_menu())
        conn.close()
        return
    
    response = "⏳ <b>Отзывы на модерацию:</b>\n\n"
    
    for review in pending_reviews:
        response += (
            f"🆔 ID: {review[0]}\n"
            f"👤 Пользователь: @{review[2] or 'нет'} (ID: {review[1]})\n"
            f"⭐ Рейтинг: {review[3]}/5\n"
            f"📝 Текст: {review[4][:100]}...\n"
            f"📅 Дата: {review[5].split()[0]}\n"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"mod_review_approve_{review[0]}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"mod_review_reject_{review[0]}")
        )
        
        bot.send_message(message.chat.id, response, parse_mode="HTML", reply_markup=markup)
        response = ""  # Сбрасываем для следующего сообщения
    
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('mod_review_'))
def moderate_review(call):
    bot.answer_callback_query(call.id)
    data = call.data.split('_')
    action = data[2]  # approve или reject
    review_id = int(data[3])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем информацию об отзыве
    cursor.execute('''SELECT r.user_id, r.rating, r.comment, u.username
                      FROM reviews r
                      LEFT JOIN users u ON r.user_id = u.user_id
                      WHERE r.id = ?''', (review_id,))
    review = cursor.fetchone()
    
    if not review:
        bot.send_message(call.message.chat.id, "❌ Отзыв не найден.")
        conn.close()
        return
    
    # Обновляем статус
    new_status = 'approved' if action == 'approve' else 'rejected'
    cursor.execute('UPDATE reviews SET status = ? WHERE id = ?', (new_status, review_id))
    conn.commit()
    
    # Уведомляем пользователя
    user_id = review[0]
    try:
        if action == 'approve':
            user_msg = (f"✅ <b>Ваш отзыв одобрен и опубликован!</b>\n\n"
                       f"Спасибо за вашу обратную связь! 💖\n\n"
                       f"⭐ Рейтинг: {review[1]}/5\n"
                       f"📝 Текст: {review[2][:100]}...")
        else:
            user_msg = (f"❌ <b>Ваш отзыв отклонен модератором</b>\n\n"
                       f"Пожалуйста, ознакомьтесь с правилами оставления отзывов.\n"
                       f"Причина: не соответствует правилам сообщества.")
        
        bot.send_message(user_id, user_msg, parse_mode="HTML")
    except:
        pass
    
    # Обновляем средний рейтинг в базе
    if action == 'approve':
        cursor.execute('''SELECT AVG(rating) FROM reviews 
                          WHERE status = 'approved' ''')
        avg_rating = cursor.fetchone()[0]
        
        # Можно сохранить средний рейтинг в отдельную таблицу для быстрого доступа
    
    # Обновляем сообщение админу
    new_text = call.message.text + f"\n\n✅ <b>Решение: {'ОДОБРЕНО' if action == 'approve' else 'ОТКЛОНЕНО'} администратором @{call.from_user.username}</b>"
    bot.edit_message_text(new_text, 
                         call.message.chat.id, 
                         call.message.message_id,
                         parse_mode="HTML")
    
    conn.close()

# --- ПРОСМОТР ПРЕДЛОЖЕК СКУПА (АДМИН) ---
@bot.message_handler(func=lambda m: m.text == "📋 Предложки скупа" and m.from_user.id in ADMIN_CACHE)
def view_buy_offers(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''SELECT 
                      COUNT(*) as total,
                      COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                      COUNT(CASE WHEN status = 'accepted' THEN 1 END) as accepted,
                      COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected
                      FROM buy_offers''')
    stats = cursor.fetchone()
    
    response = f"💰 <b>Статистика предложок:</b>\n\n"
    response += f"📊 Всего предложок: {stats[0]}\n"
    response += f"⏳ Ожидают решения: {stats[1]}\n"
    response += f"✅ Принято: {stats[2]}\n"
    response += f"❌ Отклонено: {stats[3]}\n\n"
    
    # Показываем последние pending предложки
    cursor.execute('''SELECT b.id, b.user_id, u.username, b.country, b.otlega, b.price, b.created_at
                      FROM buy_offers b
                      LEFT JOIN users u ON b.user_id = u.user_id
                      WHERE b.status = 'pending'
                      ORDER BY b.created_at DESC
                      LIMIT 5''')
    pending = cursor.fetchall()
    
    if pending:
        response += "⏳ <b>Последние предложки на рассмотрении:</b>\n\n"
        for offer in pending:
            response += (
                f"🆔 ID: {offer[0]}\n"
                f"👤 От: @{offer[2] or 'нет'} (ID: {offer[1]})\n"
                f"🌍 Страна: {offer[3]}\n"
                f"⏳ Отлега: {offer[4]}\n"
                f"💰 Цена: {offer[5]}\n"
                f"📅 Дата: {offer[6].split()[0]}\n"
                f"────────────────────\n"
            )
    else:
        response += "✅ Нет предложок на рассмотрении."
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_offers"),
        types.InlineKeyboardButton("📋 Все предложки", callback_data="all_offers")
    )
    
    bot.send_message(message.chat.id, response, parse_mode="HTML", reply_markup=markup)
    conn.close()

# --- УПРАВЛЕНИЕ АДМИНАМИ ---
@bot.message_handler(func=lambda m: m.text == "👤 Управление админами" and m.from_user.id in ADMIN_CACHE)
def admin_management(message):
    bot.send_message(message.chat.id, "👥 Управление администраторами", reply_markup=admin_management_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Список админов" and m.from_user.id in ADMIN_CACHE)
def list_admins(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''SELECT a.user_id, u.username, a.added_date 
                      FROM admins a
                      LEFT JOIN users u ON a.user_id = u.user_id
                      ORDER BY a.added_date DESC''')
    admins = cursor.fetchall()
    
    response = "👑 <b>Список администраторов:</b>\n\n"
    
    for i, admin in enumerate(admins, 1):
        is_owner = "👑" if admin[0] == OWNER_ID else "👤"
        response += f"{i}. {is_owner} ID: <code>{admin[0]}</code>\n"
        response += f"   @{admin[1] or 'нет username'}\n"
        response += f"   📅 Добавлен: {admin[2].split()[0] if admin[2] else 'Неизвестно'}\n\n"
    
    response += f"Всего админов: {len(admins)}"
    
    bot.send_message(message.chat.id, response, parse_mode="HTML")
    conn.close()

@bot.message_handler(func=lambda m: m.text == "🔙 Назад в админку" and m.from_user.id in ADMIN_CACHE)
def back_to_admin(message):
    bot.send_message(message.chat.id, "🛠 Админ-панель", reply_markup=admin_menu())

# --- ПРОЧИЕ ФУНКЦИИ (оставлены без изменений, но адаптированы) ---
@bot.message_handler(func=lambda m: m.text == "🆘 Связь с владельцем")
def support(message):
    msg = bot.send_message(message.chat.id, "📝 Напишите ваше сообщение одним текстом, и я перешлю его администраторам:")
    bot.register_next_step_handler(msg, forward_to_admins)

def forward_to_admins(message):
    if message.text in ["🏠 В главное меню", "📦 Купить ФИЗ", "💰 Предложить на продажу", "⭐ Оставить отзыв"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=main_menu())
        return

    for admin_id in ADMIN_CACHE:
        try:
            bot.send_message(admin_id, 
                           f"📩 <b>Новое сообщение в поддержку!</b>\n"
                           f"От: @{message.from_user.username or 'нет username'} (ID: <code>{message.from_user.id}</code>)\n\n"
                           f"Текст: {message.text}", parse_mode="HTML")
        except Exception as e:
            print(f"Не удалось отправить сообщение админу {admin_id}: {e}")
            
    bot.send_message(message.chat.id, "✅ Сообщение отправлено! Ожидайте ответа.", reply_markup=main_menu())

# --- ДОБАВЛЕНИЕ ТОВАРА (адаптировано под новое меню) ---
@bot.message_handler(func=lambda m: m.text == "➕ Добавить товар" and m.from_user.id in ADMIN_CACHE)
def add_item_start(message):
    msg = bot.send_message(message.chat.id, "1️⃣ Введите страну (например: 🇰🇿 Казахстан):")
    bot.register_next_step_handler(msg, process_country)

def process_country(message):
    if message.text in ["🏠 В главное меню", "🔙 Назад в админку"]:
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
    country = " ".join(data[2:]).replace('_', ' ')
    
    msg = bot.send_message(call.message.chat.id, f"3️⃣ Введите количество ({o_type}):")
    bot.register_next_step_handler(msg, lambda m: process_otlega_val(m, country, o_type))

def process_otlega_val(message, country, o_type):
    if message.text in ["🏠 В главное меню", "🔙 Назад в админку"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=admin_menu())
        return
        
    otlega_val = message.text
    full_otlega = f"{otlega_val} {o_type}"
    msg = bot.send_message(message.chat.id, "4️⃣ Введите цену (например: 500₽):")
    bot.register_next_step_handler(msg, lambda m: finish_item_add(m, country, full_otlega))

def finish_item_add(message, country, full_otlega):
    if message.text in ["🏠 В главное меню", "🔙 Назад в админку"]:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=admin_menu())
        return
        
    price = message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO accounts (country, otlega, price, added_by) VALUES (?, ?, ?, ?)', 
                   (country, full_otlega, price, message.from_user.id))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, 
                   f"✅ Товар добавлен!\n🌍 Страна: {country}\n⏳ Отлега: {full_otlega}\n💰 Цена: {price}", 
                   reply_markup=admin_menu())

# --- ОСТАЛЬНЫЕ ФУНКЦИИ АДМИНА (статистика, рассылка и т.д.) ---
@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id in ADMIN_CACHE)
def stats(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    users_count = cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    goods_count = cursor.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
    admins_count = cursor.execute('SELECT COUNT(*) FROM admins').fetchone()[0]
    
    # Статистика по отзывам
    cursor.execute('''SELECT 
                      COUNT(*) as total_reviews,
                      COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                      AVG(rating) as avg_rating
                      FROM reviews''')
    reviews_stats = cursor.fetchone()
    
    # Статистика по предложкам
    cursor.execute('''SELECT 
                      COUNT(*) as total_offers,
                      COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_offers
                      FROM buy_offers''')
    offers_stats = cursor.fetchone()
    
    conn.close()
    
    text = (
        f"📊 <b>Расширенная статистика бота:</b>\n\n"
        f"👤 Пользователей: {users_count}\n"
        f"📦 Товаров в наличии: {goods_count}\n"
        f"👮 Админов: {admins_count}\n\n"
        f"⭐ <b>Отзывы:</b>\n"
        f"• Всего отзывов: {reviews_stats[0]}\n"
        f"• Одобрено: {reviews_stats[1]}\n"
        f"• Средний рейтинг: {reviews_stats[2]:.1f}/5\n\n"
        f"💰 <b>Предложки скупа:</b>\n"
        f"• Всего предложок: {offers_stats[0]}\n"
        f"• Ожидают решения: {offers_stats[1]}"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📢 Рассылка" and m.from_user.id in ADMIN_CACHE)
def broadcast_start(message):
    msg = bot.send_message(message.chat.id, "Введите текст (или фото с подписью) для рассылки:")
    bot.register_next_step_handler(msg, run_broadcast)

def run_broadcast(message):
    if message.text in ["🏠 В главное меню", "🔙 Назад в админку"]:
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
            bot.copy_message(user_id, message.chat.id, message.message_id)
            sent += 1
            time.sleep(0.05)
        except Exception as e:
            blocked += 1
            
    bot.edit_message_text(f"✅ Рассылка завершена!\n\nПолучили: {sent}\nЗаблокировали бота: {blocked}", 
                         message.chat.id, status_msg.message_id)

@bot.message_handler(func=lambda m: m.text == "🏠 В главное меню")
def back_home(message):
    if message.from_user.id in ADMIN_CACHE:
        bot.send_message(message.chat.id, "Главное меню", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "Главное меню", reply_markup=main_menu())

# --- ОТВЕТ АДМИНА (Reply) ---
@bot.message_handler(func=lambda m: m.reply_to_message is not None and m.from_user.id in ADMIN_CACHE)
def admin_reply(message):
    try:
        original_text = message.reply_to_message.text or message.reply_to_message.caption
        if not original_text:
            bot.reply_to(message, "❌ В сообщении нет текста с ID пользователя.")
            return
            
        match = re.search(r'ID: <code>(\d+)</code>', original_text)
        if not match:
            match = re.search(r'ID: (\d+)', original_text)
        
        if match:
            target_id = int(match.group(1))
            bot.send_message(target_id, f"🔔 <b>Ответ от поддержки:</b>\n\n{message.text}", parse_mode="HTML")
            bot.reply_to(message, "✅ Ответ доставлен пользователю.")
        else:
            bot.reply_to(message, "❌ Не удалось найти ID пользователя в сообщении.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка отправки: {e}")

# --- ЗАПУСК ---
if __name__ == '__main__':
    print("🔄 Инициализация базы данных...")
    init_db()
    
    print("🌐 Запуск Flask сервера...")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🤖 Запуск Telegram бота...")
    print("✅ Бот успешно запущен! Ожидание сообщений...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка полинга: {e}")
            print("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
