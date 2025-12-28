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
from telegram.request import HTTPXRequest

# --- МИНИ-СЕРВЕР ДЛЯ ОБХОДА ОШИБКИ RENDER ---
def run_dummy_server():
    # Render автоматически назначает порт. Если его нет, берем 10000
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    # Позволяем повторное использование порта, чтобы не было ошибок при перезагрузке
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        print(f"Ошибка сервера-заглушки: {e}")

# Запускаем в отдельном потоке, чтобы бот работал параллельно
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
async def send_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb=None):
    try:
        if update.callback_query:
            try: await update.callback_query.message.delete()
            except: pass
        await context.bot.send_photo(update.effective_chat.id, IMAGE_URL, caption=text, reply_markup=kb, parse_mode='HTML')
    except:
        if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode='HTML')
        else: await update.message.reply_text(text, reply_markup=kb, parse_mode='HTML')

# --- ЛОГИКА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = f"@{update.effective_user.username}" if update.effective_user.username else str(uid)
    if not db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", (uid, uname, datetime.now()))
        # Рефералка
        if context.args and context.args[0].startswith("ref"):
            ref_id = int(context.args[0].replace("ref", ""))
            if ref_id != uid:
                db_query("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                p = db_query("SELECT referrals FROM users WHERE user_id = ?", (ref_id,), fetchone=True)
                if p and p['referrals'] % 3 == 0:
                    db_query("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    text = f"<b>Личный кабинет</b>\n\nID: <code>{uid}</code>\nБаланс: {u['balance']} куриц\nРефералов: {u['referrals']}"
    kb = [[InlineKeyboardButton("Заказать курицу", callback_data="order_nav")],
          [InlineKeyboardButton("Магазин", callback_data="shop_nav"), InlineKeyboardButton("Промокод", callback_data="promo_nav")],
          [InlineKeyboardButton("Партнерская программа", callback_data="ref_nav")],
          [InlineKeyboardButton("Связь (Оплата)", callback_data="support_nav")]]
    if uid == ADMIN_ID: kb.append([InlineKeyboardButton("Админ-панель", callback_data="adm_nav")])
    await send_interface(update, context, text, InlineKeyboardMarkup(kb))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d, uid = q.data, update.effective_user.id
    await q.answer()
    if d == "main_menu": await main_menu(update, context)
    elif d == "order_nav":
        await send_interface(update, context, "Запустить процесс заказа?", InlineKeyboardMarkup([[InlineKeyboardButton("Старт", callback_data="run")]]))
    elif d == "run":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1: await q.message.reply_text("Баланс 0"); return
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        m = await q.message.reply_text("Запуск..."); await asyncio.sleep(1)
        await m.edit_text("Прогресс: 100%"); await m.reply_text("Заказ выполнен успешно."); await main_menu(update, context)
    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"; await q.message.reply_text("Пришлите скриншот оплаты:")
    elif d == "promo_nav":
        context.user_data["state"] = "use_p"; await q.message.reply_text("Введите промокод:")
    elif d == "adm_nav" and uid == ADMIN_ID:
        kb = [[InlineKeyboardButton("Выдать баланс", callback_data="adm_gv")], [InlineKeyboardButton("Назад", callback_data="main_menu")]]
        await send_interface(update, context, "Админ-панель", InlineKeyboardMarkup(kb))
    elif d == "adm_gv":
        context.user_data["state"] = "adm_gv"; await q.message.reply_text("Введите: ID СУММА")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, text, state = update.effective_user.id, update.message.text, context.user_data.get("state")
    if state == "wait_photo" and update.message.photo:
        await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=f"Заявка от {uid}")
        await update.message.reply_text("Скриншот отправлен админу.")
    elif state == "use_p":
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (text.upper() if text else "",), fetchone=True)
        if p:
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text("Промокод активирован.")
    elif state == "adm_gv" and uid == ADMIN_ID:
        try:
            i, a = text.split()
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (a, i))
            await update.message.reply_text("Баланс обновлен.")
        except: pass
    context.user_data["state"] = None

def main():
    # Используем таймауты для стабильности
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, message_handler))
    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__': main()
