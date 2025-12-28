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

# --- ЗАГЛУШКА ДЛЯ RENDER (БЕСПЛАТНЫЙ ТАРИФ) ---
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
async def send_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb=None):
    try:
        if update.callback_query:
            try: await update.callback_query.message.delete()
            except: pass
        await context.bot.send_photo(update.effective_chat.id, IMAGE_URL, caption=text, reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode='HTML')
        else: await update.message.reply_text(text, reply_markup=kb, parse_mode='HTML')

# --- ГЛАВНОЕ МЕНЮ ---
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    text = (f"<b>Личный кабинет</b>\n\nID: <code>{uid}</code>\nБаланс: {u['balance']} куриц\nРефералов: {u['referrals']}")
    kb = [
        [InlineKeyboardButton("Заказать курицу", callback_data="order_nav")],
        [InlineKeyboardButton("Магазин", callback_data="shop_nav"), InlineKeyboardButton("Промокод", callback_data="promo_nav")],
        [InlineKeyboardButton("Партнерская программа", callback_data="ref_nav")],
        [InlineKeyboardButton("Связь (Оплата)", callback_data="support_nav")]
    ]
    if uid == ADMIN_ID: kb.append([InlineKeyboardButton("Админ-панель", callback_data="adm_nav")])
    await send_interface(update, context, text, InlineKeyboardMarkup(kb))

# --- РОУТЕР ---
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d, uid = q.data, update.effective_user.id
    await q.answer()

    if d == "main_menu": await main_menu(update, context)
    elif d == "shop_nav":
        btns = [[InlineKeyboardButton(f"Пакет {n} - {p['price']} звезд", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
        await send_interface(update, context, "<b>Магазин</b>", InlineKeyboardMarkup(btns + [[InlineKeyboardButton("Назад", callback_data="main_menu")]]))
    elif d.startswith("buy_"):
        pack = d.split("_")[1]
        await send_interface(update, context, f"Оплата пакета {pack}. Отправьте {PRICES[pack]['price']} звезд {OWNER_LINK} и пришлите скриншот в раздел Связь.", InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="shop_nav")]]))
    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"; await q.message.reply_text("Пришлите скриншот оплаты:")
    elif d == "promo_nav":
        context.user_data["state"] = "use_p"; await q.message.reply_text("Введите промокод:")
    elif d == "order_nav":
        await send_interface(update, context, "Запустить процесс заказа? (1 курица)", InlineKeyboardMarkup([[InlineKeyboardButton("Старт", callback_data="run")]]))
    elif d == "run":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1: await q.message.reply_text("Недостаточно баланса"); return
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        m = await q.message.reply_text("Инициализация..."); await asyncio.sleep(1)
        for p in [35, 70, 100]:
            await m.edit_text(f"Прогресс: {p}%"); await asyncio.sleep(1)
        await m.reply_text("Заказ выполнен успешно"); await main_menu(update, context)
    elif d == "ref_nav":
        me = await context.bot.get_me()
        await send_interface(update, context, f"Ваша ссылка:\n<code>t.me/{me.username}?start=ref{uid}</code>\n\nБонус: 1 курица за каждых 3 друзей.", InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main_menu")]]))
    
    # АДМИН ПАНЕЛЬ
    elif d == "adm_nav" and uid == ADMIN_ID:
        u_count = db_query("SELECT COUNT(*) as c FROM users", fetchone=True)['c']
        kb = [
            [InlineKeyboardButton("Рассылка", callback_data="adm_bc")],
            [InlineKeyboardButton("Выдать баланс", callback_data="adm_gv"), InlineKeyboardButton("Сброс баланса", callback_data="adm_reset")],
            [InlineKeyboardButton("Создать промо", callback_data="adm_p_new"), InlineKeyboardButton("Удалить промо", callback_data="adm_p_del")],
            [InlineKeyboardButton("Назад", callback_data="main_menu")]
        ]
        await send_interface(update, context, f"<b>Администратор</b>\nПользователей: {u_count}", InlineKeyboardMarkup(kb))
    elif d.startswith("adm_") and uid == ADMIN_ID:
        context.user_data["state"] = d; await q.message.reply_text("Введите данные:")
    elif d.startswith("aj_") and uid == ADMIN_ID:
        _, act, target = d.split("_")
        if act != "rej": db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(act), target))
        await q.message.edit_caption(caption="Заявка обработана")

# --- СООБЩЕНИЯ ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, text, state = update.effective_user.id, update.message.text, context.user_data.get("state")

    if state == "wait_photo" and update.message.photo:
        pid = update.message.photo[-1].file_id
        kb = [[InlineKeyboardButton("+1", callback_data=f"aj_1_{uid}"), InlineKeyboardButton("+5", callback_data=f"aj_5_{uid}"), InlineKeyboardButton("+10", callback_data=f"aj_10_{uid}")], [InlineKeyboardButton("Отказ", callback_data=f"aj_rej_{uid}")]]
        await context.bot.send_photo(ADMIN_ID, pid, caption=f"Заявка от {uid}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("Скриншот отправлен администратору.")
    
    elif state == "use_p":
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (text.upper() if text else "",), fetchone=True)
        if p and not db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, text.upper()), fetchone=True):
            db_query("INSERT INTO activated_promos (user_id, code) VALUES (?,?)", (uid, text.upper()))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text(f"Успешно. Начислено: {p['reward']}")
        else: await update.message.reply_text("Код неверный или использован.")

    elif uid == ADMIN_ID and state:
        if state == "adm_bc":
            for u in db_query("SELECT user_id FROM users", fetchall=True):
                try: await context.bot.send_message(u['user_id'], text)
                except: pass
            await update.message.reply_text("Рассылка завершена")
        elif state == "adm_gv":
            try:
                i, a = text.split()
                db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (a, i))
                await update.message.reply_text("Баланс обновлен")
            except: pass
        elif state == "adm_reset":
            db_query("UPDATE users SET balance = 0 WHERE user_id = ?", (text,))
            await update.message.reply_text("Обнулено")
        elif state == "adm_p_new":
            try:
                c, r = text.split()
                db_query("INSERT INTO promocodes (code, reward) VALUES (?,?)", (c.upper(), r))
                await update.message.reply_text("Промокод создан")
            except: pass
        elif state == "adm_p_del":
            db_query("DELETE FROM promocodes WHERE code = ?", (text.upper(),))
            await update.message.reply_text("Удален")
    
    context.user_data["state"] = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = f"@{update.effective_user.username}" if update.effective_user.username else str(uid)
    if not db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", (uid, uname, datetime.now()))
        if context.args and context.args[0].startswith("ref"):
            ref_id = int(context.args[0].replace("ref", ""))
            if ref_id != uid and not db_query("SELECT * FROM referral_log WHERE referred_id = ?", (uid,), fetchone=True):
                db_query("INSERT INTO referral_log (referrer_id, referred_id) VALUES (?, ?)", (ref_id, uid))
                db_query("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                p = db_query("SELECT referrals FROM users WHERE user_id = ?", (ref_id,), fetchone=True)
                if p and p['referrals'] % 3 == 0: db_query("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
    await main_menu(update, context)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, message_handler))
    app.run_polling()

if __name__ == '__main__': main()
