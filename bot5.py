#!/usr/bin/env python3
"""
Anti-Raid Telegram Bot
Полная система защиты с базой данных и веб-интерфейсом
"""

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import html
import secrets
import string
import time
import re

# Telegram импорты
from telegram import Update, ChatPermissions, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatMemberStatus, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Веб-сервер
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse

# ============ КОНСТАНТЫ ============

DEFAULT_CONFIG = {
    "token": "8290647556:AAHRcf50ez31bJbKchCCFr3xKazyhZUWkQQ",
    "web_port": 8080
}

DEFAULT_LIMITS = {
    "max_messages": 5,           # сообщений
    "time_window": 10,           # за N секунд
    "raid_threshold": 20,        # сообщений в секунду для рейда
    "raid_window": 5,            # окно анализа рейда
    "ban_hours": 2,              # длительность бана
    "auto_lockdown": True,       # авто блокировка
    "auto_slowmode": False,      # авто медленный режим
    "slowmode_delay": 30,        # задержка
    "exempt_new_members": True,  # не банить новых (<24ч)
    "exempt_duration": 24        # часов защиты для новых
}

# ============ БАЗА ДАННЫХ ============

class Database:
    def __init__(self, path="bot_data.db"):
        self.path = Path(path)
        self.conn = None
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Таблица чатов
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица админов бота
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                chat_id INTEGER,
                user_id INTEGER,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        
        # Таблица исключённых пользователей
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS exempt_users (
                chat_id INTEGER,
                user_id INTEGER,
                exempt_until TIMESTAMP,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        
        # Таблица истории сообщений (очищается автоматически)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS message_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                message_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица действий бота
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                action_type TEXT,
                target_id INTEGER,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    def get_chat_config(self, chat_id: int) -> Dict:
        """Получить конфиг чата"""
        cursor = self.conn.execute(
            "SELECT config FROM chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row['config'])
        return DEFAULT_LIMITS.copy()
    
    def save_chat_config(self, chat_id: int, config: Dict) -> None:
        """Сохранить конфиг чата"""
        config_json = json.dumps(config)
        self.conn.execute("""
            INSERT OR REPLACE INTO chats (chat_id, config) 
            VALUES (?, ?)
        """, (chat_id, config_json))
        self.conn.commit()
    
    def set_chat_owner(self, chat_id: int, owner_id: int) -> None:
        """Установить владельца чата"""
        self.conn.execute("""
            INSERT OR REPLACE INTO chats (chat_id, owner_id) 
            VALUES (?, ?)
        """, (chat_id, owner_id))
        self.conn.commit()
    
    def get_chat_owner(self, chat_id: int) -> Optional[int]:
        """Получить владельца чата"""
        cursor = self.conn.execute(
            "SELECT owner_id FROM chats WHERE chat_id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        return row['owner_id'] if row else None
    
    def add_bot_admin(self, chat_id: int, user_id: int, added_by: int) -> bool:
        """Добавить админа бота"""
        try:
            self.conn.execute("""
                INSERT OR IGNORE INTO bot_admins (chat_id, user_id, added_by)
                VALUES (?, ?, ?)
            """, (chat_id, user_id, added_by))
            self.conn.commit()
            return True
        except:
            return False
    
    def remove_bot_admin(self, chat_id: int, user_id: int) -> bool:
        """Удалить админа бота"""
        try:
            self.conn.execute("""
                DELETE FROM bot_admins 
                WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))
            self.conn.commit()
            return True
        except:
            return False
    
    def get_bot_admins(self, chat_id: int) -> List[int]:
        """Получить список админов бота"""
        cursor = self.conn.execute(
            "SELECT user_id FROM bot_admins WHERE chat_id = ?",
            (chat_id,)
        )
        return [row['user_id'] for row in cursor.fetchall()]
    
    def is_bot_admin(self, chat_id: int, user_id: int) -> bool:
        """Проверка является ли админом бота"""
        if user_id == self.get_chat_owner(chat_id):
            return True
        
        cursor = self.conn.execute("""
            SELECT 1 FROM bot_admins 
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user_id))
        return cursor.fetchone() is not None
    
    def add_exempt_user(self, chat_id: int, user_id: int, added_by: int, hours: int = 24) -> bool:
        """Добавить исключённого пользователя"""
        try:
            exempt_until = datetime.now() + timedelta(hours=hours)
            self.conn.execute("""
                INSERT OR REPLACE INTO exempt_users (chat_id, user_id, exempt_until, added_by)
                VALUES (?, ?, ?, ?)
            """, (chat_id, user_id, exempt_until.isoformat(), added_by))
            self.conn.commit()
            return True
        except:
            return False
    
    def remove_exempt_user(self, chat_id: int, user_id: int) -> bool:
        """Удалить исключённого пользователя"""
        try:
            self.conn.execute("""
                DELETE FROM exempt_users 
                WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))
            self.conn.commit()
            return True
        except:
            return False
    
    def get_exempt_users(self, chat_id: int) -> List[int]:
        """Получить список исключённых пользователей"""
        cursor = self.conn.execute("""
            SELECT user_id FROM exempt_users 
            WHERE chat_id = ? AND exempt_until > ?
        """, (chat_id, datetime.now().isoformat()))
        return [row['user_id'] for row in cursor.fetchall()]
    
    def is_exempt(self, chat_id: int, user_id: int) -> bool:
        """Проверка исключён ли пользователь"""
        cursor = self.conn.execute("""
            SELECT 1 FROM exempt_users 
            WHERE chat_id = ? AND user_id = ? AND exempt_until > ?
        """, (chat_id, user_id, datetime.now().isoformat()))
        return cursor.fetchone() is not None
    
    def add_message(self, chat_id: int, user_id: int, message_type: str = "text") -> None:
        """Добавить сообщение в историю"""
        self.conn.execute("""
            INSERT INTO message_history (chat_id, user_id, message_type)
            VALUES (?, ?, ?)
        """, (chat_id, user_id, message_type))
        self.conn.commit()
        
        # Очищаем старые записи (старше 1 часа)
        hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        self.conn.execute("""
            DELETE FROM message_history 
            WHERE timestamp < ?
        """, (hour_ago,))
        self.conn.commit()
    
    def get_message_count(self, chat_id: int, user_id: int, seconds: int) -> int:
        """Получить количество сообщений за период"""
        time_ago = (datetime.now() - timedelta(seconds=seconds)).isoformat()
        cursor = self.conn.execute("""
            SELECT COUNT(*) as count FROM message_history 
            WHERE chat_id = ? AND user_id = ? AND timestamp > ?
        """, (chat_id, user_id, time_ago))
        return cursor.fetchone()['count']
    
    def get_chat_message_rate(self, chat_id: int, seconds: int) -> float:
        """Получить скорость сообщений в чате"""
        time_ago = (datetime.now() - timedelta(seconds=seconds)).isoformat()
        cursor = self.conn.execute("""
            SELECT COUNT(*) as count FROM message_history 
            WHERE chat_id = ? AND timestamp > ?
        """, (chat_id, time_ago))
        count = cursor.fetchone()['count']
        return count / seconds if seconds > 0 else 0
    
    def log_action(self, chat_id: int, action_type: str, target_id: int = None, reason: str = "") -> None:
        """Логировать действие бота"""
        self.conn.execute("""
            INSERT INTO bot_actions (chat_id, action_type, target_id, reason)
            VALUES (?, ?, ?, ?)
        """, (chat_id, action_type, target_id, reason))
        self.conn.commit()
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        cursor = self.conn.execute("SELECT COUNT(DISTINCT chat_id) as chats FROM chats")
        chats = cursor.fetchone()['chats']
        
        cursor = self.conn.execute("SELECT COUNT(*) as actions FROM bot_actions")
        actions = cursor.fetchone()['actions']
        
        cursor = self.conn.execute("SELECT COUNT(DISTINCT user_id) as exempt FROM exempt_users")
        exempt = cursor.fetchone()['exempt']
        
        return {
            "chats": chats or 0,
            "actions": actions or 0,
            "exempt_users": exempt or 0
        }

# Глобальная БД
db = Database()

# ============ ЛОГИРОВАНИЕ ============

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ ОСНОВНАЯ ЛОГИКА ============

async def check_flood(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка на флуд"""
    config = db.get_chat_config(chat_id)
    
    # Проверяем исключения
    if db.is_exempt(chat_id, user_id):
        return False
    
    # Проверяем новых участников
    if config.get("exempt_new_members", True):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            join_date = member.joined_date or member.user.date
            if join_date:
                join_time = datetime.fromtimestamp(join_date)
                if datetime.now() - join_time < timedelta(hours=config.get("exempt_duration", 24)):
                    return False
        except:
            pass
    
    # Проверяем лимит сообщений
    message_count = db.get_message_count(
        chat_id, user_id, 
        config["time_window"]
    )
    
    if message_count >= config["max_messages"]:
        # Бан пользователя
        try:
            ban_until = datetime.now() + timedelta(hours=config["ban_hours"])
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=int(ban_until.timestamp())
            )
            
            # Логирование
            db.log_action(chat_id, "ban", user_id, f"Флуд: {message_count} сообщений за {config['time_window']} сек")
            
            # Уведомление
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚨 Пользователь забанен на {config['ban_hours']} ч. за флуд.",
                parse_mode=ParseMode.HTML
            )
            
            logger.info(f"User {user_id} banned in chat {chat_id} for flood")
            return True
        except Exception as e:
            logger.error(f"Ban error: {e}")
    
    return False

async def check_raid(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка на рейд"""
    config = db.get_chat_config(chat_id)
    
    message_rate = db.get_chat_message_rate(
        chat_id, 
        config["raid_window"]
    )
    
    if message_rate >= config["raid_threshold"]:
        if config["auto_lockdown"]:
            # Lockdown
            try:
                await context.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(
                        can_send_messages=False,
                        can_send_media_messages=False,
                        can_send_polls=False,
                        can_send_other_messages=False,
                        can_add_web_page_previews=False,
                        can_change_info=False,
                        can_invite_users=False,
                        can_pin_messages=False
                    )
                )
                
                db.log_action(chat_id, "lockdown", reason=f"Рейд: {message_rate:.1f} сообщ/сек")
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🔒 Чат заблокирован из-за высокой активности.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Lockdown error: {e}")
        
        elif config["auto_slowmode"]:
            # Slow mode
            try:
                await context.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(can_send_messages=True),
                    slow_mode_delay=config["slowmode_delay"]
                )
                
                db.log_action(chat_id, "slowmode", reason=f"Рейд: {message_rate:.1f} сообщ/сек")
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🐢 Включен медленный режим: {config['slowmode_delay']} сек.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Slowmode error: {e}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик сообщений"""
    if not update.message or not update.effective_chat:
        return
    
    chat = update.effective_chat
    user = update.effective_user
    
    # Игнорируем приватные чаты
    if chat.type == ChatType.PRIVATE:
        return
    
    # Определяем тип сообщения
    message_type = "text"
    if update.message.animation:
        message_type = "gif"
    elif update.message.sticker:
        message_type = "sticker"
    elif update.message.photo:
        message_type = "photo"
    elif update.message.video:
        message_type = "video"
    
    # Сохраняем в историю
    db.add_message(chat.id, user.id, message_type)
    
    # Игнорируем админов бота
    if db.is_bot_admin(chat.id, user.id):
        return
    
    # Проверяем флуд
    is_flood = await check_flood(chat.id, user.id, context)
    
    # Проверяем рейд (если не флуд)
    if not is_flood:
        await check_raid(chat.id, context)

# ============ КОМАНДЫ ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    if update.effective_chat.type == ChatType.PRIVATE:
        await update.message.reply_text(
            "🛡️ Anti-Raid Bot\n\n"
            "Добавьте меня в группу и назначьте администратором.\n\n"
            "Основные команды в группе:\n"
            "/setup - Настройка\n"
            "/settings - Текущие настройки\n"
            "/lock - Блокировка чата\n"
            "/unlock - Разблокировка\n"
            "/slow <сек> - Медленный режим\n"
            "/normal - Отключить медленный режим\n"
            "/exempt @user - Добавить исключение\n"
            "/unexempt @user - Удалить исключение\n"
            "/admins - Админы бота\n"
            "/exemptlist - Список исключений"
        )
    else:
        await update.message.reply_text(
            "🛡️ Anti-Raid Bot активен\n"
            "Используйте /help для помощи"
        )

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Настройка бота"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    # Проверяем права в Telegram
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            await update.message.reply_text("Только админы могут настраивать.")
            return
    except:
        await update.message.reply_text("Ошибка проверки прав.")
        return
    
    # Устанавливаем владельца если нет
    owner = db.get_chat_owner(chat.id)
    if not owner:
        db.set_chat_owner(chat.id, user.id)
        db.add_bot_admin(chat.id, user.id, user.id)
    
    # Показываем меню
    keyboard = [
        [InlineKeyboardButton("Настроить лимиты", callback_data="menu_limits")],
        [InlineKeyboardButton("Режимы защиты", callback_data="menu_modes")],
        [InlineKeyboardButton("Управление исключениями", callback_data="menu_exempt")],
        [InlineKeyboardButton("Текущие настройки", callback_data="menu_settings")]
    ]
    
    await update.message.reply_text(
        "⚙️ Настройка защиты",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Текущие настройки"""
    chat = update.effective_chat
    
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("Используйте в группе.")
        return
    
    config = db.get_chat_config(chat.id)
    
    text = (
        "⚙️ Текущие настройки:\n\n"
        f"📊 Лимиты:\n"
        f"• Сообщений: {config['max_messages']} за {config['time_window']} сек\n"
        f"• Порог рейда: {config['raid_threshold']} сообщ/сек\n"
        f"• Бан: {config['ban_hours']} часов\n\n"
        f"🔧 Режимы:\n"
        f"• Auto-Lockdown: {'✅' if config['auto_lockdown'] else '❌'}\n"
        f"• Auto-Slowmode: {'✅' if config['auto_slowmode'] else '❌'}\n"
        f"• Защита новых: {'✅' if config['exempt_new_members'] else '❌'}\n\n"
        f"👥 Исключения: {len(db.get_exempt_users(chat.id))} пользователей"
    )
    
    await update.message.reply_text(text)

async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Блокировка чата"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
        )
        
        db.log_action(chat.id, "manual_lockdown", user.id)
        await update.message.reply_text("🔒 Чат заблокирован.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Разблокировка чата"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
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

async def slow_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Медленный режим"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    delay = 30
    if context.args:
        try:
            delay = int(context.args[0])
            if delay < 0 or delay > 21600:
                delay = 30
        except:
            pass
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True),
            slow_mode_delay=delay
        )
        
        await update.message.reply_text(f"🐢 Медленный режим: {delay} сек.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def normal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отключить медленный режим"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True),
            slow_mode_delay=0
        )
        
        await update.message.reply_text("🚀 Медленный режим выключен.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def exempt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавить исключение"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /exempt @username или /exempt user_id")
        return
    
    target = context.args[0]
    
    try:
        # Пробуем найти по username
        if target.startswith("@"):
            username = target[1:]
            # В реальном боте нужно искать пользователя
            # Здесь упрощённо
            await update.message.reply_text(
                f"Укажите ID пользователя для @{username}\n"
                f"Используйте: /exempt_id 123456789"
            )
        else:
            # По ID
            target_id = int(target)
            
            # Проверяем не бот ли это
            bot_info = await context.bot.get_me()
            if target_id == bot_info.id:
                await update.message.reply_text("Нельзя добавить бота.")
                return
            
            # Добавляем исключение
            if db.add_exempt_user(chat.id, target_id, user.id, 24):
                await update.message.reply_text(f"✅ Пользователь {target} добавлен в исключения.")
            else:
                await update.message.reply_text("Ошибка.")
    except ValueError:
        await update.message.reply_text("Неверный ID.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def exempt_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавить исключение по ID"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /exempt_id 123456789")
        return
    
    try:
        target_id = int(context.args[0])
        
        # Проверяем не бот ли это
        bot_info = await context.bot.get_me()
        if target_id == bot_info.id:
            await update.message.reply_text("Нельзя добавить бота.")
            return
        
        # Добавляем исключение
        if db.add_exempt_user(chat.id, target_id, user.id, 24):
            await update.message.reply_text(f"✅ Пользователь {target_id} добавлен в исключения.")
        else:
            await update.message.reply_text("Ошибка.")
    except ValueError:
        await update.message.reply_text("Неверный ID.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def unexempt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить исключение"""
    chat = update.effective_chat
    user = update.effective_user
    
    if not db.is_bot_admin(chat.id, user.id):
        await update.message.reply_text("Нет прав.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /unexempt @username или /unexempt user_id")
        return
    
    target = context.args[0]
    
    try:
        if target.startswith("@"):
            await update.message.reply_text("Укажите ID пользователя.")
        else:
            target_id = int(target)
            
            if db.remove_exempt_user(chat.id, target_id):
                await update.message.reply_text(f"✅ Пользователь {target} удалён из исключений.")
            else:
                await update.message.reply_text("Пользователь не найден.")
    except ValueError:
        await update.message.reply_text("Неверный ID.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def exemptlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Список исключений"""
    chat = update.effective_chat
    
    exempt_users = db.get_exempt_users(chat.id)
    
    if not exempt_users:
        await update.message.reply_text("Нет исключений.")
        return
    
    text = "👥 Исключённые пользователи:\n\n"
    for i, user_id in enumerate(exempt_users, 1):
        text += f"{i}. ID: {user_id}\n"
    
    await update.message.reply_text(text)

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Список админов бота"""
    chat = update.effective_chat
    
    admins = db.get_bot_admins(chat.id)
    owner = db.get_chat_owner(chat.id)
    
    if not admins and not owner:
        await update.message.reply_text("Нет админов бота.")
        return
    
    text = "👑 Админы бота:\n\n"
    
    if owner:
        text += f"Владелец: ID {owner}\n\n"
    
    for i, admin_id in enumerate(admins, 1):
        if admin_id != owner:  # Не дублируем владельца
            text += f"{i}. ID: {admin_id}\n"
    
    await update.message.reply_text(text)

async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавить админа бота"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Только владелец может добавлять админов
    owner = db.get_chat_owner(chat.id)
    if user.id != owner:
        await update.message.reply_text("Только владелец может добавлять админов.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /promote @username или /promote user_id")
        return
    
    target = context.args[0]
    
    try:
        if target.startswith("@"):
            await update.message.reply_text("Укажите ID пользователя.")
        else:
            target_id = int(target)
            
            # Проверяем не бот ли это
            bot_info = await context.bot.get_me()
            if target_id == bot_info.id:
                await update.message.reply_text("Нельзя добавить бота.")
                return
            
            # Добавляем админа
            if db.add_bot_admin(chat.id, target_id, user.id):
                await update.message.reply_text(f"✅ Пользователь {target} добавлен в админы.")
            else:
                await update.message.reply_text("Ошибка или уже админ.")
    except ValueError:
        await update.message.reply_text("Неверный ID.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить админа бота"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Только владелец может удалять админов
    owner = db.get_chat_owner(chat.id)
    if user.id != owner:
        await update.message.reply_text("Только владелец может удалять админов.")
        return
    
    if not context.args:
        await update.message.reply_text("Использование: /demote @username или /demote user_id")
        return
    
    target = context.args[0]
    
    try:
        if target.startswith("@"):
            await update.message.reply_text("Укажите ID пользователя.")
        else:
            target_id = int(target)
            
            # Нельзя удалить владельца
            if target_id == owner:
                await update.message.reply_text("Нельзя удалить владельца.")
                return
            
            # Удаляем админа
            if db.remove_bot_admin(chat.id, target_id):
                await update.message.reply_text(f"✅ Пользователь {target} удалён из админов.")
            else:
                await update.message.reply_text("Пользователь не найден.")
    except ValueError:
        await update.message.reply_text("Неверный ID.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# ============ ИНЛАЙН МЕНЮ ============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    if not db.is_bot_admin(chat_id, user_id):
        await query.edit_message_text("Нет прав.")
        return
    
    config = db.get_chat_config(chat_id)
    
    if data == "menu_limits":
        keyboard = [
            [InlineKeyboardButton(f"Сообщений: {config['max_messages']}", callback_data="set_max_messages")],
            [InlineKeyboardButton(f"Окно: {config['time_window']} сек", callback_data="set_time_window")],
            [InlineKeyboardButton(f"Порог рейда: {config['raid_threshold']}", callback_data="set_raid_threshold")],
            [InlineKeyboardButton(f"Бан: {config['ban_hours']} ч", callback_data="set_ban_hours")],
            [InlineKeyboardButton("Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "📊 Настройка лимитов",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_modes":
        keyboard = [
            [InlineKeyboardButton(
                f"Auto-Lockdown: {'✅' if config['auto_lockdown'] else '❌'}",
                callback_data="toggle_lockdown"
            )],
            [InlineKeyboardButton(
                f"Auto-Slowmode: {'✅' if config['auto_slowmode'] else '❌'}",
                callback_data="toggle_slowmode"
            )],
            [InlineKeyboardButton(
                f"Защита новых: {'✅' if config['exempt_new_members'] else '❌'}",
                callback_data="toggle_exempt_new"
            )],
            [InlineKeyboardButton("Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "🔧 Режимы защиты",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_exempt":
        exempt_count = len(db.get_exempt_users(chat_id))
        keyboard = [
            [InlineKeyboardButton("Добавить исключение", callback_data="add_exempt")],
            [InlineKeyboardButton("Удалить исключение", callback_data="remove_exempt")],
            [InlineKeyboardButton(f"Список ({exempt_count})", callback_data="list_exempt")],
            [InlineKeyboardButton("Назад", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            "👥 Управление исключениями",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "menu_settings":
        await settings_command(query, context)
        return
    
    elif data == "back_main":
        keyboard = [
            [InlineKeyboardButton("Настроить лимиты", callback_data="menu_limits")],
            [InlineKeyboardButton("Режимы защиты", callback_data="menu_modes")],
            [InlineKeyboardButton("Управление исключениями", callback_data="menu_exempt")],
            [InlineKeyboardButton("Текущие настройки", callback_data="menu_settings")]
        ]
        
        await query.edit_message_text(
            "⚙️ Настройка защиты",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "toggle_lockdown":
        config["auto_lockdown"] = not config["auto_lockdown"]
        if config["auto_lockdown"]:
            config["auto_slowmode"] = False
        db.save_chat_config(chat_id, config)
        
        await query.answer(f"Auto-Lockdown {'включен' if config['auto_lockdown'] else 'выключен'}")
        await button_handler(update, context)  # Обновляем меню
    
    elif data == "toggle_slowmode":
        config["auto_slowmode"] = not config["auto_slowmode"]
        if config["auto_slowmode"]:
            config["auto_lockdown"] = False
        db.save_chat_config(chat_id, config)
        
        await query.answer(f"Auto-Slowmode {'включен' if config['auto_slowmode'] else 'выключен'}")
        await button_handler(update, context)
    
    elif data == "toggle_exempt_new":
        config["exempt_new_members"] = not config["exempt_new_members"]
        db.save_chat_config(chat_id, config)
        
        await query.answer(f"Защита новых {'включена' if config['exempt_new_members'] else 'выключена'}")
        await button_handler(update, context)
    
    elif data.startswith("set_"):
        param_map = {
            "set_max_messages": ("max_messages", "Введите число сообщений (1-100):"),
            "set_time_window": ("time_window", "Введите окно в секундах (1-60):"),
            "set_raid_threshold": ("raid_threshold", "Введите порог рейда (1-100):"),
            "set_ban_hours": ("ban_hours", "Введите часы бана (1-744):")
        }
        
        if data in param_map:
            param_name, prompt = param_map[data]
            context.user_data["waiting_param"] = param_name
            context.user_data["waiting_chat"] = chat_id
            
            await query.edit_message_text(
                f"{prompt}\n\n"
                "Отправьте число в чат.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="menu_limits")]])
            )
    
    elif data == "list_exempt":
        exempt_users = db.get_exempt_users(chat_id)
        
        if not exempt_users:
            text = "Нет исключённых пользователей."
        else:
            text = "👥 Исключённые пользователи:\n\n"
            for i, user_id in enumerate(exempt_users, 1):
                text += f"{i}. ID: {user_id}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu_exempt")]])
        )

async def param_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        
        # Валидация
        limits = {
            "max_messages": (1, 100),
            "time_window": (1, 60),
            "raid_threshold": (1, 100),
            "ban_hours": (1, 744)
        }
        
        if param_name in limits:
            min_val, max_val = limits[param_name]
            if value < min_val or value > max_val:
                await update.message.reply_text(f"Значение должно быть от {min_val} до {max_val}.")
                return
        
        # Сохраняем
        config = db.get_chat_config(chat_id)
        config[param_name] = value
        db.save_chat_config(chat_id, config)
        
        await update.message.reply_text(f"✅ Установлено: {value}")
        
        # Очищаем
        del context.user_data["waiting_param"]
        del context.user_data["waiting_chat"]
        
    except ValueError:
        await update.message.reply_text("Введите число.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# ============ ВЕБ-СЕРВЕР ============

class WebHandler(BaseHTTPRequestHandler):
    """Веб-сервер для Render"""
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            
            stats = db.get_stats()
            
            html_content = f"""
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Anti-Raid Bot</title>
                <style>
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    }}
                    
                    body {{
                        background: #0f172a;
                        color: #e2e8f0;
                        min-height: 100vh;
                        padding: 20px;
                    }}
                    
                    .container {{
                        max-width: 1000px;
                        margin: 0 auto;
                    }}
                    
                    header {{
                        text-align: center;
                        padding: 40px 0;
                        border-bottom: 1px solid #334155;
                        margin-bottom: 40px;
                    }}
                    
                    .logo {{
                        font-size: 3em;
                        margin-bottom: 10px;
                    }}
                    
                    h1 {{
                        font-size: 2em;
                        color: #60a5fa;
                        margin-bottom: 10px;
                    }}
                    
                    .subtitle {{
                        color: #94a3b8;
                        font-size: 1.1em;
                    }}
                    
                    .stats {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 20px;
                        margin-bottom: 40px;
                    }}
                    
                    .stat-card {{
                        background: #1e293b;
                        border-radius: 12px;
                        padding: 25px;
                        text-align: center;
                        border: 1px solid #334155;
                        transition: transform 0.2s;
                    }}
                    
                    .stat-card:hover {{
                        transform: translateY(-5px);
                        border-color: #60a5fa;
                    }}
                    
                    .stat-number {{
                        font-size: 2.5em;
                        font-weight: bold;
                        color: #60a5fa;
                        margin-bottom: 10px;
                    }}
                    
                    .stat-label {{
                        color: #94a3b8;
                        font-size: 0.9em;
                    }}
                    
                    .section {{
                        background: #1e293b;
                        border-radius: 12px;
                        padding: 30px;
                        margin-bottom: 30px;
                        border: 1px solid #334155;
                    }}
                    
                    .section-title {{
                        color: #60a5fa;
                        font-size: 1.5em;
                        margin-bottom: 20px;
                        padding-bottom: 10px;
                        border-bottom: 1px solid #334155;
                    }}
                    
                    .features {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                        gap: 15px;
                    }}
                    
                    .feature {{
                        background: #0f172a;
                        padding: 20px;
                        border-radius: 8px;
                        border-left: 4px solid #60a5fa;
                    }}
                    
                    .feature-title {{
                        color: #e2e8f0;
                        margin-bottom: 10px;
                        font-weight: 500;
                    }}
                    
                    .feature-desc {{
                        color: #94a3b8;
                        font-size: 0.9em;
                        line-height: 1.5;
                    }}
                    
                    .commands {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                        gap: 15px;
                    }}
                    
                    .command-group {{
                        background: #0f172a;
                        padding: 20px;
                        border-radius: 8px;
                    }}
                    
                    .group-title {{
                        color: #60a5fa;
                        margin-bottom: 15px;
                        font-weight: 500;
                    }}
                    
                    .command {{
                        margin-bottom: 10px;
                        padding-left: 15px;
                        border-left: 2px solid #334155;
                    }}
                    
                    .cmd {{
                        color: #e2e8f0;
                        font-family: monospace;
                        font-size: 0.9em;
                        margin-bottom: 5px;
                    }}
                    
                    .desc {{
                        color: #94a3b8;
                        font-size: 0.85em;
                    }}
                    
                    .terms {{
                        line-height: 1.6;
                        color: #94a3b8;
                    }}
                    
                    .terms h3 {{
                        color: #e2e8f0;
                        margin: 20px 0 10px 0;
                    }}
                    
                    .terms ul {{
                        margin-left: 20px;
                        margin-bottom: 15px;
                    }}
                    
                    .terms li {{
                        margin-bottom: 5px;
                    }}
                    
                    footer {{
                        text-align: center;
                        padding: 30px 0;
                        color: #64748b;
                        font-size: 0.9em;
                        border-top: 1px solid #334155;
                        margin-top: 40px;
                    }}
                    
                    .status {{
                        display: inline-block;
                        padding: 8px 16px;
                        background: #10b981;
                        color: white;
                        border-radius: 20px;
                        font-weight: 500;
                        animation: pulse 2s infinite;
                    }}
                    
                    @keyframes pulse {{
                        0% {{ opacity: 1; }}
                        50% {{ opacity: 0.7; }}
                        100% {{ opacity: 1; }}
                    }}
                    
                    @media (max-width: 600px) {{
                        .container {{
                            padding: 10px;
                        }}
                        
                        header {{
                            padding: 20px 0;
                        }}
                        
                        .logo {{
                            font-size: 2em;
                        }}
                        
                        h1 {{
                            font-size: 1.5em;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <header>
                        <div class="logo">🛡️</div>
                        <h1>Anti-Raid Bot</h1>
                        <p class="subtitle">Защита Telegram чатов от рейдов и спама</p>
                        <div style="margin-top: 20px;">
                            <span class="status">✓ Бот активен</span>
                        </div>
                    </header>
                    
                    <div class="stats">
                        <div class="stat-card">
                            <div class="stat-number">{stats['chats']}</div>
                            <div class="stat-label">Защищаемых чатов</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{stats['actions']}</div>
                            <div class="stat-label">Защитных действий</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{stats['exempt_users']}</div>
                            <div class="stat-label">Исключённых пользователей</div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2 class="section-title">📋 Функции</h2>
                        <div class="features">
                            <div class="feature">
                                <div class="feature-title">Защита от рейдов</div>
                                <div class="feature-desc">Автоматическое обнаружение массовых атак и блокировка чата</div>
                            </div>
                            <div class="feature">
                                <div class="feature-title">Анти-флуд</div>
                                <div class="feature-desc">Контроль скорости сообщений от пользователей</div>
                            </div>
                            <div class="feature">
                                <div class="feature-title">Исключения</div>
                                <div class="feature-desc">Добавление пользователей в белый список</div>
                            </div>
                            <div class="feature">
                                <div class="feature-title">Гибкие настройки</div>
                                <div class="feature-desc">Настройка всех параметров через меню</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2 class="section-title">💬 Команды</h2>
                        <div class="commands">
                            <div class="command-group">
                                <div class="group-title">Основные</div>
                                <div class="command">
                                    <div class="cmd">/setup</div>
                                    <div class="desc">Настройка бота</div>
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
                                <div class="group-title">Исключения</div>
                                <div class="command">
                                    <div class="cmd">/exempt_id 123456</div>
                                    <div class="desc">Добавить исключение по ID</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/unexempt 123456</div>
                                    <div class="desc">Удалить исключение</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/exemptlist</div>
                                    <div class="desc">Список исключений</div>
                                </div>
                            </div>
                            
                            <div class="command-group">
                                <div class="group-title">Администрирование</div>
                                <div class="command">
                                    <div class="cmd">/promote 123456</div>
                                    <div class="desc">Добавить админа бота</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/demote 123456</div>
                                    <div class="desc">Удалить админа бота</div>
                                </div>
                                <div class="command">
                                    <div class="cmd">/admins</div>
                                    <div class="desc">Список админов</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2 class="section-title">📄 Пользовательское соглашение</h2>
                        <div class="terms">
                            <h3>1. Использование бота</h3>
                            <p>Бот предназначен для защиты Telegram чатов от нежелательной активности.</p>
                            
                            <h3>2. Ответственность</h3>
                            <p>Администраторы чатов несут ответственность за настройку и использование бота.</p>
                            
                            <h3>3. Данные</h3>
                            <p>Бот хранит минимально необходимые данные для работы:</p>
                            <ul>
                                <li>ID чатов и пользователей</li>
                                <li>Настройки защиты</li>
                                <li>Историю сообщений (очищается автоматически)</li>
                            </ul>
                            
                            <h3>4. Ограничения</h3>
                            <p>Бот не может:</p>
                            <ul>
                                <li>Читать текст сообщений</li>
                                <li>Хранить личные данные</li>
                                <li>Передавать данные третьим лицам</li>
                            </ul>
                        </div>
                    </div>
                    
                    <footer>
                        <p>Anti-Raid Bot System</p>
                        <p>© 2024 | Сервер работает на Render.com</p>
                        <p>Время: {datetime.now().strftime("%d.%m.%Y %H:%M")}</p>
                    </footer>
                </div>
            </body>
            </html>
            """
            
            self.wfile.write(html_content.encode("utf-8"))
        
        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response = {"status": "ok", "time": datetime.now().isoformat()}
            self.wfile.write(json.dumps(response).encode())
        
        elif parsed.path == "/stats":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            stats = db.get_stats()
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
    print(f"Веб-сервер запущен: http://localhost:{port}")
    server.serve_forever()

# ============ ГЛАВНАЯ ФУНКЦИЯ ============

start_time = datetime.now()

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
    """Запуск бота"""
    config = load_config()
    
    if config["token"] == "ВАШ_ТОКЕН_ОТ_BOTFATHER":
        print("Установите токен в config.json")
        return
    
    # Запуск веб-сервера
    if config.get("web_enabled", True):
        web_thread = threading.Thread(
            target=run_web_server,
            args=(config.get("web_port", 8080),),
            daemon=True
        )
        web_thread.start()
        print("Веб-сервер запущен")
    
    # Создание приложения
    application = Application.builder().token(config["token"]).build()
    
    # Команды
    commands = [
        ("start", start_command),
        ("setup", setup_command),
        ("settings", settings_command),
        ("lock", lock_command),
        ("unlock", unlock_command),
        ("slow", slow_command),
        ("normal", normal_command),
        ("exempt", exempt_command),
        ("exempt_id", exempt_id_command),
        ("unexempt", unexempt_command),
        ("exemptlist", exemptlist_command),
        ("admins", admins_command),
        ("promote", promote_command),
        ("demote", demote_command),
        ("help", start_command)
    ]
    
    for cmd, handler in commands:
        application.add_handler(CommandHandler(cmd, handler))
    
    # Кнопки
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Ввод параметров
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        param_input_handler
    ))
    
    # Основной обработчик
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        message_handler
    ))
    
    # Запуск
    print("Бот запущен")
    print("Готов к работе")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Бесконечный цикл
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Создание файлов
    if not Path("config.json").exists():
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print("Создан config.json")
        print("Установите токен бота")
    
    if not Path("requirements.txt").exists():
        with open("requirements.txt", "w", encoding="utf-8") as f:
            f.write("python-telegram-bot[job-queue]==20.7\n")
        print("Создан requirements.txt")
    
    if not Path("Procfile").exists():
        with open("Procfile", "w", encoding="utf-8") as f:
            f.write("web: python bot.py")
        print("Создан Procfile")
    
    # Запуск
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановка")
    except Exception as e:
        print(f"Ошибка: {e}")
