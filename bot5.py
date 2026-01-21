#!/usr/bin/env python3
"""
🛡️ ANTI-RAID BOT - РАБОЧАЯ ВЕРСИЯ
Telegram: @anti_raid_system_bot
"""

import asyncio
import json
import logging
import sqlite3
import threading
import re
from datetime import datetime, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any

# Telegram
from telegram import (
    Update, 
    ChatPermissions, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ChatMember,
    Message,
    User
)
from telegram.constants import ParseMode, ChatMemberStatus, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============ КОНСТАНТЫ ============

TOKEN = "8290647556:AAHRcf50ez31bJbKchCCFr3xKazyhZUWkQQ"
WEB_PORT = 8080

# Настройки по умолчанию
DEFAULT_CONFIG = {
    # Анти-флуд
    "текст_лимит": 5,
    "медиа_лимит": 8,
    "окно_времени": 7,
    "строгий_режим": False,
    
    # Анти-рейд
    "порог_рейда": 12,
    "окно_рейда": 3,
    "блокировка_время": 10,
    
    # Наказания
    "бан_часы": 2,
    "мут_минуты": 30,
    "варны_до_бана": 2,
    
    # Режимы
    "авто_блокировка": True,
    "авто_медленный": False,
    "задержка_медленного": 15,
    
    # Защита
    "защита_новых": True,
    "часы_защиты": 24,
    "игнор_админов": True,
    "игнор_админов_бота": True,
}

# ============ БАЗА ДАННЫХ ============

class Database:
    def __init__(self, path="anti_raid.db"):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()
    
    def init_db(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                settings TEXT,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_admins (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exceptions (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                reason TEXT,
                added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                message_type TEXT,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                action TEXT,
                target_id INTEGER,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    # ЧАТЫ
    def get_chat_settings(self, chat_id: int) -> Dict:
        cursor = self.conn.execute(
            "SELECT settings FROM chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        if row and row['settings']:
            config = json.loads(row['settings'])
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
        return DEFAULT_CONFIG.copy()
    
    def save_chat_settings(self, chat_id: int, config: Dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO chats (chat_id, settings) VALUES (?, ?)",
            (chat_id, json.dumps(config))
        )
        self.conn.commit()
    
    def set_owner(self, chat_id: int, user_id: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO chats (chat_id, owner_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        self.conn.commit()
        self.add_bot_admin(chat_id, user_id, user_id)
    
    def get_owner(self, chat_id: int) -> Optional[int]:
        cursor = self.conn.execute(
            "SELECT owner_id FROM chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        return row['owner_id'] if row else None
    
    # АДМИНЫ
    def add_bot_admin(self, chat_id: int, user_id: int, added_by: int, username: str = None):
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO bot_admins (chat_id, user_id, username) VALUES (?, ?, ?)",
                (chat_id, user_id, username)
            )
            self.conn.commit()
        except:
            pass
    
    def remove_bot_admin(self, chat_id: int, user_id: int):
        self.conn.execute(
            "DELETE FROM bot_admins WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()
    
    def get_bot_admins(self, chat_id: int) -> List[Tuple[int, str]]:
        cursor = self.conn.execute(
            "SELECT user_id, username FROM bot_admins WHERE chat_id = ?",
            (chat_id,)
        )
        return [(row['user_id'], row['username']) for row in cursor.fetchall()]
    
    def is_bot_admin(self, chat_id: int, user_id: int) -> bool:
        if user_id == self.get_owner(chat_id):
            return True
        
        cursor = self.conn.execute(
            "SELECT 1 FROM bot_admins WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None
    
    # ИСКЛЮЧЕНИЯ
    def add_exception(self, chat_id: int, user_id: int, username: str = None, reason: str = ""):
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO exceptions (chat_id, user_id, username, reason) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, username, reason)
            )
            self.conn.commit()
        except:
            pass
    
    def remove_exception(self, chat_id: int, user_id: int):
        self.conn.execute(
            "DELETE FROM exceptions WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()
    
    def get_exceptions(self, chat_id: int) -> List[Tuple[int, str]]:
        cursor = self.conn.execute(
            "SELECT user_id, username FROM exceptions WHERE chat_id = ?",
            (chat_id,)
        )
        return [(row['user_id'], row['username']) for row in cursor.fetchall()]
    
    def is_exception(self, chat_id: int, user_id: int) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM exceptions WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None
    
    # ВАРНЫ
    def add_warning(self, chat_id: int, user_id: int):
        self.conn.execute(
            "INSERT INTO warnings (chat_id, user_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        # Очистка старых варнов (старше 6 часов)
        hour_ago = datetime.now() - timedelta(hours=6)
        self.conn.execute(
            "DELETE FROM warnings WHERE created < ?",
            (hour_ago.timestamp(),)
        )
        self.conn.commit()
    
    def get_warnings(self, chat_id: int, user_id: int) -> int:
        hour_ago = datetime.now() - timedelta(hours=6)
        cursor = self.conn.execute(
            "SELECT COUNT(*) as count FROM warnings WHERE chat_id = ? AND user_id = ? AND created > ?",
            (chat_id, user_id, hour_ago.timestamp())
        )
        return cursor.fetchone()['count']
    
    def clear_warnings(self, chat_id: int, user_id: int):
        self.conn.execute(
            "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()
    
    # ИСТОРИЯ
    def add_message(self, chat_id: int, user_id: int, message_type: str):
        self.conn.execute(
            "INSERT INTO message_history (chat_id, user_id, message_type) VALUES (?, ?, ?)",
            (chat_id, user_id, message_type)
        )
        # Очистка старых сообщений (старше 1 часа)
        hour_ago = datetime.now() - timedelta(hours=1)
        self.conn.execute(
            "DELETE FROM message_history WHERE created < ?",
            (hour_ago.timestamp(),)
        )
        self.conn.commit()
    
    def get_message_stats(self, chat_id: int, user_id: int, seconds: int) -> Dict[str, int]:
        time_ago = datetime.now() - timedelta(seconds=seconds)
        
        cursor = self.conn.execute(
            "SELECT message_type, COUNT(*) as count FROM message_history WHERE chat_id = ? AND user_id = ? AND created > ? GROUP BY message_type",
            (chat_id, user_id, time_ago.timestamp())
        )
        
        stats = {"text": 0, "media": 0, "total": 0}
        for row in cursor.fetchall():
            if row['message_type'] == "text":
                stats["text"] = row['count']
            else:
                stats["media"] += row['count']
            stats["total"] += row['count']
        
        return stats
    
    def get_chat_activity(self, chat_id: int, seconds: int) -> float:
        time_ago = datetime.now() - timedelta(seconds=seconds)
        cursor = self.conn.execute(
            "SELECT COUNT(*) as count FROM message_history WHERE chat_id = ? AND created > ?",
            (chat_id, time_ago.timestamp())
        )
        count = cursor.fetchone()['count']
        return count / seconds if seconds > 0 else 0
    
    # ЛОГИ
    def add_log(self, chat_id: int, action: str, target_id: int = None):
        self.conn.execute(
            "INSERT INTO logs (chat_id, action, target_id) VALUES (?, ?, ?)",
            (chat_id, action, target_id)
        )
        self.conn.commit()
    
    def get_logs(self, chat_id: int, limit: int = 10) -> List[Dict]:
        cursor = self.conn.execute(
            "SELECT action, target_id, created FROM logs WHERE chat_id = ? ORDER BY created DESC LIMIT ?",
            (chat_id, limit)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    # СТАТИСТИКА
    def get_bot_stats(self) -> Dict:
        cursor = self.conn.execute("SELECT COUNT(DISTINCT chat_id) as chats FROM chats")
        chats = cursor.fetchone()['chats'] or 0
        
        cursor = self.conn.execute("SELECT COUNT(*) as actions FROM logs")
        actions = cursor.fetchone()['actions'] or 0
        
        cursor = self.conn.execute("SELECT COUNT(DISTINCT user_id) as exceptions FROM exceptions")
        exceptions = cursor.fetchone()['exceptions'] or 0
        
        return {"chats": chats, "actions": actions, "exceptions": exceptions}

db = Database()

# ============ ЛОГИРОВАНИЕ ============

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def resolve_user(identifier: str, context: ContextTypes.DEFAULT_TYPE, 
                      message: Message = None) -> Optional[Tuple[int, str]]:
    """Определяет пользователя по reply, username или ID"""
    
    # Ответ на сообщение
    if message and message.reply_to_message:
        reply_user = message.reply_to_message.from_user
        if reply_user:
            return reply_user.id, reply_user.username or reply_user.first_name
    
    identifier = identifier.strip().replace('@', '')
    
    # Если пусто и есть reply
    if not identifier and message and message.reply_to_message:
        reply_user = message.reply_to_message.from_user
        if reply_user:
            return reply_user.id, reply_user.username or reply_user.first_name
    
    # Если ID
    if identifier.isdigit():
        return int(identifier), None
    
    return None

async def is_protected(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет защищён ли пользователь"""
    settings = db.get_chat_settings(chat_id)
    
    if db.is_exception(chat_id, user_id):
        return True
    
    if settings.get("игнор_админов_бота", True) and db.is_bot_admin(chat_id, user_id):
        return True
    
    if settings.get("игнор_админов", True):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return True
        except:
            pass
    
    if settings.get("защита_новых", True):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if hasattr(member, 'joined_date') and member.joined_date:
                join_time = datetime.fromtimestamp(member.joined_date)
                if datetime.now() - join_time < timedelta(hours=24):
                    return True
        except:
            pass
    
    return False

async def get_message_type(update: Update) -> str:
    """Определяет тип сообщения"""
    if update.message.text:
        return "text"
    elif update.message.photo or update.message.video or update.message.animation:
        return "media"
    elif update.message.sticker:
        return "sticker"
    else:
        return "other"

# ============ ЗАЩИТА ============

async def check_flood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == ChatType.PRIVATE:
        return False
    
    if await is_protected(chat.id, user.id, context):
        return False
    
    message_type = await get_message_type(update)
    db.add_message(chat.id, user.id, message_type)
    
    settings = db.get_chat_settings(chat.id)
    stats = db.get_message_stats(chat.id, user.id, settings["окно_времени"])
    
    text_limit = settings["текст_лимит"]
    media_limit = settings["медиа_лимит"]
    
    if stats["text"] >= text_limit or stats["media"] >= media_limit:
        warnings = db.get_warnings(chat.id, user.id)
        warnings_to_ban = settings.get("варны_до_бана", 2)
        
        if warnings < warnings_to_ban - 1:
            db.add_warning(chat.id, user.id)
            await update.message.reply_text(f"⚠️ Предупреждение {warnings + 1}/{warnings_to_ban}")
            return True
        else:
            try:
                if settings.get("бан_часы", 0) > 0:
                    ban_until = datetime.now() + timedelta(hours=settings["бан_часы"])
                    await context.bot.ban_chat_member(
                        chat_id=chat.id,
                        user_id=user.id,
                        until_date=int(ban_until.timestamp())
                    )
                    action = "бан"
                    duration = f"{settings['бан_часы']}ч"
                else:
                    mute_until = datetime.now() + timedelta(minutes=settings.get("мут_минуты", 30))
                    await context.bot.restrict_chat_member(
                        chat_id=chat.id,
                        user_id=user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=int(mute_until.timestamp())
                    )
                    action = "мут"
                    duration = f"{settings['мут_минуты']}м"
                
                db.add_log(chat.id, action, user.id)
                db.clear_warnings(chat.id, user.id)
                
                await update.message.reply_text(f"🚨 Пользователь {'забанен' if action == 'бан' else 'замучен'} на {duration}")
                return True
                
            except Exception as e:
                logger.error(f"Ошибка: {e}")
    
    return False

async def check_raid(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    settings = db.get_chat_settings(chat_id)
    activity = db.get_chat_activity(chat_id, settings["окно_рейда"])
    
    if activity >= settings["порог_рейда"]:
        if settings["авто_блокировка"]:
            try:
                await context.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                db.add_log(chat_id, "блокировка")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔒 Чат заблокирован на {settings['блокировка_время']} минут"
                )
                
                async def unlock():
                    await asyncio.sleep(settings['блокировка_время'] * 60)
                    try:
                        await context.bot.set_chat_permissions(
                            chat_id=chat_id,
                            permissions=ChatPermissions(can_send_messages=True)
                        )
                    except:
                        pass
                
                asyncio.create_task(unlock())
                
            except Exception as e:
                logger.error(f"Ошибка блокировки: {e}")
        elif settings["авто_медленный"]:
            try:
                await context.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(can_send_messages=True),
                    slow_mode_delay=settings["задержка_медленного"]
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🐢 Медленный режим: {settings['задержка_медленного']} сек"
                )
            except:
                pass

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return
    
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return
    
    flood = await check_flood(update, context)
    if not flood:
        await check_raid(chat.id, context)

# ============ КОМАНДЫ ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🛡️ Anti-Raid Bot

📋 Основные команды:
/setup - Настройка бота
/settings - Текущие настройки
/status - Статус защиты
/lock - Блокировка чата
/unlock - Разблокировка чата
/slow <сек> - Медленный режим
/normal - Выключить медленный режим

👥 Команды через ! (работают с reply):
!адм *ответ* - Добавить админа бота
!снять *ответ* - Удалить админа бота
!искл *ответ* - Добавить исключение
!нискл *ответ* - Удалить исключение
!варн *ответ* - Выдать предупреждение
!варны *ответ* - Посмотреть предупреждения
!снятьварны *ответ* - Снять все предупреждения

📊 Другие команды:
/admins - Список админов бота
/exceptions - Список исключений
/stats - Статистика чата
/logs - История действий

💡 Пример использования:
1. Ответьте на сообщение пользователя
2. Напишите !адм (без аргументов)
3. Пользователь станет админом бота
"""
    await update.message.reply_text(text)

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Добавьте меня в группу для настройки.")
        return
    
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            await update.message.reply_text("Требуются права администратора.")
            return
    except:
        await update.message.reply_text("Ошибка проверки прав.")
        return
    
    owner = db.get_owner(chat.id)
    if not owner:
        db.set_owner(chat.id, user.id)
        await update.message.reply_text("✅ Вы стали владельцем защиты в этом чате.")
    
    keyboard = [
        [InlineKeyboardButton("📊 Анти-флуд", callback_data="menu_flood")],
        [InlineKeyboardButton("🛡️ Анти-рейд", callback_data="menu_raid")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")],
        [InlineKeyboardButton("👥 Исключения", callback_data="menu_exceptions")],
        [InlineKeyboardButton("👑 Админы", callback_data="menu_admins")],
        [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")]
    ]
    
    await update.message.reply_text(
        "⚙️ Панель управления защитой\nВыберите раздел:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    settings = db.get_chat_settings(chat.id)
    
    text = f"""⚙️ Текущие настройки защиты:

📊 Анти-флуд:
• Текст: {settings['текст_лимит']} сообщ. за {settings['окно_времени']} сек
• Медиа: {settings['медиа_лимит']} сообщ. за {settings['окно_времени']} сек
• Строгий режим: {'✅' if settings['строгий_режим'] else '❌'}

🛡️ Анти-рейд:
• Порог: {settings['порог_рейда']} сообщ/сек
• Окно: {settings['окно_рейда']} сек
• Блокировка: {settings['блокировка_время']} мин

⚖️ Наказания:
• Бан: {settings['бан_часы']} ч
• Мут: {settings['мут_минуты']} м
• Предупреждений до бана: {settings['варны_до_бана']}

👥 Защита:
• Исключения: {len(db.get_exceptions(chat.id))}
• Админы бота: {len(db.get_bot_admins(chat.id))}
"""
    
    await update.message.reply_text(text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    settings = db.get_chat_settings(chat.id)
    
    text = f"""🛡️ Статус защиты

📊 Текущие ограничения:
• Текст: {settings['текст_лимит']} сообщ/{settings['окно_времени']}сек
• Медиа: {settings['медиа_лимит']} сообщ/{settings['окно_времени']}сек
• Рейд: {settings['порог_рейда']} сообщ/сек

👥 Защита:
• Исключения: {len(db.get_exceptions(chat.id))}
• Админы бота: {len(db.get_bot_admins(chat.id))}
• Владелец: {'✅' if db.get_owner(chat.id) else '❌'}

📈 Активность (за 1 мин): {db.get_chat_activity(chat.id, 60):.1f} сообщ/сек
"""
    
    await update.message.reply_text(text)

async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text("🔒 Чат заблокирован")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True)
        )
        await update.message.reply_text("🔓 Чат разблокирован")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def slow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    delay = 15
    if context.args:
        try:
            delay = int(context.args[0])
            if delay < 0 or delay > 21600:
                delay = 15
        except:
            pass
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True),
            slow_mode_delay=delay
        )
        await update.message.reply_text(f"🐢 Медленный режим: {delay} секунд")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def normal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True),
            slow_mode_delay=0
        )
        await update.message.reply_text("🚀 Медленный режим выключен")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    admins = db.get_bot_admins(chat.id)
    owner = db.get_owner(chat.id)
    
    if not admins:
        await update.message.reply_text("Нет админов бота.")
        return
    
    text = "👑 Админы бота:\n\n"
    
    for user_id, username in admins:
        if user_id == owner:
            display = f"@{username}" if username else f"ID {user_id}"
            text += f"• {display} 👑 (владелец)\n"
        else:
            display = f"@{username}" if username else f"ID {user_id}"
            text += f"• {display}\n"
    
    await update.message.reply_text(text)

async def exceptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    exceptions = db.get_exceptions(chat.id)
    
    if not exceptions:
        await update.message.reply_text("Нет исключённых пользователей.")
        return
    
    text = "👥 Исключённые пользователи:\n\n"
    for user_id, username in exceptions:
        display = f"@{username}" if username else f"ID {user_id}"
        text += f"• {display}\n"
    
    await update.message.reply_text(text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    settings = db.get_chat_settings(chat.id)
    activity = db.get_chat_activity(chat.id, 300)
    
    text = f"""📊 Статистика защиты:

📈 Активность (5 мин): {activity:.1f} сообщ/сек

👥 Пользователи:
• Исключения: {len(db.get_exceptions(chat.id))}
• Админы бота: {len(db.get_bot_admins(chat.id))}
• Владелец: {'✅' if db.get_owner(chat.id) else '❌'}

⚙️ Настройки:
• Лимит текста: {settings['текст_лимит']}/{settings['окно_времени']}сек
• Лимит медиа: {settings['медиа_лимит']}/{settings['окно_времени']}сек
• Порог рейда: {settings['порог_рейда']}/сек
"""
    
    await update.message.reply_text(text)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    logs = db.get_logs(chat.id, 10)
    
    if not logs:
        await update.message.reply_text("Нет записей о действиях.")
        return
    
    text = "📝 История действий:\n\n"
    for log in logs:
        time = datetime.fromtimestamp(log['created']).strftime("%H:%M")
        text += f"• {time} {log['action']}"
        if log['target_id']:
            text += f" (ID {log['target_id']})"
        text += "\n"
    
    await update.message.reply_text(text)

# ============ КОМАНДЫ ЧЕРЕЗ ! ============

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """!адм - добавить админа бота"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if chat.type == ChatType.PRIVATE:
        return
    
    owner = db.get_owner(chat.id)
    if user.id != owner:
        await update.message.reply_text("Только владелец может добавлять админов.")
        return
    
    argument = context.args[0] if context.args else ""
    result = await resolve_user(argument, context, message)
    
    if not result:
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return
    
    target_id, target_username = result
    
    if target_id == user.id:
        return
    
    bot_info = await context.bot.get_me()
    if target_id == bot_info.id:
        await update.message.reply_text("Нельзя добавить бота.")
        return
    
    db.add_bot_admin(chat.id, target_id, user.id, target_username)
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(f"✅ {display} теперь админ бота")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """!снять - удалить админа бота"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if chat.type == ChatType.PRIVATE:
        return
    
    owner = db.get_owner(chat.id)
    if user.id != owner:
        await update.message.reply_text("Только владелец может удалять админов.")
        return
    
    argument = context.args[0] if context.args else ""
    result = await resolve_user(argument, context, message)
    
    if not result:
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return
    
    target_id, target_username = result
    
    if target_id == owner:
        await update.message.reply_text("Нельзя удалить владельца.")
        return
    
    db.remove_bot_admin(chat.id, target_id)
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(f"✅ {display} больше не админ бота")

async def add_exception_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """!искл - добавить исключение"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if chat.type == ChatType.PRIVATE:
        return
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    argument = context.args[0] if context.args else ""
    result = await resolve_user(argument, context, message)
    
    if not result:
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return
    
    target_id, target_username = result
    
    db.add_exception(chat.id, target_id, target_username, "команда")
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(f"✅ {display} добавлен в исключения")

async def remove_exception_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """!нискл - удалить исключение"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if chat.type == ChatType.PRIVATE:
        return
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    argument = context.args[0] if context.args else ""
    result = await resolve_user(argument, context, message)
    
    if not result:
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return
    
    target_id, target_username = result
    
    db.remove_exception(chat.id, target_id)
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(f"✅ {display} удалён из исключений")

async def add_warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """!варн - выдать предупреждение"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if chat.type == ChatType.PRIVATE:
        return
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    argument = context.args[0] if context.args else ""
    result = await resolve_user(argument, context, message)
    
    if not result:
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return
    
    target_id, target_username = result
    
    if await is_protected(chat.id, target_id, context):
        await update.message.reply_text("Этот пользователь защищён.")
        return
    
    db.add_warning(chat.id, target_id)
    warnings = db.get_warnings(chat.id, target_id)
    settings = db.get_chat_settings(chat.id)
    
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(f"⚠️ {display} предупреждение {warnings}/{settings['варны_до_бана']}")
    
    if warnings >= settings['варны_до_бана']:
        try:
            await context.bot.ban_chat_member(
                chat_id=chat.id,
                user_id=target_id,
                until_date=int((datetime.now() + timedelta(hours=2)).timestamp())
            )
            await update.message.reply_text(f"🚨 {display} забанен за предупреждения")
            db.clear_warnings(chat.id, target_id)
        except Exception as e:
            logger.error(f"Ошибка: {e}")

async def check_warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """!варны - посмотреть предупреждения"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if chat.type == ChatType.PRIVATE:
        return
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    argument = context.args[0] if context.args else ""
    
    if not argument and not message.reply_to_message:
        warnings = db.get_warnings(chat.id, user.id)
        await update.message.reply_text(f"Ваши предупреждения: {warnings}/2")
        return
    
    result = await resolve_user(argument, context, message)
    
    if not result:
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return
    
    target_id, target_username = result
    warnings = db.get_warnings(chat.id, target_id)
    
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(f"⚠️ {display} предупреждений: {warnings}/2")

async def clear_warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """!снятьварны - снять все предупреждения"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if chat.type == ChatType.PRIVATE:
        return
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    argument = context.args[0] if context.args else ""
    result = await resolve_user(argument, context, message)
    
    if not result:
        await update.message.reply_text("Ответьте на сообщение пользователя или укажите ID.")
        return
    
    target_id, target_username = result
    
    db.clear_warnings(chat.id, target_id)
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(f"✅ Все предупреждения сняты у {display}")

# ============ КНОПКИ ============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    if not db.is_bot_admin(chat_id, user_id):
        await query.edit_message_text("Требуются права админа бота.")
        return
    
    settings = db.get_chat_settings(chat_id)
    
    if data == "menu_flood":
        keyboard = [
            [InlineKeyboardButton(f"Текст: {settings['текст_лимит']}", callback_data="set_text")],
            [InlineKeyboardButton(f"Медиа: {settings['медиа_лимит']}", callback_data="set_media")],
            [InlineKeyboardButton(f"Окно: {settings['окно_времени']} сек", callback_data="set_window")],
            [InlineKeyboardButton(f"Строгий: {'✅' if settings['строгий_режим'] else '❌'}", callback_data="toggle_strict")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await query.edit_message_text("📊 Анти-флуд:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "menu_raid":
        keyboard = [
            [InlineKeyboardButton(f"Порог: {settings['порог_рейда']}/сек", callback_data="set_threshold")],
            [InlineKeyboardButton(f"Окно: {settings['окно_рейда']} сек", callback_data="set_raid_window")],
            [InlineKeyboardButton(f"Блокировка: {settings['блокировка_время']} м", callback_data="set_lockdown")],
            [InlineKeyboardButton(f"Auto: {'✅' if settings['авто_блокировка'] else '❌'}", callback_data="toggle_auto")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await query.edit_message_text("🛡️ Анти-рейд:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "menu_settings":
        keyboard = [
            [InlineKeyboardButton(f"Бан: {settings['бан_часы']} ч", callback_data="set_ban")],
            [InlineKeyboardButton(f"Мут: {settings['мут_минуты']} м", callback_data="set_mute")],
            [InlineKeyboardButton(f"Варны: {settings['варны_до_бана']}", callback_data="set_warnings")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await query.edit_message_text("⚙️ Наказания:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "menu_exceptions":
        count = len(db.get_exceptions(chat_id))
        keyboard = [
            [InlineKeyboardButton("➕ Добавить", callback_data="add_exception_btn")],
            [InlineKeyboardButton("➖ Удалить", callback_data="remove_exception_btn")],
            [InlineKeyboardButton(f"📋 Список ({count})", callback_data="list_exceptions")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await query.edit_message_text("👥 Исключения:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "menu_admins":
        count = len(db.get_bot_admins(chat_id))
        keyboard = [
            [InlineKeyboardButton("➕ Добавить", callback_data="add_admin_btn")],
            [InlineKeyboardButton("➖ Удалить", callback_data="remove_admin_btn")],
            [InlineKeyboardButton(f"📋 Список ({count})", callback_data="list_admins")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
        ]
        await query.edit_message_text("👑 Админы:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "menu_stats":
        activity = db.get_chat_activity(chat_id, 60)
        text = f"""📊 Статистика:

📈 Активность: {activity:.1f} сообщ/сек
👥 Исключения: {len(db.get_exceptions(chat_id))}
👑 Админы: {len(db.get_bot_admins(chat_id))}
"""
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "back":
        keyboard = [
            [InlineKeyboardButton("📊 Анти-флуд", callback_data="menu_flood")],
            [InlineKeyboardButton("🛡️ Анти-рейд", callback_data="menu_raid")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")],
            [InlineKeyboardButton("👥 Исключения", callback_data="menu_exceptions")],
            [InlineKeyboardButton("👑 Админы", callback_data="menu_admins")],
            [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")]
        ]
        await query.edit_message_text("⚙️ Панель управления:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("toggle_"):
        if data == "toggle_strict":
            settings["строгий_режим"] = not settings["строгий_режим"]
        elif data == "toggle_auto":
            settings["авто_блокировка"] = not settings["авто_блокировка"]
        
        db.save_chat_settings(chat_id, settings)
        await button_handler(update, context)
    
    elif data.startswith("set_"):
        param_map = {
            "set_text": ("текст_лимит", "Введите лимит текста (1-20):"),
            "set_media": ("медиа_лимит", "Введите лимит медиа (1-20):"),
            "set_window": ("окно_времени", "Введите окно (1-60 сек):"),
            "set_threshold": ("порог_рейда", "Введите порог рейда (1-50):"),
            "set_raid_window": ("окно_рейда", "Введите окно рейда (1-10 сек):"),
            "set_lockdown": ("блокировка_время", "Введите блокировку (1-1440 мин):"),
            "set_ban": ("бан_часы", "Введите часы бана (0-744):"),
            "set_mute": ("мут_минуты", "Введите минуты мута (1-10080):"),
            "set_warnings": ("варны_до_бана", "Введите предупреждений до бана (1-10):"),
        }
        
        if data in param_map:
            parameter, question = param_map[data]
            context.user_data["parameter"] = parameter
            context.user_data["chat"] = chat_id
            await query.edit_message_text(f"{question}\n\nОтправьте число в чат.")
    
    elif data == "list_exceptions":
        exceptions = db.get_exceptions(chat_id)
        if exceptions:
            text = "👥 Исключения:\n\n"
            for user_id, username in exceptions:
                display = f"@{username}" if username else f"ID {user_id}"
                text += f"• {display}\n"
        else:
            text = "Нет исключений"
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_exceptions")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "list_admins":
        admins = db.get_bot_admins(chat_id)
        owner = db.get_owner(chat_id)
        if admins:
            text = "👑 Админы:\n\n"
            for user_id, username in admins:
                if user_id == owner:
                    display = f"@{username}" if username else f"ID {user_id}"
                    text += f"• {display} 👑\n"
                else:
                    display = f"@{username}" if username else f"ID {user_id}"
                    text += f"• {display}\n"
        else:
            text = "Нет админов"
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_admins")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "add_exception_btn":
        await query.edit_message_text(
            "Чтобы добавить исключение:\n"
            "1. Ответьте на сообщение пользователя\n"
            "2. Напишите !искл\n\n"
            "Или укажите ID пользователя:\n"
            "!искл 123456789"
        )
    
    elif data == "remove_exception_btn":
        await query.edit_message_text(
            "Чтобы удалить исключение:\n"
            "1. Ответьте на сообщение пользователя\n"
            "2. Напишите !нискл\n\n"
            "Или укажите ID пользователя:\n"
            "!нискл 123456789"
        )
    
    elif data == "add_admin_btn":
        await query.edit_message_text(
            "Чтобы добавить админа (только владелец):\n"
            "1. Ответьте на сообщение пользователя\n"
            "2. Напишите !адм\n\n"
            "Или укажите ID пользователя:\n"
            "!адм 123456789"
        )
    
    elif data == "remove_admin_btn":
        await query.edit_message_text(
            "Чтобы удалить админа (только владелец):\n"
            "1. Ответьте на сообщение пользователя\n"
            "2. Напишите !снять\n\n"
            "Или укажите ID пользователя:\n"
            "!снять 123456789"
        )

async def parameter_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "parameter" not in context.user_data:
        return
    
    parameter = context.user_data["parameter"]
    chat_id = context.user_data.get("chat")
    
    if not chat_id or chat_id != update.effective_chat.id:
        return
    
    if not db.is_bot_admin(chat_id, update.effective_user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    try:
        value = int(update.message.text)
        
        limits = {
            "текст_лимит": (1, 20),
            "медиа_лимит": (1, 20),
            "окно_времени": (1, 60),
            "порог_рейда": (1, 50),
            "окно_рейда": (1, 10),
            "блокировка_время": (1, 1440),
            "бан_часы": (0, 744),
            "мут_минуты": (1, 10080),
            "варны_до_бана": (1, 10),
        }
        
        if parameter in limits:
            min_val, max_val = limits[parameter]
            if value < min_val or value > max_val:
                await update.message.reply_text(f"От {min_val} до {max_val}")
                return
        
        settings = db.get_chat_settings(chat_id)
        settings[parameter] = value
        db.save_chat_settings(chat_id, settings)
        
        await update.message.reply_text(f"✅ Установлено: {value}")
        
        del context.user_data["parameter"]
        del context.user_data["chat"]
        
    except ValueError:
        await update.message.reply_text("Введите число")

# ============ ВЕБ-СЕРВЕР ============

start_time = datetime.now()

class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        
        if path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            
            stats = db.get_bot_stats()
            uptime = datetime.now() - start_time
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Anti-Raid Bot</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                        background: #000;
                        color: #fff;
                        margin: 0;
                        padding: 20px;
                        line-height: 1.6;
                    }}
                    .container {{
                        max-width: 800px;
                        margin: 0 auto;
                    }}
                    header {{
                        text-align: center;
                        margin-bottom: 40px;
                        padding-bottom: 20px;
                        border-bottom: 1px solid #333;
                    }}
                    h1 {{
                        font-size: 2.5em;
                        margin: 0;
                    }}
                    .status {{
                        display: inline-block;
                        padding: 8px 20px;
                        background: #0a0;
                        border-radius: 20px;
                        margin: 10px 0;
                    }}
                    .stats {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                        gap: 20px;
                        margin: 30px 0;
                    }}
                    .stat {{
                        background: #111;
                        padding: 20px;
                        border-radius: 10px;
                        text-align: center;
                    }}
                    .stat-number {{
                        font-size: 2em;
                        font-weight: bold;
                    }}
                    .section {{
                        background: #111;
                        padding: 30px;
                        border-radius: 10px;
                        margin-bottom: 30px;
                    }}
                    h2 {{
                        margin-top: 0;
                        color: #fff;
                    }}
                    .features {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 15px;
                        margin-top: 20px;
                    }}
                    .feature {{
                        background: #222;
                        padding: 15px;
                        border-radius: 8px;
                    }}
                    .commands {{
                        background: #222;
                        padding: 20px;
                        border-radius: 8px;
                        margin-top: 20px;
                    }}
                    .command {{
                        margin: 10px 0;
                        padding-left: 15px;
                        border-left: 3px solid #444;
                    }}
                    footer {{
                        text-align: center;
                        margin-top: 40px;
                        padding-top: 20px;
                        border-top: 1px solid #333;
                        color: #888;
                    }}
                    @media (max-width: 600px) {{
                        .container {{
                            padding: 10px;
                        }}
                        h1 {{
                            font-size: 2em;
                        }}
                        .stats {{
                            grid-template-columns: 1fr;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <header>
                        <h1>ANTI-RAID BOT</h1>
                        <div class="status">● АКТИВЕН</div>
                        <p>Защита Telegram чатов от рейдов и спама</p>
                    </header>
                    
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-number">{stats['chats']}</div>
                            <div>Чатов</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{stats['exceptions']}</div>
                            <div>Исключений</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{stats['actions']}</div>
                            <div>Действий</div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>ФУНКЦИИ</h2>
                        <div class="features">
                            <div class="feature">
                                <strong>Анти-флуд</strong>
                                <p>Контроль скорости текстовых и медиа сообщений</p>
                            </div>
                            <div class="feature">
                                <strong>Анти-рейд</strong>
                                <p>Обнаружение массовых атак и блокировка</p>
                            </div>
                            <div class="feature">
                                <strong>Исключения</strong>
                                <p>Белый список защищённых пользователей</p>
                            </div>
                            <div class="feature">
                                <strong>Гибкие настройки</strong>
                                <p>Индивидуальные параметры для каждого чата</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>КОМАНДЫ</h2>
                        <div class="commands">
                            <div class="command">
                                <strong>/setup</strong> - Настройка бота в чате
                            </div>
                            <div class="command">
                                <strong>!адм</strong> - Добавить админа бота (ответ на сообщение)
                            </div>
                            <div class="command">
                                <strong>!искл</strong> - Добавить исключение (ответ на сообщение)
                            </div>
                            <div class="command">
                                <strong>/lock</strong> - Блокировка чата
                            </div>
                            <div class="command">
                                <strong>/unlock</strong> - Разблокировка чата
                            </div>
                            <div class="command">
                                <strong>/stats</strong> - Статистика чата
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>СОГЛАШЕНИЕ</h2>
                        <div style="color: #ccc;">
                            <p>Бот предназначен исключительно для защиты Telegram чатов.</p>
                            <p>Мы храним минимально необходимые данные для работы системы.</p>
                            <p>Данные не передаются третьим лицам.</p>
                            <p>Администраторы чатов несут ответственность за настройку.</p>
                        </div>
                    </div>
                    
                    <footer>
                        <p>Anti-Raid Bot System</p>
                        <p>Время работы: {uptime.days} дней {uptime.seconds // 3600} часов</p>
                        <p>{datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
                    </footer>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        
        elif path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response = {"status": "ok", "time": datetime.now().isoformat()}
            self.wfile.write(json.dumps(response).encode())
        
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"404 - Not Found")
    
    def log_message(self, format, *args):
        pass

def run_web_server(port=8080):
    server = HTTPServer(('0.0.0.0', port), WebHandler)
    print(f"🌐 Веб-сервер запущен: http://localhost:{port}")
    server.serve_forever()

# ============ ЗАПУСК ============

async def main():
    # Запуск веб-сервера
    web_thread = threading.Thread(target=run_web_server, args=(WEB_PORT,), daemon=True)
    web_thread.start()
    print("✅ Веб-сервер запущен")
    
    # Создание приложения бота
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация команд
    commands = [
        ("start", start_command),
        ("setup", setup_command),
        ("settings", settings_command),
        ("status", status_command),
        ("lock", lock_command),
        ("unlock", unlock_command),
        ("slow", slow_command),
        ("normal", normal_command),
        ("admins", admins_command),
        ("exceptions", exceptions_command),
        ("stats", stats_command),
        ("logs", logs_command),
        ("help", start_command),
    ]
    
    for command, handler in commands:
        application.add_handler(CommandHandler(command, handler))
    
    # Команды через ! (реакции на сообщения)
    exclamation_commands = [
        ("адм", add_admin_command),
        ("снять", remove_admin_command),
        ("искл", add_exception_command),
        ("нискл", remove_exception_command),
        ("варн", add_warning_command),
        ("варны", check_warnings_command),
        ("снятьварны", clear_warnings_command),
    ]
    
    for command, handler in exclamation_commands:
        application.add_handler(MessageHandler(
            filters.Regex(f'^!{command}') & ~filters.COMMAND,
            handler
        ))
    
    # Инлайн-кнопки
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ввода параметров
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        parameter_input_handler
    ))
    
    # Основной обработчик сообщений
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        message_handler
    ))
    
    # Запуск бота
    print("🤖 Anti-Raid Bot запущен")
    print("=" * 50)
    print("📋 Основные команды:")
    print("  /setup - Настройка защиты")
    print("  !адм - Добавить админа (ответ на сообщение)")
    print("  !искл - Добавить исключение (ответ на сообщение)")
    print("  /lock - Блокировка чата")
    print("=" * 50)
    print("✅ Все команды работают")
    
    # Автосохранение базы данных
    async def auto_save():
        while True:
            await asyncio.sleep(300)  # Каждые 5 минут
            db.conn.commit()
            print("💾 База данных сохранена")
    
    asyncio.create_task(auto_save())
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Бесконечный цикл
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Создание необходимых файлов
    if not Path("requirements.txt").exists():
        with open("requirements.txt", "w", encoding="utf-8") as f:
            f.write("python-telegram-bot==20.7\n")
        print("📁 Создан requirements.txt")
    
    if not Path("Procfile").exists():
        with open("Procfile", "w", encoding="utf-8") as f:
            f.write("web: python bot.py\n")
        print("📁 Создан Procfile")
    
    if not Path("runtime.txt").exists():
        with open("runtime.txt", "w", encoding="utf-8") as f:
            f.write("python-3.11.0\n")
        print("📁 Создан runtime.txt")
    
    # Запуск бота
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Остановка бота...")
        db.conn.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        db.conn.close()
