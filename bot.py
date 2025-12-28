import logging
import sqlite3
import asyncio
import os
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8412845441:AAF0q65IIcFhlorCFth1g51hs1V8VCdIEek'
ADMIN_ID = 8292372344
OWNER_LINK = '@crollow'
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
            try: await update.callback_query.message.delete()
            except: pass
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
                    if p and p['referrals'] % 3 == 0:
                        db_query("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
                        try: await context.bot.send_message(ref_id, "<b>Бонус:</b> +1 курица за 3 приглашенных друзей! 🍗")
                        except: pass
            except: pass
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    text = (f"<b>Личный кабинет</b>\n\n"
            f"Ваш ID: <code>{uid}</code>\n"
            f"Баланс: <b>{u['balance']} куриц</b>\n"
            f"Рефералов: {u['referrals']}\n\n"
            f"Используйте кнопки ниже:")
    kb = [
        [InlineKeyboardButton("🍗 Заказать курицу", callback_data="order_nav")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="shop_nav"), InlineKeyboardButton("🎟 Промокод", callback_data="promo_nav")],
        [InlineKeyboardButton("👥 Партнерка", callback_data="ref_nav")],
        [InlineKeyboardButton("📞 Связь (Оплата)", callback_data="support_nav")]
    ]
    if uid == ADMIN_ID: kb.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="adm_nav")])
    await send_interface(update, context, text, InlineKeyboardMarkup(kb))

# --- ОБРАБОТЧИК КНОПОК (РОУТЕР) ---
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    uid = update.effective_user.id
    await q.answer()

    if d == "main_menu": await main_menu(update, context)
    
    elif d == "shop_nav":
        btns = [[InlineKeyboardButton(f"Пакет {n} - {p['price']} звезд", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
        await send_interface(update, context, "<b>Магазин куриц</b>\n\nВыберите нужный пакет:", InlineKeyboardMarkup(btns + [[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]))

    elif d.startswith("buy_"):
        pack = d.split("_")[1]
        price = PRICES[pack]['price']
        text = (f"<b>Оплата Пакета {pack}</b>\n\nЦена: {price} звезд\n\n1. Перейдите к {OWNER_LINK}\n2. Отправьте ПОДАРОК ({price} звезд)\n3. Сделайте скриншот\n4. Нажмите 'Связь' и пришлите фото.")
        await send_interface(update, context, text, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="shop_nav")]]))

    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"
        await q.message.reply_text("Отправьте скриншот оплаты (подарка):")

    elif d == "order_nav":
        await send_interface(update, context, "Запустить процесс заказа?\n(Спишется 1 курица)", InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Старт", callback_data="run")], [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]))

    elif d == "run":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1: await q.message.reply_text("❌ Недостаточно куриц на балансе!"); return
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        m = await q.message.reply_text("⏳ Подключение к сессиям..."); await asyncio.sleep(1)
        for p in [35, 72, 100]:
            await asyncio.sleep(1); await m.edit_text(f"⚙️ Прогресс: {p}%\nОбработка потоков...")
        await m.reply_text("✅ Заказ успешно выполнен!"); await main_menu(update, context)

    elif d == "promo_nav":
        context.user_data["state"] = "use_p"
        await q.message.reply_text("Введите ваш промокод:")

    elif d == "ref_nav":
        me = await context.bot.get_me()
        link = f"t.me/{me.username}?start=ref{uid}"
        await send_interface(update, context, f"<b>Партнерская программа</b>\n\nВаша ссылка:\n<code>{link}</code>\n\nПриглашайте друзей! За каждых 3-х друзей вы получаете +1 курицу.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]))

    # Админские действия (Заявки)
    elif d.startswith("aj_") and uid == ADMIN_ID:
        _, act, target = d.split("_")
        if act == "rej":
            try: await context.bot.send_message(target, "❌ Ваша заявка на пополнение отклонена.")
            except: pass
            await q.message.edit_caption(caption="Заявка отклонена")
        else:
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(act), target))
            try: await context.bot.send_message(target, f"✅ Заявка одобрена! Вам начислено {act} куриц.")
            except: pass
            await q.message.edit_caption(caption=f"Одобрено: +{act}")

    elif d == "adm_nav" and uid == ADMIN_ID:
        u_count = db_query("SELECT COUNT(*) as c FROM users", fetchone=True)['c']
        kb = [[InlineKeyboardButton("📢 Текст-рассылка", callback_data="adm_bc"), InlineKeyboardButton("🖼 Фото-рассылка", callback_data="adm_bc_photo")],
              [InlineKeyboardButton("➕ Выдать баланс", callback_data="adm_gv")], [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]
        await send_interface(update, context, f"<b>Админ-панель</b>\nЮзеров в базе: {u_count}", InlineKeyboardMarkup(kb))

    elif d == "adm_bc": context.user_data["state"] = "adm_bc"; await q.message.reply_text("Введите текст для всех:")
    elif d == "adm_bc_photo": context.user_data["state"] = "adm_bc_photo"; await q.message.reply_text("Пришлите фото с текстом:")
    elif d == "adm_gv": context.user_data["state"] = "adm_gv"; await q.message.reply_text("Введите: ID СУММА")

# --- ОБРАБОТЧИК СООБЩЕНИЙ ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")
    text = update.message.text

    if state == "wait_photo" and update.message.photo:
        pid = update.message.photo[-1].file_id
        kb = [[InlineKeyboardButton("✅ +1", callback_data=f"aj_1_{uid}"), InlineKeyboardButton("✅ +5", callback_data=f"aj_5_{uid}"), InlineKeyboardButton("✅ +10", callback_data=f"aj_10_{uid}")], [InlineKeyboardButton("❌ Отказать", callback_data=f"aj_rej_{uid}")]]
        await context.bot.send_photo(ADMIN_ID, pid, caption=f"Заявка от {uid} (@{update.effective_user.username})", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("✅ Скриншот отправлен админу. Ожидайте.")
    
    elif state == "use_p":
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (text.upper(),), fetchone=True)
        if p and not db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, text.upper()), fetchone=True):
            db_query("INSERT INTO activated_promos VALUES (?,?)", (uid, text.upper()))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text(f"✅ Активировано! +{p['reward']} куриц.")
        else: await update.message.reply_text("❌ Код неверный или уже использован.")

    elif uid == ADMIN_ID:
        if state == "adm_bc":
            us = db_query("SELECT user_id FROM users", fetchall=True)
            for u in us:
                try: await context.bot.send_message(u['user_id'], text)
                except: pass
            await update.message.reply_text("✅ Рассылка завершена.")
        elif state == "adm_gv":
            try:
                target, amount = text.split()
                db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target))
                await update.message.reply_text(f"✅ Пользователю {target} выдано {amount} куриц.")
            except: await update.message.reply_text("Ошибка. Формат: ID СУММА")
    
    context.user_data["state"] = None

def main():
    app = Application.builder().token(BOT_TOKEN).request(HTTPXRequest(connect_timeout=20)).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, message_handler))
    print("CAMD SYSTEM v5: STARTED")
    app.run_polling()

if __name__ == '__main__': main()
