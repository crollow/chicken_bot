import logging
import sqlite3
import asyncio
import os
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8412845441:AAF0q65IIcFhlorCFth1g51hs1V8VCdIEek'
ADMIN_ID = 8292372344
OWNER_LINK = '@crollow'
# Исправлено для сервера
DB_NAME = 'chicken_bot.db'
IMAGE_URL = 'https://i.postimg.cc/8zLPh2nb/hhh.png'

PRICES = {
    "1": {"price": 15},
    "5": {"price": 25},
    "10": {"price": 50}
}

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
        user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0, reg_date TIMESTAMP)''')
    db_query('''CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward INTEGER)''')
    db_query('''CREATE TABLE IF NOT EXISTS activated_promos (user_id INTEGER, code TEXT)''')
    db_query('''CREATE TABLE IF NOT EXISTS referral_log (referrer_id INTEGER, referred_id INTEGER PRIMARY KEY)''')

init_db()

# --- ИНТЕРФЕЙС ---
async def send_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb=None):
    try:
        if update.callback_query:
            await update.callback_query.message.delete()
        await context.bot.send_photo(update.effective_chat.id, IMAGE_URL, caption=text, reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Send Error: {e}")
        if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode='HTML')
        else: await update.message.reply_text(text, reply_markup=kb, parse_mode='HTML')

# --- СТАРТ И МЕНЮ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = f"@{update.effective_user.username}" if update.effective_user.username else str(uid)
    user = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if not user:
        db_query("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", (uid, uname, datetime.now()))
        if context.args and context.args[0].startswith("ref"):
            try:
                ref_id = int(context.args[0].replace("ref", ""))
                if ref_id != uid and not db_query("SELECT * FROM referral_log WHERE referred_id = ?", (uid,), fetchone=True):
                    db_query("INSERT INTO referral_log VALUES (?, ?)", (ref_id, uid))
                    db_query("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                    p = db_query("SELECT referrals FROM users WHERE user_id = ?", (ref_id,), fetchone=True)
                    if p['referrals'] % 3 == 0:
                        db_query("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
                        try: await context.bot.send_message(ref_id, "Бонус: +1 курица за 3 друзей.")
                        except: pass
            except: pass
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    text = (f"<b>Личный кабинет</b>\n\n"
            f"Ваш ID: <code>{uid}</code>\n"
            f"Баланс: {u['balance']} куриц\n"
            f"Рефералов: {u['referrals']}\n\n"
            f"Используйте кнопки ниже для управления.")
    kb = [
        [InlineKeyboardButton("Заказать курицу", callback_data="order_nav")],
        [InlineKeyboardButton("Магазин", callback_data="shop_nav"), InlineKeyboardButton("Промокод", callback_data="promo_nav")],
        [InlineKeyboardButton("Партнерская программа", callback_data="ref_nav")],
        [InlineKeyboardButton("Связь (Оплата/Спамблок)", callback_data="support_nav")]
    ]
    if uid == ADMIN_ID: kb.append([InlineKeyboardButton("Админ-панель", callback_data="adm_nav")])
    await send_interface(update, context, text, InlineKeyboardMarkup(kb))

# --- МАГАЗИН ---
async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Выберите пакет для покупки:"
    btns = [[InlineKeyboardButton(f"Пакет {n} - {p['price']} звезд", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
    await send_interface(update, context, text, InlineKeyboardMarkup(btns + [[InlineKeyboardButton("Назад", callback_data="main_menu")]]))

async def buy_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE, pack):
    price = PRICES[pack]['price']
    text = (f"<b>Инструкция по оплате (Пакет {pack})</b>\n\n"
            f"Цена: {price} звезд\n\n"
            f"1. Перейдите в профиль: {OWNER_LINK}\n"
            f"2. Отправьте подарок стоимостью {price} звезд.\n"
            f"3. Сделайте скриншот отправки.\n"
            f"4. Вернитесь в бота, нажмите кнопку Связь и пришлите фото.\n\n"
            f"Это работает даже со спамблоком!")
    await send_interface(update, context, text, InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="shop_nav")]]))

# --- АДМИН-ПАНЕЛЬ ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    u_count = db_query("SELECT COUNT(*) as c FROM users", fetchone=True)['c']
    p_count = db_query("SELECT COUNT(*) as c FROM promocodes", fetchone=True)['c']
    text = (f"<b>Управление проектом</b>\n\n"
            f"Пользователей: {u_count}\n"
            f"Активных промо: {p_count}\n\n"
            f"Выберите инструмент:")
    kb = [
        [InlineKeyboardButton("Рассылка (Текст)", callback_data="adm_bc")],
        [InlineKeyboardButton("Выдать баланс", callback_data="adm_gv"), InlineKeyboardButton("Сбросить баланс", callback_data="adm_reset")],
        [InlineKeyboardButton("Создать промо", callback_data="adm_p_new"), InlineKeyboardButton("Удалить промо", callback_data="adm_p_del")],
        [InlineKeyboardButton("Назад", callback_data="main_menu")]
    ]
    await send_interface(update, context, text, InlineKeyboardMarkup(kb))

# --- ОБРАБОТЧИКИ ---
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    if state == "wait_photo" and update.message.photo:
        photo_id = update.message.photo[-1].file_id
        kb = [[InlineKeyboardButton("+1", callback_data=f"aj_1_{uid}"), InlineKeyboardButton("+5", callback_data=f"aj_5_{uid}"), InlineKeyboardButton("+10", callback_data=f"aj_10_{uid}")],
              [InlineKeyboardButton("Отклонить", callback_data=f"aj_rej_{uid}")]]
        await context.bot.send_photo(ADMIN_ID, photo_id, caption=f"Заявка от ID: {uid}\nЮзер: @{update.effective_user.username}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        await update.message.reply_text("Скриншот получен. Ожидайте проверки.")
        context.user_data["state"] = None

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    uid = update.effective_user.id
    if d == "main_menu": await main_menu(update, context)
    elif d == "shop_nav": await shop_menu(update, context)
    elif d.startswith("buy_"): await buy_tutorial(update, context, d.split("_")[1])
    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"
        await q.message.reply_text("Пришлите скриншот отправленного подарка:")
    elif d.startswith("aj_"):
        _, act, target = d.split("_")
        if act == "rej":
            try: await context.bot.send_message(target, "Ваша заявка отклонена.")
            except: pass
            await q.message.edit_caption("Отклонено")
        else:
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (act, target))
            try: await context.bot.send_message(target, f"Заявка одобрена! Начислено {act} куриц.")
            except: pass
            await q.message.edit_caption(f"Начислено {act} куриц")
    elif d == "adm_nav": await admin_panel(update, context)
    elif d == "adm_bc": context.user_data["state"] = "adm_bc"; await q.message.reply_text("Введите текст рассылки:")
    elif d == "adm_gv": context.user_data["state"] = "adm_gv"; await q.message.reply_text("Введите: ID СУММА")
    elif d == "adm_reset": context.user_data["state"] = "adm_reset"; await q.message.reply_text("Введите ID для обнуления:")
    elif d == "adm_p_new": context.user_data["state"] = "adm_p_new"; await q.message.reply_text("Введите: КОД СУММА")
    elif d == "adm_p_del": context.user_data["state"] = "adm_p_del"; await q.message.reply_text("Введите КОД для удаления:")
    elif d == "order_nav":
        await send_interface(update, context, "Запустить процесс заказа?", InlineKeyboardMarkup([[InlineKeyboardButton("Старт", callback_data="run")], [InlineKeyboardButton("Назад", callback_data="main_menu")]]))
    elif d == "run":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1: await q.answer("Баланс 0!", show_alert=True); return
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        m = await q.message.reply_text("Сбор данных..."); await asyncio.sleep(1)
        for p in [30, 70, 100]:
            await asyncio.sleep(1); await m.edit_text(f"Прогресс: {p}%\nСессии: 412\nУспешно: {random.randint(300,400)}")
        await m.reply_text("Заказ выполнен."); await main_menu(update, context)
    elif d == "promo_nav": context.user_data["state"] = "use_p"; await q.message.reply_text("Введите код:")
    elif d == "ref_nav":
        me = await context.bot.get_me()
        await send_interface(update, context, f"Ваша ссылка:\n<code>t.me/{me.username}?start=ref{uid}</code>\n\n+1 курица за 3 друзей.", InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main_menu")]]))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, text, state = update.effective_user.id, update.message.text, context.user_data.get("state")
    if state == "use_p":
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (text.upper() if text else "",), fetchone=True)
        if p and not db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, text.upper()), fetchone=True):
            db_query("INSERT INTO activated_promos VALUES (?,?)", (uid, text.upper()))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text("Успешно!")
        else: await update.message.reply_text("Неверно или уже использовано.")
    elif uid == ADMIN_ID:
        if state == "adm_bc":
            us = db_query("SELECT user_id FROM users", fetchall=True)
            for u in us:
                try: await context.bot.send_message(u['user_id'], text)
                except: pass
            await update.message.reply_text("Рассылка готова.")
        elif state == "adm_gv":
            try: i, a = text.split(); db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (a, i)); await update.message.reply_text("Выдано.")
            except: pass
        elif state == "adm_reset":
            db_query("UPDATE users SET balance = 0 WHERE user_id = ?", (text,))
            await update.message.reply_text("Обнулено.")
        elif state == "adm_p_new":
            try: c, r = text.split(); db_query("INSERT INTO promocodes VALUES (?,?)", (c.upper(), r)); await update.message.reply_text("Создан.")
            except: pass
        elif state == "adm_p_del":
            db_query("DELETE FROM promocodes WHERE code = ?", (text.upper(),))
            await update.message.reply_text("Удален.")
    context.user_data["state"] = None

def main():
    app = Application.builder().token(BOT_TOKEN).request(HTTPXRequest(connect_timeout=20)).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, media_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == '__main__': main()
