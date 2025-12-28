import sqlite3
import asyncio
import random
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8412845441:AAF0q65IIcFhlorCFth1g51hs1V8VCdIEek'
ADMIN_ID = 8292372344
OWNER_LINK = '@crollow'
# Идентификатор картинки на серверах Telegram
LOGOTYPE_ID = "AgACAgIAAxkBAAIBVmlQd4TXvXDjziFqWSxCVopU-OTJAALBDWsb5WmISmEglpfEAmP6AQADAgADeQADNgQ"

DB_NAME = 'chicken_bot.db'

PRICES = {
    "1": {"price": 15},
    "5": {"price": 25},
    "10": {"price": 50}
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
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
        logging.error(f"Database Error: {e}")
        return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0, reg_date TIMESTAMP)''')
    db_query('''CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward INTEGER)''')
    db_query('''CREATE TABLE IF NOT EXISTS activated_promos (user_id INTEGER, code TEXT)''')
    db_query('''CREATE TABLE IF NOT EXISTS referral_log (referrer_id INTEGER, referred_id INTEGER PRIMARY KEY)''')

init_db()

# --- ОСНОВНОЙ ИНТЕРФЕЙС ---
async def send_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb=None):
    try:
        if update.callback_query:
            await update.callback_query.message.delete()
        
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=LOGOTYPE_ID,
            caption=text,
            reply_markup=kb,
            parse_mode='HTML'
        )
    except Exception as e:
        logging.error(f"Interface Error: {e}")
        # Резервный метод отправки текста при ошибке фото
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode='HTML')

# --- ОБРАБОТЧИКИ КОМАНД ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = f"@{update.effective_user.username}" if update.effective_user.username else str(uid)
    
    if not db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", (uid, uname, datetime.now()))
        # Реферальная система
        if context.args and context.args[0].startswith("ref"):
            try:
                ref_id = int(context.args[0].replace("ref", ""))
                if ref_id != uid and not db_query("SELECT * FROM referral_log WHERE referred_id = ?", (uid,), fetchone=True):
                    db_query("INSERT INTO referral_log VALUES (?, ?)", (ref_id, uid))
                    db_query("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
            except (ValueError, TypeError): pass
    
    await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    
    text = (f"<b>Курочка от Кроллова</b>\n\n"
            f"ID: <code>{uid}</code>\n"
            f"Баланс: {u['balance']} шт.\n"
            f"Рефералы: {u['referrals']}")
    
    kb = [
        [InlineKeyboardButton("Заказать", callback_data="order_nav")],
        [InlineKeyboardButton("Магазин", callback_data="shop_nav"), InlineKeyboardButton("Промокод", callback_data="promo_nav")],
        [InlineKeyboardButton("Партнерам", callback_data="ref_nav")],
        [InlineKeyboardButton("Связь / Оплата", callback_data="support_nav")]
    ]
    if uid == ADMIN_ID:
        kb.append([InlineKeyboardButton("Админ-панель", callback_data="adm_nav")])
    
    await send_interface(update, context, text, InlineKeyboardMarkup(kb))

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    uid = update.effective_user.id

    if d == "main_menu":
        await main_menu(update, context)
    
    elif d == "order_nav":
        text = "С баланса будет списана 1 единица.\nПодтвердить запуск?"
        kb = [[InlineKeyboardButton("Подтвердить", callback_data="run_order")], [InlineKeyboardButton("Назад", callback_data="main_menu")]]
        await send_interface(update, context, text, InlineKeyboardMarkup(kb))

    elif d == "run_order":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1:
            await q.answer("❌ Недостаточно средств", show_alert=True)
            return
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        m = await q.message.reply_text("Обработка данных...")
        for p in [35, 70, 100]:
            await asyncio.sleep(1)
            await m.edit_text(f"Прогресс: {p}%\nНайдено совпадений: {random.randint(100,500)}")
        await m.reply_text("✅ Заказ выполнен.")
        await main_menu(update, context)

    elif d == "shop_nav":
        text = "<b>Магазин</b>\nВыберите количество для пополнения:"
        btns = [[InlineKeyboardButton(f"{n} шт. — {p['price']} Stars", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
        await send_interface(update, context, text, InlineKeyboardMarkup(btns + [[InlineKeyboardButton("Назад", callback_data="main_menu")]]))

    elif d.startswith("buy_"):
        p = d.split("_")[1]
        text = (f"<b>Оплата ({p} шт.)</b>\n\n"
                f"1. Перейдите в профиль: {OWNER_LINK}\n"
                f"2. Отправьте подарок за {PRICES[p]['price']} звезд.\n"
                f"3. Сделайте скриншот.\n"
                f"4. Нажмите кнопку 'Связь' и отправьте скриншот.")
        await send_interface(update, context, text, InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="shop_nav")]]))

    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"
        await q.message.reply_text("Отправьте скриншот подтверждения оплаты:")

    elif d == "promo_nav":
        context.user_data["state"] = "use_promo"
        await q.message.reply_text("Введите ваш промокод:")

    elif d == "ref_nav":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start=ref{uid}"
        text = f"<b>Партнерская программа</b>\n\nСсылка:\n<code>{link}</code>\n\nБонус: +1 шт. за каждые 3 приглашения."
        await send_interface(update, context, text, InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main_menu")]]))

    elif d == "adm_nav":
        if uid != ADMIN_ID: return
        u_count = db_query("SELECT COUNT(*) as c FROM users", fetchone=True)['c']
        kb = [[InlineKeyboardButton("Рассылка", callback_data="adm_bc")], [InlineKeyboardButton("Назад", callback_data="main_menu")]]
        await send_interface(update, context, f"Админ-панель\nПользователей: {u_count}", InlineKeyboardMarkup(kb))

    elif d.startswith("aj_"):
        _, val, target = d.split("_")
        if val != "rej":
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (val, target))
            try: await context.bot.send_message(target, f"✅ Оплата подтверждена. Начислено: {val} шт.")
            except: pass
        await q.message.edit_caption("Заявка обработана")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = context.user_data.get("state")

    if update.message.photo and state == "wait_photo":
        kb = [
            [InlineKeyboardButton("+1", callback_data=f"aj_1_{uid}"), InlineKeyboardButton("+5", callback_data=f"aj_5_{uid}"), InlineKeyboardButton("+10", callback_data=f"aj_10_{uid}")],
            [InlineKeyboardButton("Отклонить", callback_data=f"aj_rej_{uid}")]
        ]
        await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=f"Заявка от ID: {uid}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("Скриншот получен. Ожидайте подтверждения.")
        context.user_data["state"] = None

    elif update.message.text and state == "use_promo":
        code = update.message.text.upper()
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (code,), fetchone=True)
        if p and not db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, code), fetchone=True):
            db_query("INSERT INTO activated_promos VALUES (?,?)", (uid, code))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text(f"Промокод активирован: +{p['reward']} шт.")
        else:
            await update.message.reply_text("Ошибка: промокод неверен или уже использован.")
        context.user_data["state"] = None

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), message_handler))
    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
