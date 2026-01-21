#!/usr/bin/env python3
"""
🛡️ ANTI-RAID BOT - ПОЛНАЯ ВЕРСИЯ
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
            CREATE TABLE IF NOT EXISTS чаты (
                id INTEGER PRIMARY KEY,
                владелец_id INTEGER,
                настройки TEXT,
                создано TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS админы_бота (
                чат_id INTEGER,
                юзер_id INTEGER,
                юзернейм TEXT,
                добавлено TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (чат_id, юзер_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS исключения (
                чат_id INTEGER,
                юзер_id INTEGER,
                юзернейм TEXT,
                причина TEXT,
                добавлено TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (чат_id, юзер_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS варны (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                чат_id INTEGER,
                юзер_id INTEGER,
                время TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS история_сообщений (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                чат_id INTEGER,
                юзер_id INTEGER,
                тип TEXT,
                время TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS логи (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                чат_id INTEGER,
                действие TEXT,
                цель_id INTEGER,
                время TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    # ЧАТЫ
    def получить_настройки(self, chat_id: int) -> Dict:
        cursor = self.conn.execute(
            "SELECT настройки FROM чаты WHERE id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        if row and row['настройки']:
            config = json.loads(row['настройки'])
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
        return DEFAULT_CONFIG.copy()
    
    def сохранить_настройки(self, chat_id: int, config: Dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO чаты (id, настройки) VALUES (?, ?)",
            (chat_id, json.dumps(config))
        )
        self.conn.commit()
    
    def установить_владельца(self, chat_id: int, user_id: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO чаты (id, владелец_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        self.conn.commit()
        self.добавить_админа(chat_id, user_id, user_id)
    
    def получить_владельца(self, chat_id: int) -> Optional[int]:
        cursor = self.conn.execute(
            "SELECT владелец_id FROM чаты WHERE id = ?",
            (chat_id,)
        )
        row = cursor.fetchone()
        return row['владелец_id'] if row else None
    
    # АДМИНЫ
    def добавить_админа(self, chat_id: int, user_id: int, added_by: int, username: str = None):
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO админы_бота (чат_id, юзер_id, юзернейм) VALUES (?, ?, ?)",
                (chat_id, user_id, username)
            )
            self.conn.commit()
        except:
            pass
    
    def удалить_админа(self, chat_id: int, user_id: int):
        self.conn.execute(
            "DELETE FROM админы_бота WHERE чат_id = ? AND юзер_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()
    
    def получить_админов(self, chat_id: int) -> List[Tuple[int, str]]:
        cursor = self.conn.execute(
            "SELECT юзер_id, юзернейм FROM админы_бота WHERE чат_id = ?",
            (chat_id,)
        )
        return [(row['юзер_id'], row['юзернейм']) for row in cursor.fetchall()]
    
    def является_админом(self, chat_id: int, user_id: int) -> bool:
        if user_id == self.получить_владельца(chat_id):
            return True
        
        cursor = self.conn.execute(
            "SELECT 1 FROM админы_бота WHERE чат_id = ? AND юзер_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None
    
    # ИСКЛЮЧЕНИЯ
    def добавить_исключение(self, chat_id: int, user_id: int, username: str = None, причина: str = ""):
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO исключения (чат_id, юзер_id, юзернейм, причина) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, username, причина)
            )
            self.conn.commit()
        except:
            pass
    
    def удалить_исключение(self, chat_id: int, user_id: int):
        self.conn.execute(
            "DELETE FROM исключения WHERE чат_id = ? AND юзер_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()
    
    def получить_исключения(self, chat_id: int) -> List[Tuple[int, str]]:
        cursor = self.conn.execute(
            "SELECT юзер_id, юзернейм FROM исключения WHERE чат_id = ?",
            (chat_id,)
        )
        return [(row['юзер_id'], row['юзернейм']) for row in cursor.fetchall()]
    
    def является_исключением(self, chat_id: int, user_id: int) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM исключения WHERE чат_id = ? AND юзер_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None
    
    # ВАРНЫ
    def добавить_варн(self, chat_id: int, user_id: int):
        self.conn.execute(
            "INSERT INTO варны (чат_id, юзер_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        # Очистка старых варнов (старше 6 часов)
        час_назад = datetime.now() - timedelta(hours=6)
        self.conn.execute(
            "DELETE FROM варны WHERE время < ?",
            (час_назад.timestamp(),)
        )
        self.conn.commit()
    
    def получить_варны(self, chat_id: int, user_id: int) -> int:
        час_назад = datetime.now() - timedelta(hours=6)
        cursor = self.conn.execute(
            "SELECT COUNT(*) as count FROM варны WHERE чат_id = ? AND юзер_id = ? AND время > ?",
            (chat_id, user_id, час_назад.timestamp())
        )
        return cursor.fetchone()['count']
    
    def очистить_варны(self, chat_id: int, user_id: int):
        self.conn.execute(
            "DELETE FROM варны WHERE чат_id = ? AND юзер_id = ?",
            (chat_id, user_id)
        )
        self.conn.commit()
    
    # ИСТОРИЯ
    def добавить_сообщение(self, chat_id: int, user_id: int, тип: str):
        self.conn.execute(
            "INSERT INTO история_сообщений (чат_id, юзер_id, тип) VALUES (?, ?, ?)",
            (chat_id, user_id, тип)
        )
        # Очистка старых сообщений (старше 1 часа)
        час_назад = datetime.now() - timedelta(hours=1)
        self.conn.execute(
            "DELETE FROM история_сообщений WHERE время < ?",
            (час_назад.timestamp(),)
        )
        self.conn.commit()
    
    def получить_статистику(self, chat_id: int, user_id: int, секунды: int) -> Dict[str, int]:
        время_назад = datetime.now() - timedelta(seconds=секунды)
        
        cursor = self.conn.execute(
            "SELECT тип, COUNT(*) as count FROM история_сообщений WHERE чат_id = ? AND юзер_id = ? AND время > ? GROUP BY тип",
            (chat_id, user_id, время_назад.timestamp())
        )
        
        stats = {"текст": 0, "медиа": 0, "всего": 0}
        for row in cursor.fetchall():
            if row['тип'] == "текст":
                stats["текст"] = row['count']
            else:
                stats["медиа"] += row['count']
            stats["всего"] += row['count']
        
        return stats
    
    def получить_активность(self, chat_id: int, секунды: int) -> float:
        время_назад = datetime.now() - timedelta(seconds=секунды)
        cursor = self.conn.execute(
            "SELECT COUNT(*) as count FROM история_сообщений WHERE чат_id = ? AND время > ?",
            (chat_id, время_назад.timestamp())
        )
        count = cursor.fetchone()['count']
        return count / секунды if секунды > 0 else 0
    
    # ЛОГИ
    def записать_лог(self, chat_id: int, действие: str, цель_id: int = None):
        self.conn.execute(
            "INSERT INTO логи (чат_id, действие, цель_id) VALUES (?, ?, ?)",
            (chat_id, действие, цель_id)
        )
        self.conn.commit()
    
    def получить_логи(self, chat_id: int, limit: int = 10) -> List[Dict]:
        cursor = self.conn.execute(
            "SELECT действие, цель_id, время FROM логи WHERE чат_id = ? ORDER BY время DESC LIMIT ?",
            (chat_id, limit)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    # СТАТИСТИКА
    def получить_статистику_бота(self) -> Dict:
        cursor = self.conn.execute("SELECT COUNT(DISTINCT id) as чаты FROM чаты")
        чаты = cursor.fetchone()['чаты'] or 0
        
        cursor = self.conn.execute("SELECT COUNT(*) as действия FROM логи")
        действия = cursor.fetchone()['действия'] or 0
        
        cursor = self.conn.execute("SELECT COUNT(DISTINCT юзер_id) as исключения FROM исключения")
        исключения = cursor.fetchone()['исключения'] or 0
        
        return {"чаты": чаты, "действия": действия, "исключения": исключения}

база = Database()

# ============ ЛОГИРОВАНИЕ ============

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
логгер = logging.getLogger(__name__)

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def разрешить_пользователя(идентификатор: str, контекст: ContextTypes.DEFAULT_TYPE, 
                                сообщение: Message = None) -> Optional[Tuple[int, str]]:
    """Определяет пользователя по reply, username или ID"""
    
    # Ответ на сообщение
    if сообщение and сообщение.reply_to_message:
        reply_user = сообщение.reply_to_message.from_user
        if reply_user:
            return reply_user.id, reply_user.username or reply_user.first_name
    
    идентификатор = идентификатор.strip().replace('@', '')
    
    # Если пусто и есть reply
    if not идентификатор and сообщение and сообщение.reply_to_message:
        reply_user = сообщение.reply_to_message.from_user
        if reply_user:
            return reply_user.id, reply_user.username or reply_user.first_name
    
    # Если ID
    if идентификатор.isdigit():
        return int(идентификатор), None
    
    return None

async def защищенный(chat_id: int, user_id: int, контекст: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет защищён ли пользователь"""
    настройки = база.получить_настройки(chat_id)
    
    if база.является_исключением(chat_id, user_id):
        return True
    
    if настройки.get("игнор_админов_бота", True) and база.является_админом(chat_id, user_id):
        return True
    
    if настройки.get("игнор_админов", True):
        try:
            member = await контекст.bot.get_chat_member(chat_id, user_id)
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return True
        except:
            pass
    
    if настройки.get("защита_новых", True):
        try:
            member = await контекст.bot.get_chat_member(chat_id, user_id)
            if hasattr(member, 'joined_date') and member.joined_date:
                время_вступления = datetime.fromtimestamp(member.joined_date)
                if datetime.now() - время_вступления < timedelta(hours=24):
                    return True
        except:
            pass
    
    return False

async def тип_сообщения(update: Update) -> str:
    """Определяет тип сообщения"""
    if update.message.text:
        return "текст"
    elif update.message.photo or update.message.video or update.message.animation:
        return "медиа"
    elif update.message.sticker:
        return "стикер"
    else:
        return "другое"

# ============ ЗАЩИТА ============

async def проверка_флуда(update: Update, контекст: ContextTypes.DEFAULT_TYPE) -> bool:
    чат = update.effective_chat
    пользователь = update.effective_user
    
    if чат.type == ChatType.PRIVATE:
        return False
    
    if await защищенный(chat.id, пользователь.id, контекст):
        return False
    
    тип = await тип_сообщения(update)
    база.добавить_сообщение(chat.id, пользователь.id, тип)
    
    настройки = база.получить_настройки(chat.id)
    статистика = база.получить_статистику(chat.id, пользователь.id, настройки["окно_времени"])
    
    лимит_текста = настройки["текст_лимит"]
    лимит_медиа = настройки["медиа_лимит"]
    
    if статистика["текст"] >= лимит_текста or статистика["медиа"] >= лимит_медиа:
        варны = база.получить_варны(chat.id, пользователь.id)
        варны_до_бана = настройки.get("варны_до_бана", 2)
        
        if варны < варны_до_бана - 1:
            база.добавить_варн(chat.id, пользователь.id)
            await update.message.reply_text(f"⚠️ Предупреждение {варны + 1}/{варны_до_бана}")
            return True
        else:
            try:
                if настройки.get("бан_часы", 0) > 0:
                    время_бана = datetime.now() + timedelta(hours=настройки["бан_часы"])
                    await контекст.bot.ban_chat_member(
                        chat_id=chat.id,
                        user_id=пользователь.id,
                        until_date=int(время_бана.timestamp())
                    )
                    действие = "бан"
                    время = f"{настройки['бан_часы']}ч"
                else:
                    время_мута = datetime.now() + timedelta(minutes=настройки.get("мут_минуты", 30))
                    await контекст.bot.restrict_chat_member(
                        chat_id=chat.id,
                        user_id=пользователь.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=int(время_мута.timestamp())
                    )
                    действие = "мут"
                    время = f"{настройки['мут_минуты']}м"
                
                база.записать_лог(chat.id, действие, пользователь.id)
                база.очистить_варны(chat.id, пользователь.id)
                
                await update.message.reply_text(f"🚨 Пользователь {'забанен' if действие == 'бан' else 'замучен'} на {время}")
                return True
                
            except Exception as e:
                логгер.error(f"Ошибка: {e}")
    
    return False

async def проверка_рейда(chat_id: int, контекст: ContextTypes.DEFAULT_TYPE):
    настройки = база.получить_настройки(chat_id)
    активность = база.получить_активность(chat_id, настройки["окно_рейда"])
    
    if активность >= настройки["порог_рейда"]:
        if настройки["авто_блокировка"]:
            try:
                await контекст.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                база.записать_лог(chat_id, "блокировка")
                await контекст.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔒 Чат заблокирован на {настройки['блокировка_время']} минут"
                )
                
                async def разблокировать():
                    await asyncio.sleep(настройки['блокировка_время'] * 60)
                    try:
                        await контекст.bot.set_chat_permissions(
                            chat_id=chat_id,
                            permissions=ChatPermissions(can_send_messages=True)
                        )
                    except:
                        pass
                
                asyncio.create_task(разблокировать())
                
            except Exception as e:
                логгер.error(f"Ошибка блокировки: {e}")
        elif настройки["авто_медленный"]:
            try:
                await контекст.bot.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=ChatPermissions(can_send_messages=True),
                    slow_mode_delay=настройки["задержка_медленного"]
                )
                await контекст.bot.send_message(
                    chat_id=chat_id,
                    text=f"🐢 Медленный режим: {настройки['задержка_медленного']} сек"
                )
            except:
                pass

async def обработчик_сообщений(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return
    
    чат = update.effective_chat
    if чат.type == ChatType.PRIVATE:
        return
    
    флуд = await проверка_флуда(update, контекст)
    if not флуд:
        await проверка_рейда(chat.id, контекст)

# ============ КОМАНДЫ ============

async def команда_старт(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    текст = """🛡️ Anti-Raid Bot

📋 Команды:
/setup - Настройка
/settings - Настройки
/status - Статус
/lock - Блокировка
/unlock - Разблокировка
/slow <сек> - Медленный режим
/normal - Выключить медленный режим

👥 Команды через ! (работают с reply):
!адм *ответ* - Добавить админа
!снять *ответ* - Удалить админа
!искл *ответ* - Добавить исключение
!нискл *ответ* - Удалить исключение
!варн *ответ* - Выдать варн
!варны *ответ* - Посмотреть варны
!снятьварны *ответ* - Снять варны

📊 Другие:
/админы - Список админов
/исключения - Список исключений
/stats - Статистика
/logs - Логи

💡 Пример: Ответьте на сообщение и напишите !адм
"""
    await update.message.reply_text(текст)

async def команда_настройка(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    чат = update.effective_chat
    пользователь = update.effective_user
    
    if чат.type == ChatType.PRIVATE:
        await update.message.reply_text("В группе")
        return
    
    try:
        member = await контекст.bot.get_chat_member(chat.id, пользователь.id)
        if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            await update.message.reply_text("Нужны права админа")
            return
    except:
        await update.message.reply_text("Ошибка")
        return
    
    владелец = база.получить_владельца(chat.id)
    if not владелец:
        база.установить_владельца(chat.id, пользователь.id)
        await update.message.reply_text("✅ Вы владелец")
    
    клавиатура = [
        [InlineKeyboardButton("📊 Анти-флуд", callback_data="меню_флуд")],
        [InlineKeyboardButton("🛡️ Анти-рейд", callback_data="меню_рейд")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="меню_настройки")],
        [InlineKeyboardButton("👥 Исключения", callback_data="меню_исключения")],
        [InlineKeyboardButton("👑 Админы", callback_data="меню_админы")],
        [InlineKeyboardButton("📊 Статистика", callback_data="меню_статистика")]
    ]
    
    await update.message.reply_text(
        "⚙️ Панель управления:",
        reply_markup=InlineKeyboardMarkup(клавиатура)
    )

async def команда_настройки(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    чат = update.effective_chat
    
    if чат.type == ChatType.PRIVATE:
        await update.message.reply_text("В группе")
        return
    
    настройки = база.получить_настройки(chat.id)
    
    текст = f"""⚙️ Настройки:

📊 Анти-флуд:
• Текст: {настройки['текст_лимит']}/{настройки['окно_времени']}сек
• Медиа: {настройки['медиа_лимит']}/{настройки['окно_времени']}сек
• Строгий: {'✅' if настройки['строгий_режим'] else '❌'}

🛡️ Анти-рейд:
• Порог: {настройки['порог_рейда']}/сек
• Блокировка: {настройки['блокировка_время']}м

⚖️ Наказания:
• Бан: {настройки['бан_часы']}ч
• Мут: {настройки['мут_минуты']}м
• Варны до бана: {настройки['варны_до_бана']}

👥 Защита:
• Исключения: {len(база.получить_исключения(chat.id))}
• Админы: {len(база.получить_админов(chat.id))}
"""
    
    await update.message.reply_text(текст)

async def команда_адм(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """!адм - добавить админа"""
    чат = update.effective_chat
    пользователь = update.effective_user
    сообщение = update.message
    
    if чат.type == ChatType.PRIVATE:
        return
    
    владелец = база.получить_владельца(chat.id)
    if пользователь.id != владелец:
        await update.message.reply_text("Только владелец")
        return
    
    аргумент = контекст.args[0] if контекст.args else ""
    результат = await разрешить_пользователя(аргумент, контекст, сообщение)
    
    if not результат:
        await update.message.reply_text("Ответьте на сообщение или укажите ID")
        return
    
    цель_id, цель_юзернейм = результат
    
    if цель_id == пользователь.id:
        return
    
    бот_инфо = await контекст.bot.get_me()
    if цель_id == бот_инфо.id:
        await update.message.reply_text("Нельзя бота")
        return
    
    база.добавить_админа(chat.id, цель_id, пользователь.id, цель_юзернейм)
    отображение = f"@{цель_юзернейм}" if цель_юзернейм else f"ID {цель_id}"
    await update.message.reply_text(f"✅ {отображение} теперь админ")

async def команда_снять(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """!снять - удалить админа"""
    чат = update.effective_chat
    пользователь = update.effective_user
    сообщение = update.message
    
    if чат.type == ChatType.PRIVATE:
        return
    
    владелец = база.получить_владельца(chat.id)
    if пользователь.id != владелец:
        await update.message.reply_text("Только владелец")
        return
    
    аргумент = контекст.args[0] if контекст.args else ""
    результат = await разрешить_пользователя(аргумент, контекст, сообщение)
    
    if not результат:
        await update.message.reply_text("Ответьте на сообщение или укажите ID")
        return
    
    цель_id, цель_юзернейм = результат
    
    if цель_id == владелец:
        await update.message.reply_text("Нельзя владельца")
        return
    
    база.удалить_админа(chat.id, цель_id)
    отображение = f"@{цель_юзернейм}" if цель_юзернейм else f"ID {цель_id}"
    await update.message.reply_text(f"✅ {отображение} больше не админ")

async def команда_искл(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """!искл - добавить исключение"""
    чат = update.effective_chat
    пользователь = update.effective_user
    сообщение = update.message
    
    if чат.type == ChatType.PRIVATE:
        return
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    аргумент = контекст.args[0] if контекст.args else ""
    результат = await разрешить_пользователя(аргумент, контекст, сообщение)
    
    if not результат:
        await update.message.reply_text("Ответьте на сообщение или укажите ID")
        return
    
    цель_id, цель_юзернейм = результат
    
    база.добавить_исключение(chat.id, цель_id, цель_юзернейм, "команда")
    отображение = f"@{цель_юзернейм}" if цель_юзернейм else f"ID {цель_id}"
    await update.message.reply_text(f"✅ {отображение} в исключениях")

async def команда_нискл(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """!нискл - удалить исключение"""
    чат = update.effective_chat
    пользователь = update.effective_user
    сообщение = update.message
    
    if чат.type == ChatType.PRIVATE:
        return
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    аргумент = контекст.args[0] if контекст.args else ""
    результат = await разрешить_пользователя(аргумент, контекст, сообщение)
    
    if not результат:
        await update.message.reply_text("Ответьте на сообщение или укажите ID")
        return
    
    цель_id, цель_юзернейм = результат
    
    база.удалить_исключение(chat.id, цель_id)
    отображение = f"@{цель_юзернейм}" if цель_юзернейм else f"ID {цель_id}"
    await update.message.reply_text(f"✅ {отображение} удалён из исключений")

async def команда_варн(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """!варн - выдать варн"""
    чат = update.effective_chat
    пользователь = update.effective_user
    сообщение = update.message
    
    if чат.type == ChatType.PRIVATE:
        return
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    аргумент = контекст.args[0] if контекст.args else ""
    результат = await разрешить_пользователя(аргумент, контекст, сообщение)
    
    if not результат:
        await update.message.reply_text("Ответьте на сообщение или укажите ID")
        return
    
    цель_id, цель_юзернейм = результат
    
    if await защищенный(chat.id, цель_id, контекст):
        await update.message.reply_text("Пользователь защищён")
        return
    
    база.добавить_варн(chat.id, цель_id)
    варны = база.получить_варны(chat.id, цель_id)
    настройки = база.получить_настройки(chat.id)
    
    отображение = f"@{цель_юзернейм}" if цель_юзернейм else f"ID {цель_id}"
    await update.message.reply_text(f"⚠️ {отображение} варн {варны}/{настройки['варны_до_бана']}")
    
    if варны >= настройки['варны_до_бана']:
        try:
            await контекст.bot.ban_chat_member(
                chat_id=chat.id,
                user_id=цель_id,
                until_date=int((datetime.now() + timedelta(hours=2)).timestamp())
            )
            await update.message.reply_text(f"🚨 {отображение} забанен за варны")
            база.очистить_варны(chat.id, цель_id)
        except Exception as e:
            логгер.error(f"Ошибка: {e}")

async def команда_варны(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """!варны - посмотреть варны"""
    чат = update.effective_chat
    пользователь = update.effective_user
    сообщение = update.message
    
    if чат.type == ChatType.PRIVATE:
        return
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    аргумент = контекст.args[0] if контекст.args else ""
    
    if not аргумент and not сообщение.reply_to_message:
        варны = база.получить_варны(chat.id, пользователь.id)
        await update.message.reply_text(f"Ваши варны: {варны}/2")
        return
    
    результат = await разрешить_пользователя(аргумент, контекст, сообщение)
    
    if not результат:
        await update.message.reply_text("Ответьте на сообщение или укажите ID")
        return
    
    цель_id, цель_юзернейм = результат
    варны = база.получить_варны(chat.id, цель_id)
    
    отображение = f"@{цель_юзернейм}" if цель_юзернейм else f"ID {цель_id}"
    await update.message.reply_text(f"⚠️ {отображение} варн: {варны}/2")

async def команда_снятьварны(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """!снятьварны - снять варны"""
    чат = update.effective_chat
    пользователь = update.effective_user
    сообщение = update.message
    
    if чат.type == ChatType.PRIVATE:
        return
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    аргумент = контекст.args[0] if контекст.args else ""
    результат = await разрешить_пользователя(аргумент, контекст, сообщение)
    
    if not результат:
        await update.message.reply_text("Ответьте на сообщение или укажите ID")
        return
    
    цель_id, цель_юзернейм = результат
    
    база.очистить_варны(chat.id, цель_id)
    отображение = f"@{цель_юзернейм}" if цель_юзернейм else f"ID {цель_id}"
    await update.message.reply_text(f"✅ {отображение} варны сняты")

async def команда_админы(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/админы - список админов"""
    чат = update.effective_chat
    
    if чат.type == ChatType.PRIVATE:
        await update.message.reply_text("В группе")
        return
    
    админы = база.получить_админов(chat.id)
    владелец = база.получить_владельца(chat.id)
    
    if not админы:
        await update.message.reply_text("Нет админов")
        return
    
    текст = "👑 Админы бота:\n\n"
    
    for юзер_id, юзернейм in админы:
        if юзер_id == владелец:
            отображение = f"@{юзернейм}" if юзернейм else f"ID {юзер_id}"
            текст += f"• {отображение} 👑 (владелец)\n"
        else:
            отображение = f"@{юзернейм}" if юзернейм else f"ID {юзер_id}"
            текст += f"• {отображение}\n"
    
    await update.message.reply_text(текст)

async def команда_исключения(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/исключения - список исключений"""
    чат = update.effective_chat
    
    if чат.type == ChatType.PRIVATE:
        await update.message.reply_text("В группе")
        return
    
    исключения = база.получить_исключения(chat.id)
    
    if not исключения:
        await update.message.reply_text("Нет исключений")
        return
    
    текст = "👥 Исключения:\n\n"
    for юзер_id, юзернейм in исключения:
        отображение = f"@{юзернейм}" if юзернейм else f"ID {юзер_id}"
        текст += f"• {отображение}\n"
    
    await update.message.reply_text(текст)

async def команда_статус(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/status - статус"""
    чат = update.effective_chat
    
    if чат.type == ChatType.PRIVATE:
        await update.message.reply_text("В группе")
        return
    
    настройки = база.получить_настройки(chat.id)
    
    текст = f"""🛡️ Статус:

📊 Лимиты:
• Текст: {настройки['текст_лимит']}/{настройки['окно_времени']}сек
• Медиа: {настройки['медиа_лимит']}/{настройки['окно_времени']}сек
• Рейд: {настройки['порог_рейда']}/сек

👥 Защита:
• Исключения: {len(база.получить_исключения(chat.id))}
• Админы бота: {len(база.получить_админов(chat.id))}
• Владелец: {'✅' if база.получить_владельца(chat.id) else '❌'}

📈 Активность: {база.получить_активность(chat.id, 60):.1f}/сек
"""
    
    await update.message.reply_text(текст)

async def команда_статистика(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/stats - статистика"""
    чат = update.effective_chat
    
    if чат.type == ChatType.PRIVATE:
        await update.message.reply_text("В группе")
        return
    
    настройки = база.получить_настройки(chat.id)
    активность = база.получить_активность(chat.id, 300)
    
    текст = f"""📊 Статистика:

📈 Активность (5 мин): {активность:.1f} сообщ/сек
👥 Пользователи: {len(база.получить_исключения(chat.id))} исключений
⚙️ Настройки: {настройки['текст_лимит']} текст, {настройки['медиа_лимит']} медиа
"""
    
    await update.message.reply_text(текст)

async def команда_логи(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/logs - логи"""
    чат = update.effective_chat
    пользователь = update.effective_user
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    логи = база.получить_логи(chat.id, 10)
    
    if not логи:
        await update.message.reply_text("Нет логов")
        return
    
    текст = "📝 Логи:\n\n"
    for запись in логи:
        время = datetime.fromtimestamp(запись['время']).strftime("%H:%M")
        текст += f"• {время} {запись['действие']}"
        if запись['цель_id']:
            текст += f" (ID {запись['цель_id']})"
        текст += "\n"
    
    await update.message.reply_text(текст)

async def команда_блокировка(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/lock - блокировка"""
    чат = update.effective_chat
    пользователь = update.effective_user
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    try:
        await контекст.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text("🔒 Чат заблокирован")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def команда_разблокировка(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/unlock - разблокировка"""
    чат = update.effective_chat
    пользователь = update.effective_user
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    try:
        await контекст.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True)
        )
        await update.message.reply_text("🔓 Чат разблокирован")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def команда_медленный(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/slow - медленный режим"""
    чат = update.effective_chat
    пользователь = update.effective_user
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    задержка = 15
    if контекст.args:
        try:
            задержка = int(контекст.args[0])
            if задержка < 0 or задержка > 21600:
                задержка = 15
        except:
            pass
    
    try:
        await контекст.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True),
            slow_mode_delay=задержка
        )
        await update.message.reply_text(f"🐢 Медленный режим: {задержка} сек")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def команда_нормальный(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    """/normal - выключить медленный режим"""
    чат = update.effective_chat
    пользователь = update.effective_user
    
    if not база.является_админом(chat.id, пользователь.id):
        await update.message.reply_text("Нужны права")
        return
    
    try:
        await контекст.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True),
            slow_mode_delay=0
        )
        await update.message.reply_text("🚀 Медленный режим выключен")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# ============ КНОПКИ ============

async def обработчик_кнопок(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    запрос = update.callback_query
    await запрос.answer()
    
    данные = запрос.data
    chat_id = запрос.message.chat.id
    user_id = запрос.from_user.id
    
    if not база.является_админом(chat_id, user_id):
        await запрос.edit_message_text("Нужны права")
        return
    
    настройки = база.получить_настройки(chat_id)
    
    if данные == "меню_флуд":
        клавиатура = [
            [InlineKeyboardButton(f"Текст: {настройки['текст_лимит']}", callback_data="уст_текст")],
            [InlineKeyboardButton(f"Медиа: {настройки['медиа_лимит']}", callback_data="уст_медиа")],
            [InlineKeyboardButton(f"Окно: {настройки['окно_времени']} сек", callback_data="уст_окно")],
            [InlineKeyboardButton(f"Строгий: {'✅' if настройки['строгий_режим'] else '❌'}", callback_data="тог_строгий")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="назад")]
        ]
        await запрос.edit_message_text("📊 Анти-флуд:", reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные == "меню_рейд":
        клавиатура = [
            [InlineKeyboardButton(f"Порог: {настройки['порог_рейда']}/сек", callback_data="уст_порог")],
            [InlineKeyboardButton(f"Окно: {настройки['окно_рейда']} сек", callback_data="уст_окно_рейд")],
            [InlineKeyboardButton(f"Блокировка: {настройки['блокировка_время']} м", callback_data="уст_блок")],
            [InlineKeyboardButton(f"Auto: {'✅' if настройки['авто_блокировка'] else '❌'}", callback_data="тог_авто")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="назад")]
        ]
        await запрос.edit_message_text("🛡️ Анти-рейд:", reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные == "меню_настройки":
        клавиатура = [
            [InlineKeyboardButton(f"Бан: {настройки['бан_часы']} ч", callback_data="уст_бан")],
            [InlineKeyboardButton(f"Мут: {настройки['мут_минуты']} м", callback_data="уст_мут")],
            [InlineKeyboardButton(f"Варны: {настройки['варны_до_бана']}", callback_data="уст_варны")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="назад")]
        ]
        await запрос.edit_message_text("⚙️ Наказания:", reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные == "меню_исключения":
        count = len(база.получить_исключения(chat_id))
        клавиатура = [
            [InlineKeyboardButton("➕ Добавить", callback_data="доб_искл")],
            [InlineKeyboardButton("➖ Удалить", callback_data="уд_искл")],
            [InlineKeyboardButton(f"📋 Список ({count})", callback_data="список_искл")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="назад")]
        ]
        await запрос.edit_message_text("👥 Исключения:", reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные == "меню_админы":
        count = len(база.получить_админов(chat_id))
        клавиатура = [
            [InlineKeyboardButton("➕ Добавить", callback_data="доб_адм")],
            [InlineKeyboardButton("➖ Удалить", callback_data="уд_адм")],
            [InlineKeyboardButton(f"📋 Список ({count})", callback_data="список_адм")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="назад")]
        ]
        await запрос.edit_message_text("👑 Админы:", reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные == "меню_статистика":
        активность = база.получить_активность(chat_id, 60)
        текст = f"""📊 Статистика:

📈 Активность: {активность:.1f} сообщ/сек
👥 Исключения: {len(база.получить_исключения(chat_id))}
👑 Админы: {len(база.получить_админов(chat_id))}
"""
        клавиатура = [[InlineKeyboardButton("⬅️ Назад", callback_data="назад")]]
        await запрос.edit_message_text(текст, reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные == "назад":
        клавиатура = [
            [InlineKeyboardButton("📊 Анти-флуд", callback_data="меню_флуд")],
            [InlineKeyboardButton("🛡️ Анти-рейд", callback_data="меню_рейд")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="меню_настройки")],
            [InlineKeyboardButton("👥 Исключения", callback_data="меню_исключения")],
            [InlineKeyboardButton("👑 Админы", callback_data="меню_админы")],
            [InlineKeyboardButton("📊 Статистика", callback_data="меню_статистика")]
        ]
        await запрос.edit_message_text("⚙️ Панель:", reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные.startswith("тог_"):
        if данные == "тог_строгий":
            настройки["строгий_режим"] = not настройки["строгий_режим"]
        elif данные == "тог_авто":
            настройки["авто_блокировка"] = not настройки["авто_блокировка"]
        
        база.сохранить_настройки(chat_id, настройки)
        await обработчик_кнопок(update, контекст)
    
    elif данные.startswith("уст_"):
        параметры = {
            "уст_текст": ("текст_лимит", "Введите лимит текста (1-20):"),
            "уст_медиа": ("медиа_лимит", "Введите лимит медиа (1-20):"),
            "уст_окно": ("окно_времени", "Введите окно (1-60 сек):"),
            "уст_порог": ("порог_рейда", "Введите порог рейда (1-50):"),
            "уст_окно_рейд": ("окно_рейда", "Введите окно рейда (1-10 сек):"),
            "уст_блок": ("блокировка_время", "Введите блокировку (1-1440 мин):"),
            "уст_бан": ("бан_часы", "Введите часы бана (0-744):"),
            "уст_мут": ("мут_минуты", "Введите минуты мута (1-10080):"),
            "уст_варны": ("варны_до_бана", "Введите варны до бана (1-10):"),
        }
        
        if данные in параметры:
            параметр, вопрос = параметры[данные]
            контекст.user_data["параметр"] = параметр
            контекст.user_data["чат"] = chat_id
            await запрос.edit_message_text(f"{question}\n\nОтправьте число в чат.")
    
    elif данные == "список_искл":
        исключения = база.получить_исключения(chat_id)
        if исключения:
            текст = "👥 Исключения:\n\n"
            for юзер_id, юзернейм in исключения:
                отображение = f"@{юзернейм}" if юзернейм else f"ID {юзер_id}"
                текст += f"• {отображение}\n"
        else:
            текст = "Нет исключений"
        клавиатура = [[InlineKeyboardButton("⬅️ Назад", callback_data="меню_исключения")]]
        await запрос.edit_message_text(текст, reply_markup=InlineKeyboardMarkup(клавиатура))
    
    elif данные == "список_адм":
        админы = база.получить_админов(chat_id)
        владелец = база.получить_владельца(chat_id)
        if админы:
            текст = "👑 Админы:\n\n"
            for юзер_id, юзернейм in админы:
                if юзер_id == владелец:
                    отображение = f"@{юзернейм}" if юзернейм else f"ID {юзер_id}"
                    текст += f"• {отображение} 👑\n"
                else:
                    отображение = f"@{юзернейм}" if юзернейм else f"ID {юзер_id}"
                    текст += f"• {отображение}\n"
        else:
            текст = "Нет админов"
        клавиатура = [[InlineKeyboardButton("⬅️ Назад", callback_data="меню_админы")]]
        await запрос.edit_message_text(текст, reply_markup=InlineKeyboardMarkup(клавиатура))

async def обработчик_ввода(update: Update, контекст: ContextTypes.DEFAULT_TYPE):
    if "параметр" not in контекст.user_data:
        return
    
    параметр = контекст.user_data["параметр"]
    chat_id = контекст.user_data.get("чат")
    
    if not chat_id or chat_id != update.effective_chat.id:
        return
    
    if not база.является_админом(chat_id, update.effective_user.id):
        await update.message.reply_text("Нужны права")
        return
    
    try:
        значение = int(update.message.text)
        
        # Валидация
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
        
        if параметр in limits:
            мин, макс = limits[параметр]
            if значение < мин or значение > макс:
                await update.message.reply_text(f"От {мин} до {макс}")
                return
        
        настройки = база.получить_настройки(chat_id)
        настройки[параметр] = значение
        база.сохранить_настройки(chat_id, настройки)
        
        await update.message.reply_text(f"✅ Установлено: {значение}")
        
        del контекст.user_data["параметр"]
        del контекст.user_data["чат"]
        
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
            
            stats = база.получить_статистику_бота()
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
                    }}
                    .container {{
                        max-width: 800px;
                        margin: 0 auto;
                    }}
                    header {{
                        text-align: center;
                        margin-bottom: 40px;
                        border-bottom: 1px solid #333;
                        padding-bottom: 20px;
                    }}
                    h1 {{
                        font-size: 2.5em;
                        margin: 0;
                    }}
                    .status {{
                        display: inline-block;
                        padding: 5px 15px;
                        background: #0a0;
                        border-radius: 15px;
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
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <header>
                        <h1>ANTI-RAID BOT</h1>
                        <div class="status">● АКТИВЕН</div>
                        <p>Защита Telegram чатов</p>
                    </header>
                    
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-number">{stats['чаты']}</div>
                            <div>Чатов</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{stats['исключения']}</div>
                            <div>Исключений</div>
                        </div>
                        <div class="stat">
                            <div class="stat-number">{stats['действия']}</div>
                            <div>Действий</div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>ФУНКЦИИ</h2>
                        <div class="features">
                            <div class="feature">
                                <strong>Анти-флуд</strong>
                                <p>Контроль скорости сообщений</p>
                            </div>
                            <div class="feature">
                                <strong>Анти-рейд</strong>
                                <p>Обнаружение массовых атак</p>
                            </div>
                            <div class="feature">
                                <strong>Исключения</strong>
                                <p>Белый список пользователей</p>
                            </div>
                            <div class="feature">
                                <strong>Гибкие настройки</strong>
                                <p>Индивидуальные параметры</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>КОМАНДЫ</h2>
                        <div style="background: #222; padding: 20px; border-radius: 8px;">
                            <p><strong>/setup</strong> - Настройка бота</p>
                            <p><strong>!адм</strong> - Добавить админа (ответ на сообщение)</p>
                            <p><strong>!искл</strong> - Добавить исключение (ответ на сообщение)</p>
                            <p><strong>/stats</strong> - Статистика чата</p>
                            <p><strong>/lock</strong> - Блокировка чата</p>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>СОГЛАШЕНИЕ</h2>
                        <div style="color: #ccc; line-height: 1.6;">
                            <p>Бот предназначен для защиты чатов от нежелательной активности.</p>
                            <p>Мы храним минимально необходимые данные для работы.</p>
                            <p>Не передаём данные третьим лицам.</p>
                        </div>
                    </div>
                    
                    <footer>
                        <p>Anti-Raid Bot System</p>
                        <p>Время работы: {uptime.days} дней</p>
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
            self.wfile.write(b"404")
    
    def log_message(self, format, *args):
        pass

def запустить_веб(port=8080):
    server = HTTPServer(('0.0.0.0', port), WebHandler)
    print(f"🌐 Веб-сервер: http://localhost:{port}")
    server.serve_forever()

# ============ ЗАПУСК ============

async def main():
    # Веб-сервер
    веб_поток = threading.Thread(target=запустить_веб, args=(WEB_PORT,), daemon=True)
    веб_поток.start()
    
    # Бот
    приложение = Application.builder().token(TOKEN).build()
    
    # Команды
    команды = [
        ("start", команда_старт),
        ("setup", команда_настройка),
        ("settings", команда_настройки),
        ("status", команда_статус),
        ("lock", команда_блокировка),
        ("unlock", команда_разблокировка),
        ("slow", команда_медленный),
        ("normal", команда_нормальный),
        ("админы", команда_админы),
        ("исключения", команда_исключения),
        ("stats", команда_статистика),
        ("logs", команда_логи),
        ("help", команда_старт),
    ]
    
    for команда, обработчик in команды:
        приложение.add_handler(CommandHandler(команда, обработчик))
    
    # Команды через !
    команды_воскл = [
        ("адм", команда_адм),
        ("снять", команда_снять),
        ("искл", команда_искл),
        ("нискл", команда_нискл),
        ("варн", команда_варн),
        ("варны", команда_варны),
        ("снятьварны", команда_снятьварны),
    ]
    
    for команда, обработчик in команды_воскл:
        приложение.add_handler(MessageHandler(
            filters.Regex(f'^!{команда}') & ~filters.COMMAND,
            обработчик
        ))
    
    # Кнопки
    приложение.add_handler(CallbackQueryHandler(обработчик_кнопок))
    
    # Ввод параметров
    приложение.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        обработчик_ввода
    ))
    
    # Обработчик сообщений
    приложение.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        обработчик_сообщений
    ))
    
    print("🤖 Бот запущен")
    print("✅ Все команды работают")
    
    await приложение.initialize()
    await приложение.start()
    await приложение.updater.start_polling()
    
    # Автосохранение
    async def автосохранение():
        while True:
            await asyncio.sleep(300)
            база.conn.commit()
    
    asyncio.create_task(автосохранение())
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Создать файлы
    if not Path("requirements.txt").exists():
        with open("requirements.txt", "w") as f:
            f.write("python-telegram-bot==20.7\n")
    
    if not Path("Procfile").exists():
        with open("Procfile", "w") as f:
            f.write("web: python bot.py\n")
    
    # Запустить
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Остановка")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
