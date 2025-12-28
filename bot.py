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

# --- СЕРВЕР ДЛЯ RENDER ---
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
    db_query('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        balance INTEGER DEFAULT 0, 
        referrals INTEGER DEFAULT 0, 
        reg_status INTEGER DEFAULT 0)''')
    db_query('''CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward INTEGER)''')
    db_query('''CREATE TABLE IF NOT EXISTS activated_promos (user_id INTEGER, code TEXT)''')
    db_query('''CREATE TABLE IF NOT EXISTS referral_log (referrer_id INTEGER, referred_id INTEGER PRIMARY KEY)''')

init_db()

# --- ОСНОВНОЙ ИНТЕРФЕЙС ---
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    
    text = (f"<b>CAMD SYSTEM v5</b>\n\n"
            f"Профиль: {u['username']}\n"
            f"ID в системе: {uid}\n"
            f"Баланс: {u['balance']} куриц\n"
            f"Рефералов: {u['referrals']}")
    
    kb = [
        [InlineKeyboardButton("Заказать курицу", callback_data="order_nav")],
        [InlineKeyboardButton("Магазин", callback_data="shop_nav"), InlineKeyboardButton("Промокод", callback_data="promo_nav")],
        [InlineKeyboardButton("Партнерская программа", callback_data="ref_nav")],
        [InlineKeyboardButton("Связь (Оплата)", callback_data="support_nav")]
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton("Админ-панель", callback_data="adm_nav")])
    
    try:
        if update.callback_query: await update.callback_query.message.delete()
        await context.bot.send_photo(update.effective_chat.id, IMAGE_URL, caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# --- СТАРТ И РЕГИСТРАЦИЯ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    
    # Сохраняем ID пригласившего, если он есть
    if context.args and context.args[0].startswith("ref"):
        context.user_data["pending_ref"] = context.args[0].replace("ref", "")

    if not user or user['reg_status'] == 0:
        context.user_data["state"] = "reg_name"
        await update.message.reply_text("Регистрация в системе.\nВведите ваш юзернейм:")
    else:
        await main_menu(update, context)

# --- ОБРАБОТЧИК СООБЩЕНИЙ (РЕГИСТРАЦИЯ, ПРОМО, АДМИНКА) ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    state = context.user_data.get("state")

    # Регистрация: Шаг 1
    if state == "reg_name":
        context.user_data["tmp_name"] = text
        context.user_data["state"] = "reg_id"
        await update.message.reply_text("Введите ваш айди:")
        return

    # Регистрация: Шаг 2
    elif state == "reg_id":
        full_name = f"{context.user_data['tmp_name']} (ID:{text})"
        db_query("INSERT OR REPLACE INTO users (user_id, username, reg_status) VALUES (?, ?, 1)", (uid, full_name))
        
        # Обработка реферала после регистрации
        ref_id = context.user_data.get("pending_ref")
        if ref_id and int(ref_id) != uid:
            if db_query("INSERT OR IGNORE INTO referral_log VALUES (?, ?)", (ref_id, uid)):
                db_query("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                r_data = db_query("SELECT referrals FROM users WHERE user_id = ?", (ref_id,), fetchone=True)
                if r_data and r_data['referrals'] % 3 == 0:
                    db_query("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
        
        await update.message.reply_text("Регистрация завершена.")
        context.user_data["state"] = None
        await main_menu(update, context)
        return

    # Ввод промокода
    elif state == "use_p":
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (text.upper() if text else "",), fetchone=True)
        if p and not db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, text.upper()), fetchone=True):
            db_query("INSERT INTO activated_promos VALUES (?,?)", (uid, text.upper()))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text(f"Код активирован. Начислено: {p['reward']}")
        else:
            await update.message.reply_text("Ошибка активации.")
        context.user_data["state"] = None
        return

    # Админские функции
    if uid == ADMIN_ID:
        if state == "adm_bc":
            users = db_query("SELECT user_id FROM users", fetchall=True)
            for u in users:
                try: await context.bot.send_message(u['user_id'], text)
                except: pass
            await update.message.reply_text("Рассылка завершена.")
        elif state == "adm_gv":
            try:
                target, amount = text.split()
                db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target))
                await update.message.reply_text("Баланс пополнен.")
            except: await update.message.reply_text("Ошибка. Формат: ID СУММА")
        elif state == "adm_p_new":
            try:
                c, r = text.split()
                db_query("INSERT INTO promocodes VALUES (?,?)", (c.upper(), r))
                await update.message.reply_text("Промокод создан.")
            except: pass
    
    context.user_data["state"] = None

# --- ОБРАБОТЧИК ФОТО (СКРИНШОТЫ ОПЛАТЫ) ---
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if context.user_data.get("state") == "wait_photo":
        pid = update.message.photo[-1].file_id
        kb = [
            [InlineKeyboardButton("+1", callback_data=f"aj_1_{uid}"), 
             InlineKeyboardButton("+5", callback_data=f"aj_5_{uid}"), 
             InlineKeyboardButton("+10", callback_data=f"aj_10_{uid}")],
            [InlineKeyboardButton("Отклонить", callback_data=f"aj_0_{uid}")]
        ]
        await context.bot.send_photo(ADMIN_ID, pid, caption=f"Заявка от {uid}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("Скриншот отправлен на проверку.")
        context.user_data["state"] = None

# --- ОБРАБОТЧИК КНОПОК ---
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d, uid = q.data, update.effective_user.id
    await q.answer()

    if d == "main_menu": await main_menu(update, context)
    elif d == "order_nav":
        await main_menu(update, context) # Или отдельное сообщение
        await q.message.reply_text("Списать 1 курицу и запустить заказ?", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Старт", callback_data="run")]]))
    elif d == "run":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1:
            await q.message.reply_text("Недостаточно баланса.")
            return
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        m = await q.message.reply_text("Инициализация...")
        for p in [35, 72, 100]:
            await asyncio.sleep(1)
            await m.edit_text(f"Выполнение: {p}%")
        await m.reply_text("Заказ завершен.")
    elif d == "shop_nav":
        btns = [[InlineKeyboardButton(f"Пакет {n} - {p['price']} звезд", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
        await q.message.reply_text("Выберите пакет:", reply_markup=InlineKeyboardMarkup(btns + [[InlineKeyboardButton("Назад", callback_data="main_menu")]]))
    elif d.startswith("buy_"):
        await q.message.reply_text(f"Переведите звезды {OWNER_LINK} и отправьте скриншот в раздел Связь.")
    elif d == "promo_nav":
        context.user_data["state"] = "use_p"
        await q.message.reply_text("Введите промокод:")
    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"
        await q.message.reply_text("Пришлите скриншот оплаты:")
    elif d == "ref_nav":
        me = await context.bot.get_me()
        await q.message.reply_text(f"Ссылка:\nt.me/{me.username}?start=ref{uid}\n\nБонус: 1 курица за 3 приглашенных.")
    
    # Админка
    elif d == "adm_nav" and uid == ADMIN_ID:
        kb = [[InlineKeyboardButton("Рассылка", callback_data="adm_bc")],
              [InlineKeyboardButton("Выдать баланс", callback_data="adm_gv")],
              [InlineKeyboardButton("Создать промо", callback_data="adm_p_new")]]
        await q.message.reply_text("Админ-панель:", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("adm_"):
        context.user_data["state"] = d
        await q.message.reply_text("Введите данные:")
    elif d.startswith("aj_"):
        _, am, target = d.split("_")
        if am != "0":
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (am, target))
            try: await context.bot.send_message(target, f"Заявка одобрена. Начислено: {am}")
            except: pass
        await q.message.edit_caption("Обработано")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()

if __name__ == '__main__': main()
