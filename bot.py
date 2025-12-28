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

# --- СЕРВЕР-ЗАГЛУШКА ДЛЯ RENDER ---
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
    db_query('''CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, target_user TEXT, target_id TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    db_query('''CREATE TABLE IF NOT EXISTS payments (payment_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, status TEXT DEFAULT 'pending', date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    db_query('''CREATE TABLE IF NOT EXISTS admin_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target_id INTEGER, details TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

init_db()

def log_admin_action(admin_id, action, target_id=None, details=""):
    db_query("INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?, ?, ?, ?)", 
             (admin_id, action, target_id, details))

# --- ИНТЕРФЕЙС ---
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    text = (f"<b>Личный кабинет</b>\n\nID: <code>{uid}</code>\nБаланс: {u['balance']} куриц\nРефералов: {u['referrals']}")
    kb = [
        [InlineKeyboardButton("Заказать курицу", callback_data="order_process")],
        [InlineKeyboardButton("Магазин", callback_data="shop_nav"), InlineKeyboardButton("Промокод", callback_data="promo_nav")],
        [InlineKeyboardButton("Партнерская программа", callback_data="ref_nav")],
        [InlineKeyboardButton("Связь (Оплата)", callback_data="support_nav")]
    ]
    if uid == ADMIN_ID: 
        kb.append([InlineKeyboardButton("Админ-панель", callback_data="adm_nav")])
    
    if update.callback_query:
        try: await update.callback_query.message.delete()
        except: pass
    await context.bot.send_photo(update.effective_chat.id, IMAGE_URL, caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# --- ОБРАБОТЧИК СООБЩЕНИЙ ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, text, state = update.effective_user.id, update.message.text, context.user_data.get("state")

    # Имитация заказа (Target)
    if state == "order_user":
        context.user_data["t_user"] = text
        context.user_data["state"] = "order_id"
        await update.message.reply_text("Введите адрес точки (ID):")
        return

    elif state == "order_id":
        t_user = context.user_data["t_user"]
        db_query("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
        db_query("INSERT INTO orders (user_id, target_user, target_id) VALUES (?, ?, ?)", (uid, t_user, text))
        
        context.user_data["state"] = None
        
        m = await update.message.reply_text(f"Запуск процесса доставки на {t_user}...")
        logs = [
            "Подключение к выделенному каналу... Успешно",
            f"Синхронизация данных с точкой {text}... OK",
            "Подготовка пакетов данных... Готово",
            "Передача в автоматическую систему обработки...",
            f"Точка {t_user} подтверждена в системе.",
            "Процесс завершен. Курица успешно отправлена."
        ]
        for log in logs:
            await asyncio.sleep(random.uniform(0.7, 1.4))
            await m.edit_text(f"<b>ПРОЦЕСС ЗАКАЗА: {t_user}</b>\n\n{log}", parse_mode='HTML')
        await main_menu(update, context)
        return

    # Промокоды
    elif state == "use_promo":
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (text.upper() if text else "",), fetchone=True)
        already = db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, text.upper()), fetchone=True)
        if p and not already:
            db_query("INSERT INTO activated_promos VALUES (?,?)", (uid, text.upper()))
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
            await update.message.reply_text(f"Промокод активен. +{p['reward']}")
        else:
            await update.message.reply_text("Ошибка ввода.")
        context.user_data["state"] = None
        await main_menu(update, context)
        return

    # Админка - расширенные функции
    elif uid == ADMIN_ID:
        # Выдача баланса
        if state == "adm_gv":
            try:
                tid, am = text.split()
                tid, am = int(tid), int(am)
                db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (am, tid))
                log_admin_action(uid, "give_balance", tid, f"Amount: {am}")
                await update.message.reply_text(f"Баланс пользователя {tid} изменен на {am} куриц.")
            except: 
                await update.message.reply_text("Ошибка. Формат: ID КОЛИЧЕСТВО")
        
        # Создание промокода
        elif state == "adm_p_new":
            try:
                c, r = text.split()
                c, r = c.upper(), int(r)
                db_query("INSERT OR REPLACE INTO promocodes VALUES (?,?)", (c, r))
                log_admin_action(uid, "create_promo", None, f"Code: {c}, Reward: {r}")
                await update.message.reply_text(f"Промокод {c} создан с наградой {r} куриц.")
            except:
                await update.message.reply_text("Ошибка. Формат: КОД КОЛИЧЕСТВО")
        
        # Поиск пользователя
        elif state == "adm_find":
            try:
                search = text
                if search.startswith('@'):
                    users = db_query("SELECT * FROM users WHERE username LIKE ?", (f"%{search[1:]}%",), fetchall=True)
                else:
                    try:
                        user_id = int(search)
                        users = db_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchall=True)
                    except:
                        users = db_query("SELECT * FROM users WHERE username LIKE ?", (f"%{search}%",), fetchall=True)
                
                if users:
                    response = "Найденные пользователи:\n\n"
                    for user in users[:10]:  # Ограничиваем 10 пользователями
                        response += f"ID: {user['user_id']}\nUsername: @{user['username'] if user['username'] else 'нет'}\nБаланс: {user['balance']} куриц\nРефералов: {user['referrals']}\n\n"
                    await update.message.reply_text(response)
                else:
                    await update.message.reply_text("Пользователь не найден.")
            except:
                await update.message.reply_text("Ошибка поиска.")
        
        # Рассылка
        elif state == "adm_broadcast":
            msg = text
            users = db_query("SELECT user_id FROM users", fetchall=True)
            total = len(users)
            success = 0
            failed = 0
            
            progress = await update.message.reply_text(f"Начинаю рассылку для {total} пользователей...")
            
            for i, user in enumerate(users):
                try:
                    await context.bot.send_message(user['user_id'], msg)
                    success += 1
                except:
                    failed += 1
                
                if i % 10 == 0:
                    await progress.edit_text(f"Рассылка... {int((i+1)/total*100)}%")
                
                await asyncio.sleep(0.1)
            
            await progress.edit_text(f"Рассылка завершена.\nУспешно: {success}\nНе удалось: {failed}")
        
        # Статистика
        elif state == "adm_stats":
            # Показать текущую статистику
            total_users = db_query("SELECT COUNT(*) as count FROM users", fetchone=True)['count']
            total_chickens = db_query("SELECT SUM(balance) as total FROM users", fetchone=True)['total'] or 0
            total_orders = db_query("SELECT COUNT(*) as count FROM orders", fetchone=True)['count']
            
            stats_text = f"📊 Статистика бота:\n\n"
            stats_text += f"👥 Всего пользователей: {total_users}\n"
            stats_text += f"🐔 Куриц на балансах: {total_chickens}\n"
            stats_text += f"📦 Всего заказов: {total_orders}\n"
            stats_text += f"👑 Админ ID: {ADMIN_ID}"
            
            await update.message.reply_text(stats_text)
        
        # Изменение баланса (с указанием +/-)
        elif state == "adm_set_balance":
            try:
                parts = text.split()
                if len(parts) == 2:
                    tid = int(parts[0])
                    new_balance = int(parts[1])
                    db_query("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, tid))
                    log_admin_action(uid, "set_balance", tid, f"New balance: {new_balance}")
                    await update.message.reply_text(f"Баланс пользователя {tid} установлен на {new_balance} куриц.")
                else:
                    await update.message.reply_text("Формат: ID БАЛАНС")
            except:
                await update.message.reply_text("Ошибка.")
        
        # Просмотр логов
        elif state == "adm_view_logs":
            try:
                count = int(text) if text.isdigit() else 10
                logs = db_query("SELECT * FROM admin_logs ORDER BY date DESC LIMIT ?", (count,), fetchall=True)
                
                if logs:
                    response = f"Последние {len(logs)} действий:\n\n"
                    for log in logs:
                        response += f"📅 {log['date']}\n👤 Admin: {log['admin_id']}\n"
                        response += f"🔧 Action: {log['action']}\n🎯 Target: {log['target_id'] or 'N/A'}\n"
                        response += f"📝 Details: {log['details']}\n"
                        response += "─" * 30 + "\n"
                    await update.message.reply_text(response[:4000])  # Ограничение Telegram
                else:
                    await update.message.reply_text("Логов нет.")
            except:
                await update.message.reply_text("Ошибка.")
    
    context.user_data["state"] = None

# --- ФОТО (СКРИНЫ) ---
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if context.user_data.get("state") == "wait_photo":
        pid = update.message.photo[-1].file_id
        db_query("INSERT INTO payments (user_id, amount, status) VALUES (?, ?, 'pending')", (uid, 0))
        
        kb = [
            [InlineKeyboardButton("+1", callback_data=f"aj_1_{uid}"), 
             InlineKeyboardButton("+5", callback_data=f"aj_5_{uid}"), 
             InlineKeyboardButton("+10", callback_data=f"aj_10_{uid}")],
            [InlineKeyboardButton("Отмена", callback_data=f"aj_0_{uid}")],
            [InlineKeyboardButton("Настроить сумму", callback_data=f"aj_custom_{uid}")]
        ]
        await context.bot.send_photo(ADMIN_ID, pid, caption=f"Заявка на пополнение от {uid}", reply_markup=InlineKeyboardMarkup(kb))
        await update.message.reply_text("Скриншот на проверке.")
        context.user_data["state"] = None

# --- КНОПКИ ---
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d, uid = q.data, update.effective_user.id
    await q.answer()

    if d == "main_menu": 
        await main_menu(update, context)
    
    elif d == "order_process":
        u = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if u['balance'] < 1: 
            await q.message.reply_text("Недостаточно куриц на балансе.")
        else:
            context.user_data["state"] = "order_user"
            await q.message.reply_text("Введите Username (объект доставки):")
    
    elif d == "shop_nav":
        btns = [[InlineKeyboardButton(f"Пакет {n} - {p['price']} звезд", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
        await q.message.reply_text("Магазин:", reply_markup=InlineKeyboardMarkup(btns + [[InlineKeyboardButton("Назад", callback_data="main_menu")]]))
    
    elif d.startswith("buy_"):
        await q.message.reply_text(f"Оплата: {OWNER_LINK}. Скриншот в раздел Связь.")
    
    elif d == "promo_nav":
        context.user_data["state"] = "use_promo"
        await q.message.reply_text("Введите промокод:")
    
    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"
        await q.message.reply_text("Пришлите скриншот оплаты:")
    
    elif d == "ref_nav":
        me = await context.bot.get_me()
        user = db_query("SELECT referrals FROM users WHERE user_id = ?", (uid,), fetchone=True)
        ref_count = user['referrals'] if user else 0
        await q.message.reply_text(f"Реферальная ссылка: t.me/{me.username}?start=ref{uid}\nПриглашено: {ref_count}\nБонус: 1 курица за 3 человека.")
    
    # АДМИН-ПАНЕЛЬ
    elif d == "adm_nav" and uid == ADMIN_ID:
        kb = [
            [InlineKeyboardButton("Выдать баланс", callback_data="adm_gv"), 
             InlineKeyboardButton("Установить баланс", callback_data="adm_set_balance")],
            [InlineKeyboardButton("Создать промокод", callback_data="adm_p_new"),
             InlineKeyboardButton("Поиск пользователя", callback_data="adm_find")],
            [InlineKeyboardButton("Рассылка", callback_data="adm_broadcast"),
             InlineKeyboardButton("Статистика", callback_data="adm_stats")],
            [InlineKeyboardButton("Просмотр логов", callback_data="adm_view_logs"),
             InlineKeyboardButton("Экспорт данных", callback_data="adm_export")],
            [InlineKeyboardButton("Назад", callback_data="main_menu")]
        ]
        await q.message.reply_text("Админ-панель:", reply_markup=InlineKeyboardMarkup(kb))
    
    elif d.startswith("adm_"):
        context.user_data["state"] = d
        if d == "adm_stats":
            await message_handler(update, context)
        elif d == "adm_export":
            await export_data(update, context)
        else:
            await q.message.reply_text("Введите данные:")
    
    # Обработка заявок на пополнение
    elif d.startswith("aj_"):
        parts = d.split("_")
        action = parts[1]
        target = parts[2] if len(parts) > 2 else None
        
        if action == "0":
            await q.message.edit_caption("Заявка отклонена.")
            try:
                await context.bot.send_message(target, "Ваша заявка на пополнение отклонена.")
            except: pass
        
        elif action == "custom" and target:
            context.user_data["custom_amount_user"] = target
            context.user_data["state"] = "adm_custom_amount"
            await q.message.reply_text("Введите сумму для начисления:")
        
        elif action.isdigit() and target:
            amount = int(action)
            db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target))
            log_admin_action(uid, "approve_payment", target, f"Amount: {amount}")
            await q.message.edit_caption(f"Заявка подтверждена. Начислено {amount} куриц.")
            try:
                await context.bot.send_message(target, f"Ваша заявка подтверждена. Начислено {amount} куриц.")
            except: pass

# --- ЭКСПОРТ ДАННЫХ ---
async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.from_user.id
    if uid != ADMIN_ID:
        return
    
    # Экспорт пользователей
    users = db_query("SELECT * FROM users", fetchall=True)
    orders = db_query("SELECT * FROM orders", fetchall=True)
    
    user_data = "Экспорт пользователей:\n\n"
    for user in users[:50]:  # Ограничиваем для телеграма
        user_data += f"ID: {user['user_id']}, Username: {user['username']}, Balance: {user['balance']}, Referrals: {user['referrals']}\n"
    
    order_data = "\n\nЭкспорт заказов:\n\n"
    for order in orders[:30]:
        order_data += f"ID: {order['order_id']}, User: {order['user_id']}, Target: {order['target_user']}, Date: {order['date']}\n"
    
    full_data = user_data + order_data
    
    if len(full_data) > 4000:
        chunks = [full_data[i:i+4000] for i in range(0, len(full_data), 4000)]
        for chunk in chunks[:3]:  # Максимум 3 сообщения
            await update.callback_query.message.reply_text(chunk)
    else:
        await update.callback_query.message.reply_text(full_data)
    
    log_admin_action(uid, "export_data", None, "Data exported")

# --- СТАРТ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True):
        db_query("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", 
                 (uid, update.effective_user.username, datetime.now()))
        if context.args and context.args[0].startswith("ref"):
            ref_id = context.args[0].replace("ref", "")
            if ref_id != str(uid):
                db_query("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                r = db_query("SELECT referrals FROM users WHERE user_id = ?", (ref_id,), fetchone=True)
                if r and r['referrals'] % 3 == 0: 
                    db_query("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
                    log_admin_action(ADMIN_ID, "ref_bonus", ref_id, "Bonus for 3 referrals")
    await main_menu(update, context)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.run_polling()

if __name__ == '__main__': 
    main()
