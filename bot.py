import logging
import sqlite3
import asyncio
import os
import random
import http.server
import socketserver
import threading
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# --- СЕРВЕР ДЛЯ ОБХОДА ОШИБКИ ПОРТА RENDER ---
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            httpd.serve_forever()
    except: pass

threading.Thread(target=run_dummy_server, daemon=True).start()

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8412845441:AAF0q65IIcFhlorCFth1g51hs1V8VCdIEek'
ADMIN_ID = 8292372344
OWNER_LINK = '@crollow'
DB_NAME = 'chicken_bot.db'
IMAGE_URL = 'https://i.postimg.cc/8zLPh2nb/hhh.png'

PRICES = {"1": {"price": 15}, "5": {"price": 25}, "10": {"price": 50}}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- БАЗА ДАННЫХ ---
def db_query(sql, params=(), fetchone=False, fetchall=False):
    try:
        with sqlite3.connect(DB_NAME, timeout=20) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql, params)
            if fetchone: return cur.fetchone()
            if fetchall: return cur.fetchall()
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0, reg_date TIMESTAMP)''')
    db_query('''CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward INTEGER)''')
    db_query('''CREATE TABLE IF NOT EXISTS activated_promos (user_id INTEGER, code TEXT)''')
    db_query('''CREATE TABLE IF NOT EXISTS referral_log (referrer_id INTEGER, referred_id INTEGER PRIMARY KEY)''')

init_db()

# --- ИНТЕРФЕЙС ---
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    text = (f"<b>CAMD SYSTEM v5</b>\n\nID: <code>{uid}</code>\nБаланс: {u['balance']} куриц\nРефералов: {u['referrals']}")
    kb = [
        [InlineKeyboardButton("Заказать курицу", callback_data="target_start")],
        [InlineKeyboardButton("Магазин", callback_data="shop_nav"), InlineKeyboardButton("Промокод", callback_data="promo_nav")],
        [InlineKeyboardButton("Партнерская программа", callback_data="ref_nav")],
        [InlineKeyboardButton("Связь (Оплата)", callback_data="support_nav")]
    ]
    if uid == ADMIN_ID: kb.append([InlineKeyboardButton("Админ-панель", callback_data="adm_nav")])
    
    if update.callback_query:
        try: await update.callback_query.message.delete()
        except: pass
    await context.bot.send_photo(update.effective_chat.id, IMAGE_URL, caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# --- ЛОГИКА ТЕКСТОВЫХ СООБЩЕНИЙ ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, text, state = update.effective_user.id, update.message.text, context.user_data.get("state")

    # Имитация Target (Снос)
    if state == "target_user":
        context.user_data["t_user"] = text
        context.user_data["state"] = "target_id"
        await update.message.reply_text("Введите ID цели:")
        return

    elif state == "target_id":
        t_user = context.user_data["t_user"]
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        context.user_data["state"] = None
        
        m = await update.message.reply_text(f"Запуск протокола на {t_user}...")
        logs = [
            "Подключение к прокси-серверам... OK",
            f"Анализ уязвимостей сессий {text}... Готово",
            "Обход защиты Telegram Cloud... Успешно",
            "Запуск массовой рассылки жалоб (Report Flood)...",
            f"Аккаунт {t_user} помечен как ToS Violation.",
            "Процесс завершен. Ожидайте блокировки в течение 24 часов."
        ]
        for log in logs:
            await asyncio.sleep(random.uniform(1, 2))
            await m.edit_text(f"<b>TARGET: {t_user}</b>\n\n{log}", parse_mode='HTML')
        await main_menu(update, context)
        return

    # Активация промокода
    elif state == "use_promo":
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (text.upper() if text else "",), fetchone=True)
        already = db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, text.upper()), fetchone=True)
        if p and not already:
            db_query("INSERT INTO activated_promos VALUES (?,?)", (uid, text.upper()))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text(f"Успешно. Начислено: {p['reward']}")
        else:
            await update.message.reply_text("Код недействителен.")
        context.user_data["state"] = None
        await main_menu(update, context)
        return

    # Админка: Выдача баланса
    elif uid == ADMIN_ID and state == "adm_gv":
        try:
            target_id, amount = text.split()
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
            await update.message.reply_text("Баланс изменен.")
        except: await update.message.reply_text("Ошибка. Формат: ID СУММА")
        context.user_data["state"] = None
        return

    # Админка: Создание промо
    elif uid == ADMIN_ID and state == "adm_p_new":
        try:
            c, r = text.split()
            db_query("INSERT INTO promocodes VALUES (?,?)", (c.upper(), r))
            await update.message.reply_text("Промокод создан.")
        except: pass
        context.user_data["state"] = None
        return

# --- ФОТО (ЗАЯВКИ НА ОПЛАТУ) ---
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if context.user_data.get("state") == "wait_photo":
        pid = update.message.photo[-1].file_id
        kb = [[InlineKeyboardButton("+1", callback_data=f"aj_1_{uid}"), InlineKeyboardButton("+5", callback_data=f"aj_5_{uid}")],
              [InlineKeyboardButton("Отказ", callback_data=f"aj_0_{uid}")]]
        await context.bot.send_photo(ADMIN_ID, pid, caption=f"Заявка от {uid}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("Скриншот отправлен.")
        context.user_data["state"] = None

# --- РОУТЕР КНОПОК ---
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d, uid = q.data, update.effective_user.id
    await q.answer()

    if d == "main_menu": await main_menu(update, context)
    elif d == "target_start":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1:
            await q.message.reply_text("Баланс пуст.")
        else:
            context.user_data["state"] = "target_user"
            await q.message.reply_text("Введите Username цели:")
    elif d == "shop_nav":
        btns = [[InlineKeyboardButton(f"Пакет {n} - {p['price']} звезд", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
        await q.message.reply_text("Магазин:", reply_markup=InlineKeyboardMarkup(btns + [[InlineKeyboardButton("Назад", callback_data="main_menu")]]))
    elif d.startswith("buy_"):
        await q.message.reply_text(f"Оплата: {OWNER_LINK}. Пришлите скриншот в Связь.")
    elif d == "promo_nav":
        context.user_data["state"] = "use_promo"
        await q.message.reply_text("Введите код:")
    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"
        await q.message.reply_text("Пришлите скриншот:")
    elif d == "ref_nav":
        me = await context.bot.get_me()
        await q.message.reply_text(f"Ваша ссылка: t.me/{me.username}?start=ref{uid}")
    elif d == "adm_nav" and uid == ADMIN_ID:
        kb = [[InlineKeyboardButton("Выдать баланс", callback_data="adm_gv")],
              [InlineKeyboardButton("Создать промо", callback_data="adm_p_new")]]
        await q.message.reply_text("Админка:", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("adm_"):
        context.user_data["state"] = d
        await q.message.reply_text("Введите данные:")
    elif d.startswith("aj_"):
        _, am, target = d.split("_")
        if am != "0":
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (am, target))
            try: await context.bot.send_message(target, "Заявка одобрена.")
            except: pass
        await q.message.edit_caption("Готово.")

# --- СТАРТ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", (uid, update.effective_user.username, datetime.now()))
        if context.args and context.args[0].startswith("ref"):
            ref_id = context.args[0].replace("ref", "")
            if ref_id != str(uid):
                db_query("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                # Логика 3 к 1
                r = db_query("SELECT referrals FROM users WHERE user_id = ?", (ref_id,), fetchone=True)
                if r and r['referrals'] % 3 == 0:
                    db_query("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
    await main_menu(update, context)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()

if __name__ == '__main__': main()
