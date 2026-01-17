"""
Упрощенный Telegram-бот для анонимных вопросов
Использует long polling, Flask только для веб-сервера
"""

import os
import json
import time
import logging
import threading
from flask import Flask, jsonify
import requests

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8077751788:AAEFpJ0hnSGhA7UzhIZlYn-NVkj_kKG_x5Y')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'anoncoo1_bot')
PORT = int(os.getenv('PORT', 10000))

class SimpleBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f'https://api.telegram.org/bot{token}'
        self.offset = 0
        self.active_sessions = {}  # {user_id: target_id}
        self.reply_sessions = {}   # {user_id: original_sender_id}
        self.banned = {}           # {target_id: [banned_user_ids]}
        
        # Загружаем данные
        self.load_data()
    
    def load_data(self):
        """Загружаем данные из файлов"""
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)
                self.banned = data.get('banned', {})
                logger.info("Данные загружены")
        except:
            self.banned = {}
    
    def save_data(self):
        """Сохраняем данные в файл"""
        try:
            data = {'banned': self.banned}
            with open('data.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
    
    def send_message(self, chat_id, text, reply_markup=None):
        """Упрощенная отправка сообщения"""
        try:
            url = f'{self.base_url}/sendMessage'
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            
            if reply_markup:
                payload['reply_markup'] = json.dumps(reply_markup)
            
            response = requests.post(url, json=payload, timeout=5)
            result = response.json()
            
            if not result.get('ok'):
                logger.error(f"Ошибка Telegram API: {result}")
            
            return result.get('ok', False)
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            return False
    
    def get_updates(self):
        """Получаем обновления"""
        try:
            url = f'{self.base_url}/getUpdates'
            params = {
                'offset': self.offset,
                'timeout': 20,
                'limit': 100
            }
            
            response = requests.get(url, params=params, timeout=25)
            data = response.json()
            
            if data.get('ok') and data.get('result'):
                updates = data['result']
                if updates:
                    self.offset = updates[-1]['update_id'] + 1
                return updates
            return []
        except Exception as e:
            logger.error(f"Ошибка получения обновлений: {e}")
            return []
    
    def is_banned(self, sender_id, target_id):
        """Проверяем бан"""
        target_str = str(target_id)
        sender_str = str(sender_id)
        
        if target_str in self.banned:
            return sender_str in self.banned[target_str]
        return False
    
    def ban_user(self, target_id, sender_id):
        """Баним пользователя"""
        target_str = str(target_id)
        sender_str = str(sender_id)
        
        if target_str not in self.banned:
            self.banned[target_str] = []
        
        if sender_str not in self.banned[target_str]:
            self.banned[target_str].append(sender_str)
            self.save_data()
            return True
        return False
    
    def handle_start(self, chat_id, user_id, username, name, args=None):
        """Обработка /start"""
        if args:
            # Переход по ссылке
            try:
                target_id = int(args)
                
                if self.is_banned(user_id, target_id):
                    self.send_message(chat_id, "🚫 Вы заблокированы этим пользователем")
                    return
                
                self.active_sessions[user_id] = target_id
                
                message = (
                    "🎭 <b>Режим анонимности активирован</b>\n\n"
                    "Теперь вы можете отправлять анонимные сообщения.\n"
                    "Просто напишите что-нибудь, фото, видео или голосовое."
                )
                self.send_message(chat_id, message)
                
            except:
                self.send_message(chat_id, "❌ Неверная ссылка")
        else:
            # Генерация ссылки
            link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
            message = (
                f"👋 <b>Ваша ссылка для анонимных вопросов:</b>\n\n"
                f"<code>{link}</code>\n\n"
                f"Разместите её в профиле!"
            )
            self.send_message(chat_id, message)
    
    def handle_text(self, chat_id, user_id, username, name, text):
        """Обработка текста"""
        # Проверяем режим ответа
        if user_id in self.reply_sessions:
            target_id = self.reply_sessions[user_id]
            
            reply_msg = (
                f"💬 <b>Ответ на ваше сообщение:</b>\n\n"
                f"{text}\n\n"
                f"От: {name}"
            )
            if username:
                reply_msg += f" (@{username})"
            
            self.send_message(target_id, reply_msg)
            self.send_message(chat_id, "✅ Ответ отправлен!")
            del self.reply_sessions[user_id]
            return
        
        # Проверяем режим анонимности
        if user_id in self.active_sessions:
            target_id = self.active_sessions[user_id]
            
            if self.is_banned(user_id, target_id):
                self.send_message(chat_id, "🚫 Вы заблокированы")
                del self.active_sessions[user_id]
                return
            
            # Сообщение получателю
            sender_info = f"👤 {name}"
            if username:
                sender_info += f" (@{username})"
            sender_info += f"\n🆔 ID: {user_id}"
            
            message = (
                f"📩 <b>Анонимное сообщение:</b>\n\n"
                f"{text}\n\n"
                f"{sender_info}"
            )
            
            # Кнопки
            keyboard = {
                'inline_keyboard': [[
                    {
                        'text': '💬 Ответить',
                        'callback_data': f'reply_{user_id}'
                    },
                    {
                        'text': '🚫 Забанить',
                        'callback_data': f'ban_{user_id}'
                    }
                ]]
            }
            
            if self.send_message(target_id, message, keyboard):
                self.send_message(chat_id, "✅ Сообщение отправлено!")
            else:
                self.send_message(chat_id, "❌ Ошибка отправки")
            
            del self.active_sessions[user_id]
        else:
            # Простое сообщение
            help_text = (
                "ℹ️ <b>Использование бота:</b>\n\n"
                "1. /start - получить свою ссылку\n"
                "2. Разместите ссылку в профиле\n"
                "3. Другие пишут вам анонимно\n\n"
                "Чтобы написать анонимно, перейдите по чужой ссылке."
            )
            self.send_message(chat_id, help_text)
    
    def handle_media(self, chat_id, user_id, username, name, media_type, file_id, caption=None):
        """Обработка медиа"""
        if user_id not in self.active_sessions:
            self.send_message(chat_id, "ℹ️ Сначала перейдите по чьей-либо ссылке (/start с ID)")
            return
        
        target_id = self.active_sessions[user_id]
        
        if self.is_banned(user_id, target_id):
            self.send_message(chat_id, "🚫 Вы заблокированы")
            del self.active_sessions[user_id]
            return
        
        # Типы медиа
        media_methods = {
            'photo': 'sendPhoto',
            'video': 'sendVideo',
            'voice': 'sendVoice',
            'document': 'sendDocument'
        }
        
        if media_type not in media_methods:
            self.send_message(chat_id, "❌ Неподдерживаемый тип файла")
            return
        
        # Отправляем отправителю подтверждение
        self.send_message(chat_id, f"✅ {media_type.capitalize()} отправлено!")
        
        # Подготовка сообщения получателю
        sender_info = f"👤 {name}"
        if username:
            sender_info += f" (@{username})"
        sender_info += f"\n🆔 ID: {user_id}"
        
        media_caption = ""
        if caption:
            media_caption += f"{caption}\n\n"
        media_caption += f"📎 <b>{media_type.capitalize()} от анонима:</b>\n{sender_info}"
        
        # Отправляем медиа получателю
        try:
            url = f'{self.base_url}/{media_methods[media_type]}'
            payload = {
                'chat_id': target_id,
                'caption': media_caption,
                'parse_mode': 'HTML'
            }
            
            # Для фото нужно передать file_id
            if media_type == 'photo':
                payload['photo'] = file_id
            elif media_type == 'video':
                payload['video'] = file_id
            elif media_type == 'voice':
                payload['voice'] = file_id
            elif media_type == 'document':
                payload['document'] = file_id
            
            # Добавляем кнопки
            keyboard = {
                'inline_keyboard': [[
                    {
                        'text': '💬 Ответить',
                        'callback_data': f'reply_{user_id}'
                    },
                    {
                        'text': '🚫 Забанить',
                        'callback_data': f'ban_{user_id}'
                    }
                ]]
            }
            payload['reply_markup'] = json.dumps(keyboard)
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
        except Exception as e:
            logger.error(f"Ошибка отправки медиа: {e}")
        
        del self.active_sessions[user_id]
    
    def handle_callback(self, callback_id, chat_id, user_id, data):
        """Обработка нажатия кнопки"""
        try:
            parts = data.split('_')
            action = parts[0]
            target_user_id = int(parts[1]) if len(parts) > 1 else None
            
            if action == 'reply' and target_user_id:
                self.reply_sessions[user_id] = target_user_id
                self.send_message(chat_id, "💬 <b>Режим ответа активирован</b>\n\nОтправьте сообщение, и оно будет переслано отправителю.")
                
                # Ответ на callback
                requests.post(
                    f'{self.base_url}/answerCallbackQuery',
                    json={'callback_query_id': callback_id}
                )
            
            elif action == 'ban' and target_user_id:
                if self.ban_user(user_id, target_user_id):
                    self.send_message(chat_id, f"🚫 Пользователь ID:{target_user_id} заблокирован")
                    
                    # Уведомляем забаненного
                    self.send_message(
                        target_user_id,
                        "⚠️ Вы были заблокированы пользователем и больше не можете писать ему."
                    )
                else:
                    self.send_message(chat_id, "❌ Ошибка блокировки")
                
                # Ответ на callback
                requests.post(
                    f'{self.base_url}/answerCallbackQuery',
                    json={'callback_query_id': callback_id}
                )
        
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
    
    def process_update(self, update):
        """Обработка одного обновления"""
        try:
            # Callback query
            if 'callback_query' in update:
                cb = update['callback_query']
                self.handle_callback(
                    cb['id'],
                    cb['message']['chat']['id'],
                    cb['from']['id'],
                    cb.get('data', '')
                )
                return
            
            # Message
            if 'message' not in update:
                return
            
            msg = update['message']
            chat_id = msg['chat']['id']
            from_user = msg.get('from', {})
            user_id = from_user.get('id')
            username = from_user.get('username', '')
            
            # Имя пользователя
            first = from_user.get('first_name', '')
            last = from_user.get('last_name', '')
            name = f"{first} {last}".strip()
            if not name:
                name = username if username else f"User{user_id}"
            
            # Команда /start
            if 'text' in msg and msg['text'].startswith('/start'):
                args = msg['text'].split(' ')
                if len(args) > 1:
                    self.handle_start(chat_id, user_id, username, name, args[1])
                else:
                    self.handle_start(chat_id, user_id, username, name)
            
            # Текст
            elif 'text' in msg:
                self.handle_text(chat_id, user_id, username, name, msg['text'])
            
            # Фото
            elif 'photo' in msg:
                # Берем самое большое фото (последнее в массиве)
                file_id = msg['photo'][-1]['file_id']
                caption = msg.get('caption', '')
                self.handle_media(chat_id, user_id, username, name, 'photo', file_id, caption)
            
            # Видео
            elif 'video' in msg:
                file_id = msg['video']['file_id']
                caption = msg.get('caption', '')
                self.handle_media(chat_id, user_id, username, name, 'video', file_id, caption)
            
            # Голосовое
            elif 'voice' in msg:
                file_id = msg['voice']['file_id']
                self.handle_media(chat_id, user_id, username, name, 'voice', file_id)
            
            # Документ
            elif 'document' in msg:
                file_id = msg['document']['file_id']
                caption = msg.get('caption', '')
                self.handle_media(chat_id, user_id, username, name, 'document', file_id, caption)
            
            # Другое
            else:
                self.send_message(chat_id, "❌ Поддерживаются только текст, фото, видео, голосовые и документы")
        
        except Exception as e:
            logger.error(f"Ошибка обработки: {e}")
    
    def run_polling(self):
        """Основной цикл"""
        logger.info("Бот запущен...")
        
        while True:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.process_update(update)
                
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                logger.info("Остановка бота...")
                break
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}")
                time.sleep(5)

# Создаем бота
bot = SimpleBot(TOKEN)

# Flask app (только для веб-сервера)
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "bot is running", "users": len(bot.active_sessions)})

@app.route('/health')
def health():
    return 'OK'

def start_bot():
    """Запуск бота в отдельном потоке"""
    bot_thread = threading.Thread(target=bot.run_polling, daemon=True)
    bot_thread.start()
    logger.info("Бот запущен в отдельном потоке")

if __name__ == '__main__':
    # Проверка токена
    if TOKEN == 'ВАШ_ТОКЕН_БОТА':
        logger.error("Установите TELEGRAM_BOT_TOKEN!")
        exit(1)
    
    # Запускаем бота
    start_bot()
    
    # Запускаем Flask
    app.run(host='0.0.0.0', port=PORT, debug=False)
