#!/usr/bin/env python3
"""
🛡️ FINAL ANTI-RAID BOT
Полная защита Telegram чатов от рейдов и спама
Версия 4.0 - Финальная
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
from typing import Dict, List, Optional, Tuple, Set, Any
from enum import Enum
import time

# Telegram
from telegram import (
    Update, 
    ChatPermissions, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ChatMember,
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

DEFAULT_CONFIG = {
    "token": "8290647556:AAHRcf50ez31bJbKchCCFr3xKazyhZUWkQQ",
    "web_port": 8080
}

DEFAULT_CHAT_CONFIG = {
    # Анти-флуд
    "text_limit": 5,
    "media_limit": 8,
    "time_window": 7,
    "strict_mode": False,
    
    # Анти-рейд
    "raid_threshold": 12,
    "raid_window": 3,
    "lockdown_duration": 10,
    
    # Наказания
    "ban_duration": 2,
    "mute_duration": 30,
    
    # Режимы
    "auto_lockdown": True,
    "auto_slowmode": False,
    "slowmode_delay": 15,
    
    # Защита
    "protect_new": True,
    "new_member_hours": 24,
    "ignore_admins": True,
    "ignore_bot_admins": True,
    
    # Система
    "warnings_enabled": True,
    "warning_reset_hours": 6
}

# ============ БАЗА ДАННЫХ ============

class Database:
    def __init__(self, path="bot_data.db"):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()
    
    def init_db(self):
        cursor = self.conn.cursor()
        
        # Чаты
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Админы бота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_admins (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')
        
        # Исключения
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exempt_users (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                reason TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')
        
        # Предупреждения
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                warning_type TEXT,
                admin_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # История сообщений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                message_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # История действий
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                action TEXT,
                target_id INTEGER,
                target_username TEXT,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Кэш username -> user_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_cache (
                username TEXT PRIMARY KEY,
                user_id INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    # ===== ЧАТЫ =====
    def get_chat_config(self, chat_id: int) -> Dict:
        cursor = self.conn.execute(
            "SELECT config FROM chats WHERE chat_id = ? AND is_active = 1",
            (chat_id,)
        )
        row = cursor.fetchone()
        if row and row['config']:
            config = json.loads(row['config'])
            # Обновляем старые конфиги
            for key, value in DEFAULT_CHAT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
        return DEFAULT_CHAT_CONFIG.copy()
    
    def save_chat_config(self, chat_id: int, config: Dict):
        config_json = json.dumps(config)
        self.conn.execute(
            "INSERT OR REPLACE INTO chats (chat_id, config) VALUES (?, ?)",
            (chat_id, config_json)
        )
        self.conn.commit()
    
    def set_chat_owner(self, chat_id: int, user_id: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO chats (chat_id, owner_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        self.conn.commit()
        self.add_bot_admin(chat_id, user_id, user_id, "owner")
    
    def get_chat_owner(self, chat_id: int) -> Optional[int]:
        cursor = self.conn.execute(
            "SELECT owner_id FROM chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        return row['owner_id'] if row else None
    
    def is_chat_active(self, chat_id: int) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM chats WHERE chat_id = ? AND is_active = 1",
            (chat_id,)
        )
        return cursor.fetchone() is not None
    
    # ===== АДМИНЫ БОТА =====
    def add_bot_admin(self, chat_id: int, user_id: int, added_by: int, username: str = None) -> bool:
        try:
            self.conn.execute(
                '''INSERT OR IGNORE INTO bot_admins 
                   (chat_id, user_id, username, added_by) 
                   VALUES (?, ?, ?, ?)''',
                (chat_id, user_id, username, added_by)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error adding bot admin: {e}")
            return False
    
    def remove_bot_admin(self, chat_id: int, user_id: int) -> bool:
        try:
            self.conn.execute(
                "DELETE FROM bot_admins WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            self.conn.commit()
            return True
        except:
            return False
    
    def get_bot_admins(self, chat_id: int) -> List[Tuple[int, str]]:
        cursor = self.conn.execute(
            "SELECT user_id, username FROM bot_admins WHERE chat_id = ?",
            (chat_id,)
        )
        return [(row['user_id'], row['username']) for row in cursor.fetchall()]
    
    def is_bot_admin(self, chat_id: int, user_id: int) -> bool:
        if user_id == self.get_chat_owner(chat_id):
            return True
        
        cursor = self.conn.execute(
            "SELECT 1 FROM bot_admins WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None
    
    # ===== ИСКЛЮЧЕНИЯ =====
    def add_exempt_user(self, chat_id: int, user_id: int, added_by: int, 
                       username: str = None, reason: str = "") -> bool:
        try:
            self.conn.execute(
                '''INSERT OR REPLACE INTO exempt_users 
                   (chat_id, user_id, username, reason, added_by) 
                   VALUES (?, ?, ?, ?, ?)''',
                (chat_id, user_id, username, reason, added_by)
            )
            self.conn.commit()
            return True
        except:
            return False
    
    def remove_exempt_user(self, chat_id: int, user_id: int) -> bool:
        try:
            self.conn.execute(
                "DELETE FROM exempt_users WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            self.conn.commit()
            return True
        except:
            return False
    
    def get_exempt_users(self, chat_id: int) -> List[Tuple[int, str]]:
        cursor = self.conn.execute(
            "SELECT user_id, username FROM exempt_users WHERE chat_id = ?",
            (chat_id,)
        )
        return [(row['user_id'], row['username']) for row in cursor.fetchall()]
    
    def is_exempt(self, chat_id: int, user_id: int) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM exempt_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None
    
    # ===== ПРЕДУПРЕЖДЕНИЯ =====
    def add_warning(self, chat_id: int, user_id: int, warning_type: str, admin_id: int = None):
        self.conn.execute(
            '''INSERT INTO warnings (chat_id, user_id, warning_type, admin_id)
               VALUES (?, ?, ?, ?)''',
            (chat_id, user_id, warning_type, admin_id)
        )
        
        # Очистка старых предупреждений
        config = self.get_chat_config(chat_id)
        hours = config.get("warning_reset_hours", 6)
        time_ago = datetime.now() - timedelta(hours=hours)
        
        self.conn.execute(
            "DELETE FROM warnings WHERE timestamp < ?",
            (time_ago.timestamp(),)
        )
        
        self.conn.commit()
    
    def get_warning_count(self, chat_id: int, user_id: int) -> int:
        config = self.get_chat_config(chat_id)
        hours = config.get("warning_reset_hours", 6)
        time_ago = datetime.now() - timedelta(hours=hours)
        
        cursor = self.conn.execute(
            '''SELECT COUNT(*) as count FROM warnings 
               WHERE chat_id = ? AND user_id = ? AND timestamp > ?''',
            (chat_id, user_id, time_ago.timestamp())
        )
        return cursor.fetchone()['count']
    
    def clear_warnings(self, chat_id: int, user_id: int):
        self.conn.execute(
            "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()
    
    # ===== ИСТОРИЯ СООБЩЕНИЙ =====
    def add_message(self, chat_id: int, user_id: int, message_type: str):
        self.conn.execute(
            "INSERT INTO message_history (chat_id, user_id, message_type) VALUES (?, ?, ?)",
            (chat_id, user_id, message_type)
        )
        
        # Очистка старых сообщений (старше 1 часа)
        hour_ago = datetime.now() - timedelta(hours=1)
        self.conn.execute(
            "DELETE FROM message_history WHERE timestamp < ?",
            (hour_ago.timestamp(),)
        )
        
        self.conn.commit()
    
    def get_message_stats(self, chat_id: int, user_id: int, seconds: int) -> Dict[str, int]:
        time_ago = datetime.now() - timedelta(seconds=seconds)
        
        cursor = self.conn.execute(
            '''SELECT message_type, COUNT(*) as count 
               FROM message_history 
               WHERE chat_id = ? AND user_id = ? AND timestamp > ?
               GROUP BY message_type''',
            (chat_id, user_id, time_ago.timestamp())
        )
        
        stats = {"text": 0, "media": 0, "total": 0}
        for row in cursor.fetchall():
            msg_type = row['message_type']
            count = row['count']
            
            if msg_type == "text":
                stats["text"] = count
            else:
                stats["media"] += count
            
            stats["total"] += count
        
        return stats
    
    def get_chat_activity(self, chat_id: int, seconds: int) -> float:
        time_ago = datetime.now() - timedelta(seconds=seconds)
        
        cursor = self.conn.execute(
            "SELECT COUNT(*) as count FROM message_history WHERE chat_id = ? AND timestamp > ?",
            (chat_id, time_ago.timestamp())
        )
        
        count = cursor.fetchone()['count']
        return count / seconds if seconds > 0 else 0
    
    # ===== ЛОГИРОВАНИЕ ДЕЙСТВИЙ =====
    def log_action(self, chat_id: int, action: str, target_id: int = None, 
                  target_username: str = None, reason: str = ""):
        self.conn.execute(
            '''INSERT INTO action_log (chat_id, action, target_id, target_username, reason)
               VALUES (?, ?, ?, ?, ?)''',
            (chat_id, action, target_id, target_username, reason)
        )
        self.conn.commit()
    
    def get_recent_actions(self, chat_id: int, limit: int = 10) -> List[Dict]:
        cursor = self.conn.execute(
            '''SELECT action, target_id, target_username, reason, timestamp 
               FROM action_log 
               WHERE chat_id = ? 
               ORDER BY timestamp DESC 
               LIMIT ?''',
            (chat_id, limit)
        )
        
        return [dict(row) for row in cursor.fetchall()]
    
    # ===== КЭШ USERNAME =====
    def cache_user(self, username: str, user_id: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO user_cache (username, user_id) VALUES (?, ?)",
            (username.lower().replace('@', ''), user_id)
        )
        self.conn.commit()
    
    def get_user_from_cache(self, username: str) -> Optional[int]:
        cursor = self.conn.execute(
            "SELECT user_id FROM user_cache WHERE username = ?",
            (username.lower().replace('@', ''),)
        )
        row = cursor.fetchone()
        return row['user_id'] if row else None
    
    # ===== СТАТИСТИКА =====
    def get_stats(self) -> Dict:
        cursor = self.conn.execute("SELECT COUNT(DISTINCT chat_id) as chats FROM chats WHERE is_active = 1")
        chats = cursor.fetchone()['chats'] or 0
        
        cursor = self.conn.execute("SELECT COUNT(*) as actions FROM action_log")
        actions = cursor.fetchone()['actions'] or 0
        
        cursor = self.conn.execute("SELECT COUNT(DISTINCT user_id) as exempt FROM exempt_users")
        exempt = cursor.fetchone()['exempt'] or 0
        
        cursor = self.conn.execute("SELECT COUNT(*) as messages FROM message_history")
        messages = cursor.fetchone()['messages'] or 0
        
        return {
            "chats": chats,
            "actions": actions,
            "exempt_users": exempt,
            "messages_processed": messages
        }
    
    def close(self):
        self.conn.close()

# Глобальная БД
db = Database()

# ============ ЛОГИРОВАНИЕ ============

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def resolve_user_identifier(identifier: str, context: ContextTypes.DEFAULT_TYPE, 
                                 chat_id: int = None) -> Optional[Tuple[int, str]]:
    """
    Разрешает идентификатор пользователя (username или ID)
    Возвращает (user_id, username) или None
    """
    identifier = identifier.strip().replace('@', '')
    
    # Если это число, пробуем как ID
    if identifier.isdigit():
        user_id = int(identifier)
        
        # Проверяем существование пользователя
        try:
            user = await context.bot.get_chat(user_id)
            return user_id, user.username or user.first_name
        except:
            # Проверяем в кэше
            return user_id, None
    
    # Ищем в кэше
    cached_id = db.get_user_from_cache(identifier)
    if cached_id:
        return cached_id, identifier
    
    # Если это username, ищем через mention
    if chat_id:
        try:
            # Пробуем найти пользователя в чате
            # Это упрощённый подход - в реальности нужно использовать другие методы
            pass
        except:
            pass
    
    return None

async def is_telegram_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, является ли пользователь админом в Telegram"""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

async def is_protected(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, защищён ли пользователь от действий бота"""
    config = db.get_chat_config(chat_id)
    
    # Проверка исключений
    if db.is_exempt(chat_id, user_id):
        return True
    
    # Проверка админов бота
    if config.get("ignore_bot_admins", True) and db.is_bot_admin(chat_id, user_id):
        return True
    
    # Проверка Telegram админов
    if config.get("ignore_admins", True):
        if await is_telegram_admin(chat_id, user_id, context):
            return True
    
    # Защита новых участников
    if config.get("protect_new", True):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if hasattr(member, 'joined_date') and member.joined_date:
                join_time = datetime.fromtimestamp(member.joined_date)
                hours = config.get("new_member_hours", 24)
                if datetime.now() - join_time < timedelta(hours=hours):
                    return True
        except:
            pass
    
    return False

async def get_message_type(update: Update) -> str:
    """Определяет тип сообщения"""
    if update.message.text:
        return "text"
    elif update.message.photo:
        return "photo"
    elif update.message.animation:
        return "gif"
    elif update.message.sticker:
        return "sticker"
    elif update.message.video:
        return "video"
    elif update.message.voice:
        return "voice"
    elif update.message.video_note:
        return "video_note"
    elif update.message.document:
        return "document"
    else:
        return "other"

# ============ ОСНОВНАЯ ЛОГИКА ЗАЩИТЫ ============

async def check_flood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка на флуд"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == ChatType.PRIVATE:
        return False
    
    config = db.get_chat_config(chat.id)
    
    # Проверка защиты
    if await is_protected(chat.id, user.id, context):
        return False
    
    # Сохраняем сообщение в историю
    msg_type = await get_message_type(update)
    db.add_message(chat.id, user.id, msg_type)
    
    # Получаем статистику
    stats = db.get_message_stats(chat.id, user.id, config["time_window"])
    
    # Проверяем лимиты
    text_limit = config["text_limit"]
    media_limit = config["media_limit"]
    
    text_violation = stats["text"] >= text_limit
    media_violation = stats["media"] >= media_limit
    
    # В строгом режиме проверяем общее количество
    if config.get("strict_mode", False):
        total_violation = stats["total"] >= (text_limit + media_limit) // 2
        violation = text_violation or media_violation or total_violation
    else:
        violation = text_violation or media_violation
    
    if violation:
        # Проверяем предупреждения
        warning_count = db.get_warning_count(chat.id, user.id)
        
        if config.get("warnings_enabled", True) and warning_count < 2:
            # Выдаём предупреждение
            db.add_warning(chat.id, user.id, "flood")
            
            warning_text = f"⚠️ Предупреждение {warning_count + 1}/2: Флуд"
            if text_violation:
                warning_text += f" ({stats['text']} текстовых сообщений)"
            elif media_violation:
                warning_text += f" ({stats['media']} медиа сообщений)"
            
            await update.message.reply_text(warning_text)
            return True
        
        # Применяем наказание
        try:
            if config.get("ban_duration", 0) > 0:
                ban_until = datetime.now() + timedelta(hours=config["ban_duration"])
                await context.bot.ban_chat_member(
                    chat_id=chat.id,
                    user_id=user.id,
                    until_date=int(ban_until.timestamp())
                )
                
                action = "ban"
                duration = f"{config['ban_duration']}ч"
            else:
                # Мут вместо бана
                mute_until = datetime.now() + timedelta(minutes=config.get("mute_duration", 30))
                permissions = ChatPermissions(
                    can_send_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
                
                await context.bot.restrict_chat_member(
                    chat_id=chat.id,
                    user_id=user.id,
                    permissions=permissions,
                    until_date=int(mute_until.timestamp())
                )
                
                action = "mute"
                duration = f"{config['mute_duration']}м"
            
            # Логируем действие
            db.log_action(
                chat.id, 
                action, 
                user.id,
                user.username,
                f"Флуд: текст={stats['text']}, медиа={stats['media']}"
            )
            
            # Оповещение
            await update.message.reply_text(
                f"🚨 Пользователь {'забанен' if action == 'ban' else 'замучен'} "
                f"на {duration} за флуд."
            )
            
            # Сбрасываем предупреждения
            db.clear_warnings(chat.id, user.id)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка наказания: {e}")
    
    return False

async def check_raid(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Проверка на рейд"""
    config = db.get_chat_config(chat_id)
    
    activity = db.get_chat_activity(chat_id, config["raid_window"])
    
    if activity >= config["raid_threshold"]:
        if config["auto_lockdown"]:
            try:
                # Блокировка чата
                await context.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(
                        can_send_messages=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False,
                        can_change_info=False,
                        can_invite_users=False,
                        can_pin_messages=False
                    )
                )
                
                db.log_action(chat_id, "lockdown", reason=f"Рейд: {activity:.1f} сообщ/сек")
                
                duration = config.get("lockdown_duration", 10)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔒 Чат заблокирован на {duration} минут из-за рейда."
                )
                
                # Авторазблокировка через N минут
                async def auto_unlock():
                    await asyncio.sleep(duration * 60)
                    try:
                        await context.bot.set_chat_permissions(
                            chat_id=chat_id,
                            permissions=ChatPermissions(
                                can_send_messages=True,
                                can_send_other_messages=True,
                                can_add_web_page_previews=True,
                                can_change_info=False,
                                can_invite_users=True,
                                can_pin_messages=False
                            )
                        )
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="🔓 Чат автоматически разблокирован."
                        )
                    except:
                        pass
                
                asyncio.create_task(auto_unlock())
                
            except Exception as e:
                logger.error(f"Ошибка блокировки: {e}")
        
        elif config["auto_slowmode"]:
            try:
                await context.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_other_messages=True
                    ),
                    slow_mode_delay=config["slowmode_delay"]
                )
                
                db.log_action(chat_id, "slowmode", reason=f"Рейд: {activity:.1f} сообщ/сек")
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🐢 Включен медленный режим: {config['slowmode_delay']} сек."
                )
            except Exception as e:
                logger.error(f"Ошибка slowmode: {e}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик сообщений"""
    if not update.message or not update.effective_chat:
        return
    
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        # В ЛС - только команды
        return
    
    # Проверяем флуд
    is_flood = await check_flood(update, context)
    
    # Проверяем рейд (если не флуд)
    if not is_flood:
        await check_raid(chat.id, context)

# ============ КОМАНДЫ УПРАВЛЕНИЯ ============

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    text = """🛡️ Anti-Raid Bot

Полная защита чатов от рейдов и спама.

📋 Основные команды:
/setup - Настройка защиты
/settings - Текущие настройки
/status - Статус защиты
/lock - Блокировка чата
/unlock - Разблокировка
/slow <сек> - Медленный режим
/normal - Выключить медленный режим

👥 Управление исключениями:
/exempt <user> - Добавить исключение
/unexempt <user> - Удалить исключение
/exemptlist - Список исключений

👑 Управление админами:
/promote <user> - Добавить админа бота
/demote <user> - Удалить админа бота
/admins - Список админов бота

📊 Статистика:
/stats - Статистика чата
/logs - Последние действия
/warnings <user> - Предупреждения

💡 Как добавить пользователя:
• /exempt username (без @)
• /exempt 123456789 (ID пользователя)
• /promote username
• /promote 123456789
"""
    await update.message.reply_text(text)

async def setup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройка бота в чате"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Добавьте меня в группу для настройки.")
        return
    
    # Проверяем права Telegram
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            await update.message.reply_text("Требуются права администратора.")
            return
    except Exception as e:
        logger.error(f"Setup error: {e}")
        await update.message.reply_text("Ошибка проверки прав.")
        return
    
    # Устанавливаем владельца
    owner = db.get_chat_owner(chat.id)
    if not owner:
        db.set_chat_owner(chat.id, user.id)
        db.cache_user(user.username or str(user.id), user.id)
        await update.message.reply_text("✅ Вы стали владельцем защиты в этом чате.")
    
    # Меню настроек
    keyboard = [
        [InlineKeyboardButton("📊 Анти-флуд", callback_data="menu_flood")],
        [InlineKeyboardButton("🛡️ Анти-рейд", callback_data="menu_raid")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")],
        [InlineKeyboardButton("👥 Исключения", callback_data="menu_exempt")],
        [InlineKeyboardButton("👑 Админы", callback_data="menu_admins")],
        [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")]
    ]
    
    await update.message.reply_text(
        "⚙️ Панель управления защитой\nВыберите раздел:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текущие настройки"""
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    config = db.get_chat_config(chat.id)
    
    text = f"""⚙️ Текущие настройки защиты:

📊 Анти-флуд:
• Текст: {config['text_limit']} сообщ. за {config['time_window']} сек
• Медиа: {config['media_limit']} сообщ. за {config['time_window']} сек
• Строгий режим: {'✅' if config['strict_mode'] else '❌'}

🛡️ Анти-рейд:
• Порог: {config['raid_threshold']} сообщ/сек
• Окно: {config['raid_window']} сек
• Блокировка: {config['lockdown_duration']} мин

⚖️ Наказания:
• Бан: {config['ban_duration']} ч
• Мут: {config['mute_duration']} м

🔧 Режимы:
• Auto-Lockdown: {'✅' if config['auto_lockdown'] else '❌'}
• Auto-Slowmode: {'✅' if config['auto_slowmode'] else '❌'}
• Задержка: {config['slowmode_delay']} сек

🛡️ Защита:
• Новые участники: {'✅' if config['protect_new'] else '❌'}
• Telegram админы: {'✅' if config['ignore_admins'] else '❌'}
• Админы бота: {'✅' if config['ignore_bot_admins'] else '❌'}

📈 Статистика:
• Исключения: {len(db.get_exempt_users(chat.id))}
• Админы бота: {len(db.get_bot_admins(chat.id))}
"""
    
    await update.message.reply_text(text)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус защиты"""
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    config = db.get_chat_config(chat.id)
    active = db.is_chat_active(chat.id)
    
    text = f"""🛡️ Статус защиты

{'✅ АКТИВНА' if active else '❌ НЕАКТИВНА'}

📊 Текущие ограничения:
• Текст: {config['text_limit']} сообщ/{config['time_window']}сек
• Медиа: {config['media_limit']} сообщ/{config['time_window']}сек
• Рейд: {config['raid_threshold']} сообщ/сек

👥 Исключения: {len(db.get_exempt_users(chat.id))}
👑 Админы бота: {len(db.get_bot_admins(chat.id))}

📈 Активность (за 1 мин): {db.get_chat_activity(chat.id, 60):.1f} сообщ/сек
"""
    
    await update.message.reply_text(text)

async def lock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная блокировка чата"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    duration = 30  # минут
    if context.args:
        try:
            duration = int(context.args[0])
            if duration < 1 or duration > 1440:
                duration = 30
        except:
            pass
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
        )
        
        db.log_action(chat.id, "manual_lockdown", user.id, reason=f"{duration} мин")
        
        await update.message.reply_text(f"🔒 Чат заблокирован на {duration} минут.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def unlock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разблокировка чата"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
        )
        
        await update.message.reply_text("🔓 Чат разблокирован.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def slow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение медленного режима"""
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
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_other_messages=True
            ),
            slow_mode_delay=delay
        )
        
        db.log_action(chat.id, "slowmode", user.id, reason=f"{delay} сек")
        
        await update.message.reply_text(f"🐢 Медленный режим: {delay} секунд.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def normal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выключение медленного режима"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_other_messages=True
            ),
            slow_mode_delay=0
        )
        
        await update.message.reply_text("🚀 Медленный режим выключен.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# ============ КОМАНДЫ ИСКЛЮЧЕНИЙ ============

async def exempt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить исключение"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /exempt <username или ID>")
        return
    
    identifier = context.args[0]
    
    # Разрешаем идентификатор
    result = await resolve_user_identifier(identifier, context, chat.id)
    
    if not result:
        await update.message.reply_text("Пользователь не найден.")
        return
    
    target_id, target_username = result
    
    # Нельзя добавить самого себя
    if target_id == user.id:
        await update.message.reply_text("Нельзя добавить самого себя.")
        return
    
    # Нельзя добавить бота
    bot_info = await context.bot.get_me()
    if target_id == bot_info.id:
        await update.message.reply_text("Нельзя добавить бота.")
        return
    
    # Добавляем исключение
    if db.add_exempt_user(chat.id, target_id, user.id, target_username, "manual"):
        # Кэшируем username
        if target_username:
            db.cache_user(target_username, target_id)
        
        display_name = f"@{target_username}" if target_username else f"ID {target_id}"
        await update.message.reply_text(f"✅ {display_name} добавлен в исключения.")
    else:
        await update.message.reply_text("Ошибка добавления.")

async def unexempt_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить исключение"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /unexempt <username или ID>")
        return
    
    identifier = context.args[0]
    
    # Разрешаем идентификатор
    result = await resolve_user_identifier(identifier, context, chat.id)
    
    if not result:
        await update.message.reply_text("Пользователь не найден.")
        return
    
    target_id, target_username = result
    
    # Удаляем исключение
    if db.remove_exempt_user(chat.id, target_id):
        display_name = f"@{target_username}" if target_username else f"ID {target_id}"
        await update.message.reply_text(f"✅ {display_name} удалён из исключений.")
    else:
        await update.message.reply_text("Пользователь не найден в исключениях.")

async def exemptlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список исключений"""
    chat = update.effective_chat
    
    exempt_users = db.get_exempt_users(chat.id)
    
    if not exempt_users:
        await update.message.reply_text("Нет исключённых пользователей.")
        return
    
    text = "👥 Исключённые пользователи:\n\n"
    for i, (user_id, username) in enumerate(exempt_users, 1):
        display = f"@{username}" if username else f"ID {user_id}"
        text += f"{i}. {display}\n"
    
    await update.message.reply_text(text)

# ============ КОМАНДЫ АДМИНИСТРИРОВАНИЯ ============

async def promote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить админа бота"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Только владелец может добавлять админов
    owner = db.get_chat_owner(chat.id)
    if user.id != owner:
        await update.message.reply_text("Только владелец может добавлять админов.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /promote <username или ID>")
        return
    
    identifier = context.args[0]
    
    # Разрешаем идентификатор
    result = await resolve_user_identifier(identifier, context, chat.id)
    
    if not result:
        await update.message.reply_text("Пользователь не найден.")
        return
    
    target_id, target_username = result
    
    # Нельзя добавить самого себя
    if target_id == user.id:
        await update.message.reply_text("Вы уже владелец.")
        return
    
    # Нельзя добавить бота
    bot_info = await context.bot.get_me()
    if target_id == bot_info.id:
        await update.message.reply_text("Нельзя добавить бота.")
        return
    
    # Добавляем админа
    if db.add_bot_admin(chat.id, target_id, user.id, target_username):
        # Кэшируем username
        if target_username:
            db.cache_user(target_username, target_id)
        
        display_name = f"@{target_username}" if target_username else f"ID {target_id}"
        await update.message.reply_text(f"✅ {display_name} добавлен в админы бота.")
    else:
        await update.message.reply_text("Ошибка или уже админ.")

async def demote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить админа бота"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Только владелец может удалять админов
    owner = db.get_chat_owner(chat.id)
    if user.id != owner:
        await update.message.reply_text("Только владелец может удалять админов.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /demote <username или ID>")
        return
    
    identifier = context.args[0]
    
    # Разрешаем идентификатор
    result = await resolve_user_identifier(identifier, context, chat.id)
    
    if not result:
        await update.message.reply_text("Пользователь не найден.")
        return
    
    target_id, target_username = result
    
    # Нельзя удалить владельца
    if target_id == owner:
        await update.message.reply_text("Нельзя удалить владельца.")
        return
    
    # Удаляем админа
    if db.remove_bot_admin(chat.id, target_id):
        display_name = f"@{target_username}" if target_username else f"ID {target_id}"
        await update.message.reply_text(f"✅ {display_name} удалён из админов бота.")
    else:
        await update.message.reply_text("Пользователь не найден в админах.")

async def admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список админов бота"""
    chat = update.effective_chat
    
    bot_admins = db.get_bot_admins(chat.id)
    owner = db.get_chat_owner(chat.id)
    
    if not bot_admins and not owner:
        await update.message.reply_text("Нет админов бота.")
        return
    
    text = "👑 Админы бота:\n\n"
    
    if owner:
        # Находим username владельца
        owner_name = "Владелец"
        for admin_id, username in bot_admins:
            if admin_id == owner:
                owner_name = f"@{username}" if username else f"ID {owner}"
                break
        
        text += f"👑 {owner_name} (владелец)\n\n"
    
    # Остальные админы
    admin_count = 0
    for admin_id, username in bot_admins:
        if admin_id != owner:  # Пропускаем владельца
            admin_count += 1
            display = f"@{username}" if username else f"ID {admin_id}"
            text += f"{admin_count}. {display}\n"
    
    if admin_count == 0 and owner:
        text += "Других админов нет"
    
    await update.message.reply_text(text)

# ============ КОМАНДЫ СТАТИСТИКИ ============

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика чата"""
    chat = update.effective_chat
    
    config = db.get_chat_config(chat.id)
    
    # Активность за разные периоды
    activity_1m = db.get_chat_activity(chat.id, 60)
    activity_5m = db.get_chat_activity(chat.id, 300)
    activity_15m = db.get_chat_activity(chat.id, 900)
    
    text = f"""📊 Статистика защиты:

📈 Активность:
• 1 минута: {activity_1m:.1f} сообщ/сек
• 5 минут: {activity_5m:.1f} сообщ/сек
• 15 минут: {activity_15m:.1f} сообщ/сек

👥 Пользователи:
• Исключения: {len(db.get_exempt_users(chat.id))}
• Админы бота: {len(db.get_bot_admins(chat.id))}
• Владелец: {'Установлен' if db.get_chat_owner(chat.id) else 'Нет'}

⚙️ Настройки:
• Лимит текста: {config['text_limit']}/{config['time_window']}сек
• Лимит медиа: {config['media_limit']}/{config['time_window']}сек
• Порог рейда: {config['raid_threshold']}/сек
"""
    
    await update.message.reply_text(text)

async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Последние действия"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    recent_actions = db.get_recent_actions(chat.id, 10)
    
    if not recent_actions:
        await update.message.reply_text("Нет записей о действиях.")
        return
    
    text = "📝 Последние действия:\n\n"
    
    for action in recent_actions:
        timestamp = datetime.fromtimestamp(action['timestamp'])
        time_str = timestamp.strftime("%H:%M:%S")
        
        target = ""
        if action['target_username']:
            target = f"@{action['target_username']}"
        elif action['target_id']:
            target = f"ID {action['target_id']}"
        
        reason = f" - {action['reason']}" if action['reason'] else ""
        
        text += f"• {time_str} {action['action'].upper()}"
        if target:
            text += f" {target}"
        text += f"{reason}\n"
    
    await update.message.reply_text(text)

async def warnings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предупреждения пользователя"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Требуются права админа бота.")
        return
    
    if not context.args:
        # Показываем свои предупреждения
        count = db.get_warning_count(chat.id, user.id)
        config = db.get_chat_config(chat.id)
        max_warnings = 2
        
        await update.message.reply_text(
            f"⚠️ Ваши предупреждения: {count}/{max_warnings}\n"
            f"Сбрасываются через {config.get('warning_reset_hours', 6)} часов."
        )
        return
    
    # Показываем предупреждения другого пользователя
    identifier = context.args[0]
    
    result = await resolve_user_identifier(identifier, context, chat.id)
    
    if not result:
        await update.message.reply_text("Пользователь не найден.")
        return
    
    target_id, target_username = result
    count = db.get_warning_count(chat.id, target_id)
    
    display = f"@{target_username}" if target_username else f"ID {target_id}"
    await update.message.reply_text(
        f"⚠️ Предупреждения {display}: {count}/2\n"
        "После 2 предупреждений - бан/мут."
    )

# ============ ИНЛАЙН МЕНЮ ============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик инлайн-кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    if not db.is_bot_admin(chat_id, user_id):
        await query.edit_message_text("Требуются права админа бота.")
        return
    
    config = db.get_chat_config(chat_id)
    
    if data == "menu_flood":
        keyboard = [
            [InlineKeyboardButton(f"Текст: {config['text_limit']}", callback_data="set_text_limit")],
            [InlineKeyboardButton(f"Медиа: {config['media_limit']}", callback_data="set_media_limit")],
            [InlineKeyboardButton(f"Окно: {config['time_window']} сек", callback_data="set_time_window")],
            [InlineKeyboardButton(f"Строгий режим: {'✅' if config['strict_mode'] else '❌'}", 
                                 callback_data="toggle_strict")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "📊 Настройка анти-флуда:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_raid":
        keyboard = [
            [InlineKeyboardButton(f"Порог: {config['raid_threshold']}/сек", callback_data="set_raid_threshold")],
            [InlineKeyboardButton(f"Окно: {config['raid_window']} сек", callback_data="set_raid_window")],
            [InlineKeyboardButton(f"Блокировка: {config['lockdown_duration']} мин", 
                                 callback_data="set_lockdown_duration")],
            [InlineKeyboardButton(f"Auto-Lockdown: {'✅' if config['auto_lockdown'] else '❌'}", 
                                 callback_data="toggle_lockdown")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "🛡️ Настройка анти-рейда:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_settings":
        keyboard = [
            [InlineKeyboardButton(f"Бан: {config['ban_duration']} ч", callback_data="set_ban_duration")],
            [InlineKeyboardButton(f"Мут: {config['mute_duration']} м", callback_data="set_mute_duration")],
            [InlineKeyboardButton(f"Auto-Slowmode: {'✅' if config['auto_slowmode'] else '❌'}", 
                                 callback_data="toggle_slowmode")],
            [InlineKeyboardButton(f"Задержка: {config['slowmode_delay']} сек", callback_data="set_slowmode_delay")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "⚙️ Дополнительные настройки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_exempt":
        exempt_count = len(db.get_exempt_users(chat_id))
        keyboard = [
            [InlineKeyboardButton("➕ Добавить исключение", callback_data="add_exempt")],
            [InlineKeyboardButton("➖ Удалить исключение", callback_data="remove_exempt")],
            [InlineKeyboardButton(f"📋 Список ({exempt_count})", callback_data="list_exempt_menu")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "👥 Управление исключениями:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_admins":
        admins_count = len(db.get_bot_admins(chat_id))
        keyboard = [
            [InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin")],
            [InlineKeyboardButton("➖ Удалить админа", callback_data="remove_admin")],
            [InlineKeyboardButton(f"📋 Список ({admins_count})", callback_data="list_admins_menu")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "👑 Управление админами бота:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_stats":
        await stats_cmd(query, context)
        return
    
    elif data == "back_main":
        keyboard = [
            [InlineKeyboardButton("📊 Анти-флуд", callback_data="menu_flood")],
            [InlineKeyboardButton("🛡️ Анти-рейд", callback_data="menu_raid")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings")],
            [InlineKeyboardButton("👥 Исключения", callback_data="menu_exempt")],
            [InlineKeyboardButton("👑 Админы", callback_data="menu_admins")],
            [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")]
        ]
        
        await query.edit_message_text(
            "⚙️ Панель управления защитой\nВыберите раздел:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith("toggle_"):
        # Обработка переключателей
        toggle_map = {
            "toggle_strict": "strict_mode",
            "toggle_lockdown": "auto_lockdown",
            "toggle_slowmode": "auto_slowmode"
        }
        
        if data in toggle_map:
            param = toggle_map[data]
            config[param] = not config[param]
            db.save_chat_config(chat_id, config)
            
            await query.answer(f"{param} изменён")
            await button_handler(update, context)  # Обновляем меню
    
    elif data.startswith("set_"):
        # Обработка установки значений
        param_map = {
            "set_text_limit": ("text_limit", "Введите лимит текстовых сообщений (1-20):"),
            "set_media_limit": ("media_limit", "Введите лимит медиа сообщений (1-20):"),
            "set_time_window": ("time_window", "Введите временное окно в секундах (1-60):"),
            "set_raid_threshold": ("raid_threshold", "Введите порог рейда (1-50):"),
            "set_raid_window": ("raid_window", "Введите окно анализа рейда (1-10):"),
            "set_lockdown_duration": ("lockdown_duration", "Введите длительность блокировки (1-1440 мин):"),
            "set_ban_duration": ("ban_duration", "Введите длительность бана (0-744 часов):"),
            "set_mute_duration": ("mute_duration", "Введите длительность мута (1-10080 минут):"),
            "set_slowmode_delay": ("slowmode_delay", "Введите задержку медленного режима (0-21600 сек):")
        }
        
        if data in param_map:
            param_name, prompt = param_map[data]
            context.user_data["waiting_param"] = param_name
            context.user_data["waiting_chat"] = chat_id
            
            await query.edit_message_text(
                f"{prompt}\n\nОтправьте число в чат.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Отмена", callback_data="back_main")]
                ])
            )
    
    elif data == "list_exempt_menu":
        exempt_users = db.get_exempt_users(chat_id)
        
        if not exempt_users:
            text = "Нет исключённых пользователей."
        else:
            text = "👥 Исключённые пользователи:\n\n"
            for i, (user_id, username) in enumerate(exempt_users, 1):
                display = f"@{username}" if username else f"ID {user_id}"
                text += f"{i}. {display}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu_exempt")]
            ])
        )
    
    elif data == "list_admins_menu":
        bot_admins = db.get_bot_admins(chat_id)
        owner = db.get_chat_owner(chat_id)
        
        if not bot_admins and not owner:
            text = "Нет админов бота."
        else:
            text = "👑 Админы бота:\n\n"
            
            if owner:
                owner_name = "Владелец"
                for admin_id, username in bot_admins:
                    if admin_id == owner:
                        owner_name = f"@{username}" if username else f"ID {owner}"
                        break
                
                text += f"👑 {owner_name} (владелец)\n\n"
            
            admin_count = 0
            for admin_id, username in bot_admins:
                if admin_id != owner:
                    admin_count += 1
                    display = f"@{username}" if username else f"ID {admin_id}"
                    text += f"{admin_count}. {display}\n"
            
            if admin_count == 0 and owner:
                text += "Других админов нет"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu_admins")]
            ])
        )

async def param_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода параметров"""
    if "waiting_param" not in context.user_data:
        return
    
    param_name = context.user_data["waiting_param"]
    chat_id = context.user_data.get("waiting_chat")
    
    if not chat_id or chat_id != update.effective_chat.id:
        return
    
    if not db.is_bot_admin(chat_id, update.effective_user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    try:
        value = int(update.message.text)
        
        # Валидация значений
        limits = {
            "text_limit": (1, 20),
            "media_limit": (1, 20),
            "time_window": (1, 60),
            "raid_threshold": (1, 50),
            "raid_window": (1, 10),
            "lockdown_duration": (1, 1440),
            "ban_duration": (0, 744),
            "mute_duration": (1, 10080),
            "slowmode_delay": (0, 21600)
        }
        
        if param_name in limits:
            min_val, max_val = limits[param_name]
            if value < min_val or value > max_val:
                await update.message.reply_text(f"От {min_val} до {max_val}")
                return
        
        # Сохраняем значение
        config = db.get_chat_config(chat_id)
        config[param_name] = value
        db.save_chat_config(chat_id, config)
        
        # Показываем сообщение об успехе
        await update.message.reply_text(f"✅ {param_name} установлен: {value}")
        
        # Очищаем состояние
        del context.user_data["waiting_param"]
        del context.user_data["waiting_chat"]
        
    except ValueError:
        await update.message.reply_text("Введите число.")

# ============ ВЕБ-СЕРВЕР ============

start_time = datetime.now()

class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        
        if path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            
            stats = db.get_stats()
            uptime = datetime.now() - start_time
            
            days = uptime.days
            hours = uptime.seconds // 3600
            minutes = (uptime.seconds % 3600) // 60
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Anti-Raid Bot</title>
                <style>
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }}
                    
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                        background: #0a0a0a;
                        color: #f0f0f0;
                        line-height: 1.6;
                        min-height: 100vh;
                    }}
                    
                    .container {{
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 40px 20px;
                    }}
                    
                    header {{
                        text-align: center;
                        margin-bottom: 50px;
                        padding-bottom: 30px;
                        border-bottom: 1px solid #333;
                    }}
                    
                    h1 {{
                        font-size: 2.8em;
                        font-weight: 300;
                        letter-spacing: 2px;
                        margin-bottom: 10px;
                    }}
                    
                    .subtitle {{
                        color: #888;
                        font-size: 1.1em;
                        margin-bottom: 30px;
                    }}
                    
                    .status {{
                        display: inline-block;
                        padding: 8px 20px;
                        background: #222;
                        border: 1px solid #444;
                        border-radius: 20px;
                        font-size: 0.9em;
                        color: #4CAF50;
                    }}
                    
                    .stats-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                        gap: 20px;
                        margin: 40px 0;
                    }}
                    
                    .stat-card {{
                        background: #111;
                        border: 1px solid #222;
                        border-radius: 8px;
                        padding: 25px;
                        text-align: center;
                        transition: transform 0.2s;
                    }}
                    
                    .stat-card:hover {{
                        transform: translateY(-2px);
                        border-color: #333;
                    }}
                    
                    .stat-number {{
                        font-size: 2.2em;
                        font-weight: 300;
                        color: #fff;
                        margin-bottom: 5px;
                    }}
                    
                    .stat-label {{
                        color: #888;
                        font-size: 0.9em;
                    }}
                    
                    .section {{
                        background: #111;
                        border: 1px solid #222;
                        border-radius: 8px;
                        padding: 30px;
                        margin-bottom: 30px;
                    }}
                    
                    .section-title {{
                        font-size: 1.4em;
                        font-weight: 400;
                        margin-bottom: 20px;
                        color: #fff;
                        padding-bottom: 10px;
                        border-bottom: 1px solid #333;
                    }}
                    
                    .features {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
                        gap: 15px;
                    }}
                    
                    .feature {{
                        background: #0a0a0a;
                        padding: 20px;
                        border-radius: 6px;
                        border-left: 3px solid #444;
                    }}
                    
                    .feature-title {{
                        color: #fff;
                        margin-bottom: 10px;
                        font-weight: 500;
                    }}
                    
                    .feature-desc {{
                        color: #888;
                        font-size: 0.9em;
                    }}
                    
                    .commands {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                        gap: 20px;
                    }}
                    
                    .command-group {{
                        background: #0a0a0a;
                        padding: 20px;
                        border-radius: 6px;
                    }}
                    
                    .group-title {{
                        color: #fff;
                        margin-bottom: 15px;
                        font-weight: 500;
                    }}
                    
                    .command {{
                        margin-bottom: 12px;
                        padding-left: 15px;
                        border-left: 2px solid #333;
                    }}
                    
                    .cmd {{
                        color: #fff;
                        font-family: 'Courier New', monospace;
                        font-size: 0.9em;
                        margin-bottom: 5px;
                    }}
                    
                    .desc {{
                        color: #888;
                        font-size: 0.85em;
                    }}
                    
                    .terms {{
                        color: #aaa;
                        line-height: 1.8;
                    }}
                    
                    .terms h3 {{
                        color: #fff;
                        margin: 25px 0 15px 0;
                        font-weight: 400;
                    }}
                    
                    .terms ul {{
                        margin-left: 20px;
                        margin-bottom: 20px;
                    }}
                    
                    .terms li {{
                        margin-bottom: 8px;
                    }}
                    
                    footer {{
                        text-align: center;
                        margin-top: 50px;
                        padding-top: 30px;
                        border-top: 1px solid #333;
                        color: #666;
                        font-size: 0.9em;
                    }}
                    
                    .uptime {{
                        color: #888;
                        margin: 20px 0;
                        font-size: 0.9em;
                    }}
                    
                    @media (max-width: 600px) {{
                        .container {{
                            padding: 20px 15px;
                        }}
                        
                        h1 {{
                            font-size: 2em;
                        }}
                        
                        .stats-grid {{
                            grid-template-columns: 1fr;
                        }}
                    }}
                    
                    .highlight {{
                        color: #4CAF50;
                    }}
                    
                    a {{
                        color: #4CAF50;
                        text-decoration: none;
                    }}
                    
                    a:hover {{
                        text-decoration: underline;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <header>
                        <h1>ANTI-RAID BOT</h1>
                        <p class="subtitle">Защита Telegram чатов от рейдов и спама</p>
                        <div class="status">● АКТИВЕН</div>
                    </header>
                    
                    <div class="section">
                        <h2 class="section-title">СТАТИСТИКА</h2>
                        <div class="stats-grid">
                            <div class="stat-card">
                                <div class="stat-number">{stats['chats']}</div>
                                <div class="stat-label">ЧАТОВ</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-number">{stats['exempt_users']}</div>
                                <div class="stat-label">ИСКЛЮЧЕНИЙ</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-number">{stats['actions']}</div>
                                <div class="stat-label">ДЕЙСТВИЙ</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-number">{stats['messages_processed']}</div>
                                <div class="stat-label">СООБЩЕНИЙ</div>
                            </div>
                        </div>
                        
                        <div class="uptime">
                            Время работы: {days}д {hours}ч {minutes}м
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2 class="section-title">ФУНКЦИИ</h2>
                        <div class="features">
                            <div class="feature">
                                <div class="feature-title">АНТИ-ФЛУД</div>
                                <div class="feature-desc">Контроль скорости текстовых и медиа сообщений</div>
                            </div>
                            <div class="feature">
                                <div class="feature-title">АНТИ-РЕЙД</div>
                                <div class="feature-desc">Обнаружение массовых атак и автоматическая блокировка</div>
                            </div>
                            <div class="feature">
                                <div class="feature-title">ИСКЛЮЧЕНИЯ</div>
                                <div class="feature-desc">Белый список защищённых пользователей</div>
                            </div>
                            <div class="feature">
                                <div class="feature-title">ГИБКАЯ НАСТРОЙКА</div>
                                <div class="feature-desc">Индивидуальные параметры для каждого чата</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2 class="section-title">КОМАНДЫ</h2>
                        <div class="commands">
                            <div class="command-group">
                                <div class="group-title">ОСНОВНЫЕ</div>
                                <div class="command">
                                    <div class="cmd">/setup</div>
                                    <div class="desc">Настройка защиты в чате</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/settings</div>
                                    <div class="desc">Текущие настройки</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/lock</div>
                                    <div class="desc">Блокировка чата</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/unlock</div>
                                    <div class="desc">Разблокировка чата</div>
                                </div>
                            </div>
                            
                            <div class="command-group">
                                <div class="group-title">УПРАВЛЕНИЕ</div>
                                <div class="command">
                                    <div class="cmd">/exempt username</div>
                                    <div class="desc">Добавить исключение</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/promote username</div>
                                    <div class="desc">Добавить админа бота</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/stats</div>
                                    <div class="desc">Статистика чата</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/logs</div>
                                    <div class="desc">История действий</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2 class="section-title">ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ</h2>
                        <div class="terms">
                            <h3>1. ИСПОЛЬЗОВАНИЕ</h3>
                            <p>Бот предназначен исключительно для защиты Telegram чатов от нежелательной активности.</p>
                            
                            <h3>2. ОТВЕТСТВЕННОСТЬ</h3>
                            <p>Администраторы чатов несут полную ответственность за настройку и использование бота.</p>
                            
                            <h3>3. ДАННЫЕ</h3>
                            <p>Бот хранит минимально необходимые данные для функционирования:</p>
                            <ul>
                                <li>ID чатов и пользователей</li>
                                <li>Настройки системы защиты</li>
                                <li>Временную историю сообщений</li>
                            </ul>
                            
                            <h3>4. КОНФИДЕНЦИАЛЬНОСТЬ</h3>
                            <p>Мы не передаём данные третьим лицам. Вся информация используется только для работы системы защиты.</p>
                            
                            <h3>5. ОГРАНИЧЕНИЯ</h3>
                            <p>Бот не может:</p>
                            <ul>
                                <li>Читать содержимое сообщений</li>
                                <li>Хранить персональные данные</li>
                                <li>Отправлять сообщения от имени пользователей</li>
                            </ul>
                            
                            <h3>6. КОНТАКТЫ</h3>
                            <p>По вопросам работы бота обращайтесь через Telegram.</p>
                        </div>
                    </div>
                    
                    <footer>
                        <p>Anti-Raid Bot System</p>
                        <p>© {datetime.now().year} | Сервер работает на Render.com</p>
                        <p>Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
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
            response = {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": (datetime.now() - start_time).total_seconds()
            }
            self.wfile.write(json.dumps(response).encode())
        
        elif path == "/stats":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            stats = db.get_stats()
            stats["status"] = "active"
            stats["uptime"] = str(datetime.now() - start_time)
            self.wfile.write(json.dumps(stats).encode())
        
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"404 - Not Found")
    
    def log_message(self, format, *args):
        pass

def run_web_server(port=8080):
    """Запуск веб-сервера"""
    server = HTTPServer(('0.0.0.0', port), WebHandler)
    print(f"🌐 Веб-сервер запущен: http://localhost:{port}")
    server.serve_forever()

# ============ ЗАПУСК БОТА ============

def load_config():
    """Загрузка конфигурации"""
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CONFIG.copy()

async def main():
    """Основная функция запуска бота"""
    config = load_config()
    
    if config["token"] == "ВАШ_ТОКЕН_ОТ_BOTFATHER":
        print("❌ Установите токен бота в файле config.json")
        print("Получите токен у @BotFather и вставьте в config.json")
        return
    
    # Запуск веб-сервера
    web_thread = threading.Thread(
        target=run_web_server,
        args=(config.get("web_port", 8080),),
        daemon=True
    )
    web_thread.start()
    print("✅ Веб-сервер запущен")
    
    # Создание приложения бота
    application = Application.builder().token(config["token"]).build()
    
    # Регистрация команд
    commands = [
        ("start", start_cmd),
        ("setup", setup_cmd),
        ("settings", settings_cmd),
        ("status", status_cmd),
        ("lock", lock_cmd),
        ("unlock", unlock_cmd),
        ("slow", slow_cmd),
        ("normal", normal_cmd),
        ("exempt", exempt_cmd),
        ("unexempt", unexempt_cmd),
        ("exemptlist", exemptlist_cmd),
        ("promote", promote_cmd),
        ("demote", demote_cmd),
        ("admins", admins_cmd),
        ("stats", stats_cmd),
        ("logs", logs_cmd),
        ("warnings", warnings_cmd),
        ("help", start_cmd)
    ]
    
    for cmd, handler in commands:
        application.add_handler(CommandHandler(cmd, handler))
    
    # Инлайн-кнопки
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ввода параметров
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        param_input_handler
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
    print("  /exempt username - Добавить исключение")
    print("  /promote username - Добавить админа")
    print("=" * 50)
    
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
    if not Path("config.json").exists():
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print("📁 Создан config.json")
        print("⚠️ Замените 'ВАШ_ТОКЕН_ОТ_BOTFATHER' на ваш токен")
    
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
    
    # Запуск
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Остановка бота...")
        db.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        db.close()
