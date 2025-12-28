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
BOT_TOKEN = '8412845441:AAHVumWT4MLo6GLiDu5AHmSXcRvjZ_DCxzA'
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
            if fetchone: 
                result = cur.fetchone()
            elif fetchall: 
                result = cur.fetchall()
            else:
                result = None
            conn.commit()  # ВАЖНО: коммитим ВСЕГДА
            return result
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0, reg_date TIMESTAMP)''')
    db_query('''CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, reward INTEGER)''')
    db_query('''CREATE TABLE IF NOT EXISTS activated_promos (user_id INTEGER, code TEXT, PRIMARY KEY(user_id, code))''')
    db_query('''CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, target_user TEXT, target_id TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    db_query('''CREATE TABLE IF NOT EXISTS admin_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target_id INTEGER, details TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

init_db()

def log_admin_action(admin_id, action, target_id=None, details=""):
    db_query("INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?, ?, ?, ?)", 
             (admin_id, action, target_id, details))

# --- ИНТЕРФЕЙС ---
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = db_query("SELECT * FROM users WHERE user_id = ?", (uid,), fetchone=True)
    if not u:
        # Создаем пользователя если не существует
        username = update.effective_user.username or str(uid)
        db_query("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", 
                 (uid, username, datetime.now()))
        u = {'balance': 0, 'referrals': 0}
    else:
        u = dict(u)
    
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
        try: 
            await update.callback_query.message.delete()
        except: 
            pass
    await context.bot.send_photo(update.effective_chat.id, IMAGE_URL, caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

# --- ОБРАБОТЧИК СООБЩЕНИЙ ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, text, state = update.effective_user.id, update.message.text.strip(), context.user_data.get("state")

    # Имитация заказа (Target)
    if state == "order_user":
        context.user_data["t_user"] = text
        context.user_data["state"] = "order_id"
        await update.message.reply_text("Введите адрес точки (ID):")
        return

    elif state == "order_id":
        t_user = context.user_data["t_user"]
        
        # Проверяем баланс
        user = db_query("SELECT balance FROM users WHERE user_id = ?", (uid,), fetchone=True)
        if not user or user['balance'] < 1:
            await update.message.reply_text("❌ Недостаточно куриц на балансе!")
            context.user_data["state"] = None
            await main_menu(update, context)
            return
        
        # Списание баланса и запись заказа В ОДНОЙ ТРАНЗАКЦИИ
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        try:
            cur.execute("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (uid,))
            cur.execute("INSERT INTO orders (user_id, target_user, target_id) VALUES (?, ?, ?)", (uid, t_user, text))
            conn.commit()
            success = True
        except:
            conn.rollback()
            success = False
        finally:
            conn.close()
        
        if not success:
            await update.message.reply_text("❌ Ошибка при обработке заказа!")
            context.user_data["state"] = None
            await main_menu(update, context)
            return
        
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
        promo_code = text.upper()
        p = db_query("SELECT * FROM promocodes WHERE code = ?", (promo_code,), fetchone=True)
        already = db_query("SELECT * FROM activated_promos WHERE user_id=? AND code=?", (uid, promo_code), fetchone=True)
        
        if p and not already:
            # Активация промокода в транзакции
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO activated_promos VALUES (?,?)", (uid, promo_code))
                cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (p['reward'], uid))
                conn.commit()
                await update.message.reply_text(f"✅ Промокод активирован! +{p['reward']} куриц")
            except:
                conn.rollback()
                await update.message.reply_text("❌ Ошибка активации промокода")
            finally:
                conn.close()
        else:
            await update.message.reply_text("❌ Промокод не найден или уже активирован!")
        
        context.user_data["state"] = None
        await main_menu(update, context)
        return

    # Админка - расширенные функции
    elif uid == ADMIN_ID:
        # Выдача баланса
        if state == "adm_gv":
            try:
                parts = text.split()
                if len(parts) == 2:
                    tid, am = int(parts[0]), int(parts[1])
                    
                    # Обновляем баланс в транзакции
                    conn = sqlite3.connect(DB_NAME)
                    cur = conn.cursor()
                    try:
                        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (am, tid))
                        log_admin_action(uid, "give_balance", tid, f"Amount: {am}")
                        conn.commit()
                        
                        await update.message.reply_text(f"✅ Баланс пользователя {tid} изменен на {am} куриц.")
                        
                        # Уведомляем пользователя
                        try:
                            await context.bot.send_message(
                                chat_id=tid,
                                text=f"📥 Администратор выдал вам {am} куриц\n\n✅ Проверьте баланс в личном кабинете"
                            )
                        except:
                            pass
                            
                    except:
                        conn.rollback()
                        await update.message.reply_text("❌ Ошибка обновления баланса!")
                    finally:
                        conn.close()
                else:
                    await update.message.reply_text("❌ Формат: ID КОЛИЧЕСТВО\nПример: 123456789 10")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}\nПроверьте введенные данные")
        
        # Создание промокода
        elif state == "adm_p_new":
            try:
                parts = text.split()
                if len(parts) == 2:
                    c, r = parts[0].upper(), int(parts[1])
                    db_query("INSERT OR REPLACE INTO promocodes VALUES (?,?)", (c, r))
                    log_admin_action(uid, "create_promo", None, f"Code: {c}, Reward: {r}")
                    await update.message.reply_text(f"✅ Промокод {c} создан с наградой {r} куриц")
                else:
                    await update.message.reply_text("❌ Формат: КОД КОЛИЧЕСТВО\nПример: SUMMER2024 5")
            except:
                await update.message.reply_text("❌ Ошибка. Проверьте формат: КОД ЧИСЛО")
        
        # Поиск пользователя
        elif state == "adm_find":
            try:
                search = text.strip()
                if not search:
                    await update.message.reply_text("❌ Введите ID или username для поиска")
                    return
                
                if search.startswith('@'):
                    users = db_query("SELECT * FROM users WHERE username LIKE ?", (f"%{search[1:]}%",), fetchall=True)
                else:
                    try:
                        user_id = int(search)
                        users = db_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchall=True)
                    except:
                        users = db_query("SELECT * FROM users WHERE username LIKE ?", (f"%{search}%",), fetchall=True)
                
                if users:
                    response = "🔍 Найденные пользователи:\n\n"
                    for user in users[:10]:
                        response += f"🆔 ID: {user['user_id']}\n"
                        response += f"👤 Username: @{user['username'] if user['username'] else 'нет'}\n"
                        response += f"💰 Баланс: {user['balance']} куриц\n"
                        response += f"📊 Рефералов: {user['referrals']}\n"
                        response += f"📅 Регистрация: {user['reg_date'][:10] if user['reg_date'] else 'Неизвестно'}\n"
                        response += "─" * 30 + "\n"
                    await update.message.reply_text(response)
                else:
                    await update.message.reply_text("❌ Пользователь не найден")
            except:
                await update.message.reply_text("❌ Ошибка поиска")
        
        # Рассылка
        elif state == "adm_broadcast":
            msg = text
            if not msg:
                await update.message.reply_text("❌ Введите сообщение для рассылки")
                return
                
            users = db_query("SELECT user_id FROM users", fetchall=True)
            total = len(users)
            
            if total == 0:
                await update.message.reply_text("❌ Нет пользователей для рассылки")
                return
            
            progress = await update.message.reply_text(f"📢 Начинаю рассылку для {total} пользователей... 0%")
            success = 0
            failed = 0
            
            for i, user in enumerate(users):
                try:
                    await context.bot.send_message(user['user_id'], msg)
                    success += 1
                except:
                    failed += 1
                
                if i % 10 == 0 or i == total - 1:
                    progress_percent = int((i + 1) / total * 100)
                    await progress.edit_text(
                        f"📢 Рассылка... {progress_percent}%\n"
                        f"✅ Успешно: {success}\n"
                        f"❌ Неудачно: {failed}"
                    )
                
                await asyncio.sleep(0.05)
            
            await progress.edit_text(
                f"✅ Рассылка завершена!\n\n"
                f"👥 Всего пользователей: {total}\n"
                f"✅ Успешно отправлено: {success}\n"
                f"❌ Не удалось отправить: {failed}"
            )
        
        # Статистика
        elif state == "adm_stats":
            total_users = db_query("SELECT COUNT(*) as count FROM users", fetchone=True)['count']
            total_chickens = db_query("SELECT SUM(balance) as total FROM users", fetchone=True)['total'] or 0
            total_orders = db_query("SELECT COUNT(*) as count FROM orders", fetchone=True)['count']
            
            stats_text = "📊 Статистика бота:\n\n"
            stats_text += f"👥 Всего пользователей: {total_users}\n"
            stats_text += f"🐔 Куриц на балансах: {total_chickens}\n"
            stats_text += f"📦 Всего заказов: {total_orders}\n"
            stats_text += f"👑 Админ ID: {ADMIN_ID}"
            
            await update.message.reply_text(stats_text)
        
        # Установка баланса
        elif state == "adm_set_balance":
            try:
                parts = text.split()
                if len(parts) == 2:
                    tid, new_balance = int(parts[0]), int(parts[1])
                    
                    conn = sqlite3.connect(DB_NAME)
                    cur = conn.cursor()
                    try:
                        cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, tid))
                        log_admin_action(uid, "set_balance", tid, f"New balance: {new_balance}")
                        conn.commit()
                        
                        await update.message.reply_text(f"✅ Баланс пользователя {tid} установлен на {new_balance} куриц")
                        
                        # Уведомляем пользователя
                        try:
                            await context.bot.send_message(
                                chat_id=tid,
                                text=f"📊 Ваш баланс установлен администратором: {new_balance} куриц"
                            )
                        except:
                            pass
                            
                    except:
                        conn.rollback()
                        await update.message.reply_text("❌ Ошибка установки баланса!")
                    finally:
                        conn.close()
                else:
                    await update.message.reply_text("❌ Формат: ID БАЛАНС\nПример: 123456789 50")
            except:
                await update.message.reply_text("❌ Ошибка. Проверьте введенные данные")
        
        # Просмотр логов
        elif state == "adm_view_logs":
            try:
                count = int(text) if text.isdigit() else 10
                logs = db_query("SELECT * FROM admin_logs ORDER BY date DESC LIMIT ?", (count,), fetchall=True)
                
                if logs:
                    response = f"📋 Последние {len(logs)} действий:\n\n"
                    for log in logs:
                        response += f"📅 {log['date']}\n"
                        response += f"👤 Admin: {log['admin_id']}\n"
                        response += f"🔧 Действие: {log['action']}\n"
                        response += f"🎯 Цель: {log['target_id'] or 'Нет'}\n"
                        if log['details']:
                            response += f"📝 Подробности: {log['details']}\n"
                        response += "─" * 30 + "\n"
                    await update.message.reply_text(response[:4000])
                else:
                    await update.message.reply_text("📭 Логов пока нет")
            except:
                await update.message.reply_text("❌ Ошибка просмотра логов")
        
        # Кастомная сумма для пополнения
        elif state == "adm_custom_amount":
            try:
                target_user = context.user_data.get("custom_amount_user")
                amount = int(text)
                
                if target_user and amount > 0:
                    conn = sqlite3.connect(DB_NAME)
                    cur = conn.cursor()
                    try:
                        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_user))
                        log_admin_action(uid, "custom_payment", target_user, f"Amount: {amount}")
                        conn.commit()
                        
                        await update.message.reply_text(f"✅ Начислено {amount} куриц пользователю {target_user}")
                        
                        # Уведомляем пользователя
                        try:
                            await context.bot.send_message(
                                chat_id=target_user,
                                text=f"💰 Ваш платеж подтвержден! Начислено {amount} куриц"
                            )
                        except:
                            pass
                            
                    except:
                        conn.rollback()
                        await update.message.reply_text("❌ Ошибка начисления!")
                    finally:
                        conn.close()
                else:
                    await update.message.reply_text("❌ Ошибка данных")
            except:
                await update.message.reply_text("❌ Введите корректное число")
    
    context.user_data["state"] = None

# --- ФОТО (СКРИНЫ) ---
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if context.user_data.get("state") == "wait_photo":
        pid = update.message.photo[-1].file_id
        
        kb = [
            [InlineKeyboardButton("+1", callback_data=f"aj_1_{uid}"), 
             InlineKeyboardButton("+5", callback_data=f"aj_5_{uid}"), 
             InlineKeyboardButton("+10", callback_data=f"aj_10_{uid}")],
            [InlineKeyboardButton("Настроить сумму", callback_data=f"aj_custom_{uid}")],
            [InlineKeyboardButton("Отклонить", callback_data=f"aj_0_{uid}")]
        ]
        await context.bot.send_photo(
            ADMIN_ID, 
            pid, 
            caption=f"📸 Заявка на пополнение от пользователя {uid}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        await update.message.reply_text("✅ Скриншот отправлен на проверку администратору")
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
        if not u or u['balance'] < 1: 
            await q.message.reply_text("❌ Недостаточно куриц на балансе!")
        else:
            context.user_data["state"] = "order_user"
            await q.message.reply_text("👤 Введите Username (объект доставки):")
    
    elif d == "shop_nav":
        btns = [[InlineKeyboardButton(f"Пакет {n} - {p['price']} звезд", callback_data=f"buy_{n}")] for n,p in PRICES.items()]
        await q.message.reply_text(
            "🛒 Магазин:\n\n1 курочка - 15 звезд\n5 курочек - 25 звезд\n10 курочек - 50 звезд",
            reply_markup=InlineKeyboardMarkup(btns + [[InlineKeyboardButton("Назад", callback_data="main_menu")]])
        )
    
    elif d.startswith("buy_"):
        package = d.split("_")[1]
        price = PRICES[package]["price"]
        await q.message.reply_text(
            f"💰 Для покупки пакета {package} ({price} звезд):\n\n"
            f"1. Оплатите {price} звезд на {OWNER_LINK}\n"
            f"2. Отправьте скриншот оплаты в разделе 'Связь (Оплата)'\n\n"
            f"✅ После проверки баланс будет пополнен"
        )
    
    elif d == "promo_nav":
        context.user_data["state"] = "use_promo"
        await q.message.reply_text("🎁 Введите промокод:")
    
    elif d == "support_nav":
        context.user_data["state"] = "wait_photo"
        await q.message.reply_text(
            f"💰 Для пополнения баланса:\n\n"
            f"1. Оплатите нужную сумму на {OWNER_LINK}\n"
            f"2. Отправьте скриншот оплаты\n\n"
            f"✅ После проверки администратором баланс будет пополнен"
        )
    
    elif d == "ref_nav":
        me = await context.bot.get_me()
        user = db_query("SELECT referrals FROM users WHERE user_id = ?", (uid,), fetchone=True)
        ref_count = user['referrals'] if user else 0
        await q.message.reply_text(
            f"📤 Реферальная система:\n\n"
            f"🔗 Ссылка: t.me/{me.username}?start=ref{uid}\n"
            f"👥 Приглашено: {ref_count} человек\n"
            f"🎁 Бонус: 1 курица за 3 приглашенных друга\n"
            f"📊 Прогресс: {ref_count % 3}/3"
        )
    
    # АДМИН-ПАНЕЛЬ
    elif d == "adm_nav" and uid == ADMIN_ID:
        kb = [
            [InlineKeyboardButton("💰 Выдать баланс", callback_data="adm_gv"), 
             InlineKeyboardButton("⚖️ Установить баланс", callback_data="adm_set_balance")],
            [InlineKeyboardButton("🎁 Создать промокод", callback_data="adm_p_new"),
             InlineKeyboardButton("🔍 Поиск пользователя", callback_data="adm_find")],
            [InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"),
             InlineKeyboardButton("📊 Статистика", callback_data="adm_stats")],
            [InlineKeyboardButton("📋 Просмотр логов", callback_data="adm_view_logs"),
             InlineKeyboardButton("📥 Экспорт данных", callback_data="adm_export")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        await q.message.reply_text("⚡ Админ-панель:", reply_markup=InlineKeyboardMarkup(kb))
    
    elif d.startswith("adm_"):
        context.user_data["state"] = d
        
        # Улучшенные сообщения для каждой функции
        if d == "adm_gv":
            await q.message.reply_text("💰 ВЫДАЧА БАЛАНСА\n\nВведите ID пользователя и количество через пробел:\nПример: 123456789 10")
        elif d == "adm_p_new":
            await q.message.reply_text("🎁 СОЗДАНИЕ ПРОМОКОДА\n\nВведите код и количество куриц через пробел:\nПример: SUMMER2024 5")
        elif d == "adm_find":
            await q.message.reply_text("🔍 ПОИСК ПОЛЬЗОВАТЕЛЯ\n\nВведите ID, username или @username для поиска:")
        elif d == "adm_broadcast":
            await q.message.reply_text("📢 РАССЫЛКА\n\nВведите сообщение для отправки всем пользователям:")
        elif d == "adm_stats":
            await message_handler(update, context)  # Показываем статистику сразу
        elif d == "adm_set_balance":
            await q.message.reply_text("⚖️ УСТАНОВКА БАЛАНСА\n\nВведите ID пользователя и новый баланс:\nПример: 123456789 50")
        elif d == "adm_view_logs":
            await q.message.reply_text("📋 ПРОСМОТР ЛОГОВ\n\nВведите количество записей для показа (по умолчанию 10):")
        elif d == "adm_export":
            await export_data(update, context)
    
    # Обработка заявок на пополнение
    elif d.startswith("aj_"):
        parts = d.split("_")
        action = parts[1]
        target = parts[2] if len(parts) > 2 else None
        
        if action == "0":
            await q.message.edit_caption("❌ Заявка отклонена")
            try:
                await context.bot.send_message(target, "❌ Ваша заявка на пополнение отклонена администратором")
            except: 
                pass
        
        elif action == "custom" and target:
            context.user_data["custom_amount_user"] = target
            context.user_data["state"] = "adm_custom_amount"
            await q.message.reply_text(f"💰 НАСТРОЙКА СУММЫ\n\nВведите количество куриц для пользователя {target}:")
        
        elif action.isdigit() and target:
            amount = int(action)
            
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            try:
                cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target))
                log_admin_action(uid, "approve_payment", target, f"Amount: {amount}")
                conn.commit()
                
                await q.message.edit_caption(f"✅ Заявка подтверждена\nНачислено: {amount} куриц")
                
                try:
                    await context.bot.send_message(
                        target, 
                        f"✅ Ваша заявка подтверждена!\nНачислено: {amount} куриц\n\n💰 Проверьте баланс в личном кабинете"
                    )
                except:
                    pass
                    
            except:
                conn.rollback()
                await q.message.edit_caption("❌ Ошибка начисления!")
            finally:
                conn.close()

# --- ЭКСПОРТ ДАННЫХ ---
async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.from_user.id
    if uid != ADMIN_ID:
        return
    
    users = db_query("SELECT * FROM users", fetchall=True)
    orders = db_query("SELECT * FROM orders", fetchall=True)
    
    user_data = "📊 ЭКСПОРТ ПОЛЬЗОВАТЕЛЕЙ:\n\n"
    for user in users[:30]:  # Ограничиваем
        user_data += f"ID: {user['user_id']}, Username: {user['username']}, Balance: {user['balance']}, Referrals: {user['referrals']}\n"
    
    order_data = "\n📦 ЭКСПОРТ ЗАКАЗОВ:\n\n"
    for order in orders[:20]:
        order_data += f"Order: {order['order_id']}, User: {order['user_id']}, Target: {order['target_user']}, Date: {order['date']}\n"
    
    full_data = user_data + order_data
    
    if len(full_data) > 4000:
        chunks = [full_data[i:i+4000] for i in range(0, len(full_data), 4000)]
        for chunk in chunks[:3]:
            await update.callback_query.message.reply_text(chunk)
    else:
        await update.callback_query.message.reply_text(full_data)
    
    log_admin_action(uid, "export_data", None, "Data exported")

# --- СТАРТ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.username or str(uid)
    
    # Создаем или обновляем пользователя
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", 
                       (uid, username, datetime.now()))
        
        # Реферальная система
        if context.args and context.args[0].startswith("ref"):
            ref_id = context.args[0].replace("ref", "")
            if ref_id and ref_id != str(uid):
                try:
                    ref_id = int(ref_id)
                    cur.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                    
                    # Проверяем бонус за каждые 3 реферала
                    cur.execute("SELECT referrals FROM users WHERE user_id = ?", (ref_id,))
                    ref_data = cur.fetchone()
                    if ref_data and ref_data[0] % 3 == 0:
                        cur.execute("UPDATE users SET balance = balance + 1 WHERE user_id = ?", (ref_id,))
                        log_admin_action(ADMIN_ID, "ref_bonus", ref_id, "Bonus for 3 referrals")
                except:
                    pass
        
        conn.commit()
    except Exception as e:
        logger.error(f"Start error: {e}")
        conn.rollback()
    finally:
        conn.close()
    
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
