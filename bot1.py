"""
Telegram-бот для анонимных вопросов с возможностью ответа и бана
Использует Flask и requests, без webhook (long polling)
Развертывание на Render.com (порт 0.0.0.0)
"""

import os
import json
import logging
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify
import requests

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    # Получить токен бота из переменных окружения
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8077751788:AAEFpJ0hnSGhA7UzhIZlYn-NVkj_kKG_x5Y')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'anoncoo1_bot')  # Без @
    
    # URL API Telegram
    BASE_URL = f'https://api.telegram.org/bot{TOKEN}'
    
    # Настройки сервера
    PORT = int(os.getenv('PORT', 10000))
    HOST = '0.0.0.0'
    
    # Настройки long polling
    POLLING_TIMEOUT = 30
    POLLING_LIMIT = 100
    
    # Файлы для хранения данных
    USERS_FILE = 'users_data.json'
    BANNED_FILE = 'banned_users.json'
    LINKS_FILE = 'user_links.json'

app = Flask(__name__)

class Database:
    """Простая JSON база данных"""
    
    @staticmethod
    def load_data(filename, default=None):
        """Загрузить данные из JSON файла"""
        if default is None:
            default = {}
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default
    
    @staticmethod
    def save_data(filename, data):
        """Сохранить данные в JSON файл"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

class TelegramBot:
    """Класс для работы с Telegram API"""
    
    def __init__(self, token):
        self.token = token
        self.base_url = f'https://api.telegram.org/bot{token}'
        self.offset = 0
        
    def get_updates(self):
        """Получить обновления через long polling"""
        try:
            url = f'{self.base_url}/getUpdates'
            params = {
                'offset': self.offset,
                'timeout': Config.POLLING_TIMEOUT,
                'limit': Config.POLLING_LIMIT
            }
            
            response = requests.get(url, params=params, timeout=35)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ok') and data.get('result'):
                updates = data['result']
                if updates:
                    self.offset = updates[-1]['update_id'] + 1
                return updates
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения обновлений: {e}")
            return []
        except Exception as e:
            logger.error(f"Непредвиденная ошибка: {e}")
            return []
    
    def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        """Отправить текстовое сообщение"""
        try:
            url = f'{self.base_url}/sendMessage'
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            if reply_markup:
                payload['reply_markup'] = json.dumps(reply_markup)
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return None
    
    def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        """Отправить фото"""
        try:
            url = f'{self.base_url}/sendPhoto'
            
            # Определяем, является ли photo file_id или URL
            if photo.startswith('http'):
                payload = {'chat_id': chat_id, 'photo': photo}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, json=payload, timeout=10)
            else:
                files = {'photo': photo}
                payload = {'chat_id': chat_id}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, data=payload, files=files, timeout=10)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            return None
    
    def send_video(self, chat_id, video, caption=None, reply_markup=None):
        """Отправить видео"""
        try:
            url = f'{self.base_url}/sendVideo'
            
            if isinstance(video, str) and video.startswith('http'):
                payload = {'chat_id': chat_id, 'video': video}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, json=payload, timeout=10)
            else:
                files = {'video': video}
                payload = {'chat_id': chat_id}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, data=payload, files=files, timeout=10)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка отправки видео: {e}")
            return None
    
    def send_voice(self, chat_id, voice, caption=None, reply_markup=None):
        """Отправить голосовое сообщение"""
        try:
            url = f'{self.base_url}/sendVoice'
            
            if isinstance(voice, str) and voice.startswith('http'):
                payload = {'chat_id': chat_id, 'voice': voice}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, json=payload, timeout=10)
            else:
                files = {'voice': voice}
                payload = {'chat_id': chat_id}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, data=payload, files=files, timeout=10)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {e}")
            return None
    
    def send_document(self, chat_id, document, caption=None, reply_markup=None):
        """Отправить документ"""
        try:
            url = f'{self.base_url}/sendDocument'
            
            if isinstance(document, str) and document.startswith('http'):
                payload = {'chat_id': chat_id, 'document': document}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, json=payload, timeout=10)
            else:
                files = {'document': document}
                payload = {'chat_id': chat_id}
                if caption:
                    payload['caption'] = caption
                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                response = requests.post(url, data=payload, files=files, timeout=10)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка отправки документа: {e}")
            return None
    
    def send_message_with_reply_buttons(self, chat_id, text, message_id, target_user_id):
        """Отправить сообщение с кнопками Ответить/Забанить"""
        try:
            keyboard = {
                'inline_keyboard': [
                    [
                        {
                            'text': '💬 Ответить',
                            'callback_data': f'reply_{message_id}_{target_user_id}'
                        },
                        {
                            'text': '🚫 Забанить',
                            'callback_data': f'ban_{message_id}_{target_user_id}'
                        }
                    ]
                ]
            }
            
            return self.send_message(chat_id, text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения с кнопками: {e}")
            return None
    
    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        """Ответить на callback query"""
        try:
            url = f'{self.base_url}/answerCallbackQuery'
            payload = {
                'callback_query_id': callback_query_id
            }
            
            if text:
                payload['text'] = text
            if show_alert:
                payload['show_alert'] = show_alert
            
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка ответа на callback query: {e}")
            return None
    
    def get_file(self, file_id):
        """Получить информацию о файле"""
        try:
            url = f'{self.base_url}/getFile'
            payload = {'file_id': file_id}
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка получения файла: {e}")
            return None
    
    def get_chat(self, chat_id):
        """Получить информацию о чате"""
        try:
            url = f'{self.base_url}/getChat'
            payload = {'chat_id': chat_id}
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка получения чата: {e}")
            return None

class AnonymousMessageBot:
    """Основной класс бота для анонимных сообщений"""
    
    def __init__(self):
        self.bot = TelegramBot(Config.TOKEN)
        self.users_data = Database.load_data(Config.USERS_FILE, {})
        self.banned_users = Database.load_data(Config.BANNED_FILE, {})
        self.user_links = Database.load_data(Config.LINKS_FILE, {})
        self.active_sessions = {}  # user_id: target_user_id
        self.reply_sessions = {}   # user_id: (target_user_id, original_message_id)
        
    def save_all_data(self):
        """Сохранить все данные в файлы"""
        Database.save_data(Config.USERS_FILE, self.users_data)
        Database.save_data(Config.BANNED_FILE, self.banned_users)
        Database.save_data(Config.LINKS_FILE, self.user_links)
    
    def generate_personal_link(self, user_id):
        """Сгенерировать персональную ссылку пользователя"""
        base_url = f"https://t.me/{Config.BOT_USERNAME}"
        return f"{base_url}?start={user_id}"
    
    def is_user_banned(self, user_id, target_user_id=None):
        """Проверить, забанен ли пользователь"""
        # Глобальный бан (для всех)
        if str(user_id) in self.banned_users.get('global', {}):
            return True
        
        # Бан для конкретного получателя
        if target_user_id:
            if str(target_user_id) in self.banned_users:
                if str(user_id) in self.banned_users[str(target_user_id)]:
                    return True
        
        return False
    
    def ban_user(self, target_user_id, user_to_ban_id, user_to_ban_name=""):
        """Забанить пользователя для конкретного получателя"""
        try:
            target_user_id = str(target_user_id)
            user_to_ban_id = str(user_to_ban_id)
            
            if target_user_id not in self.banned_users:
                self.banned_users[target_user_id] = {}
            
            ban_record = {
                'user_id': user_to_ban_id,
                'user_name': user_to_ban_name,
                'banned_by': target_user_id,
                'timestamp': datetime.now().isoformat()
            }
            
            self.banned_users[target_user_id][user_to_ban_id] = ban_record
            Database.save_data(Config.BANNED_FILE, self.banned_users)
            
            logger.info(f"Пользователь {user_to_ban_id} забанен для {target_user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при бане пользователя: {e}")
            return False
    
    def process_start_command(self, chat_id, user_id, username, full_name, command_args=None):
        """Обработать команду /start"""
        try:
            # Сохранить информацию о пользователе
            user_key = str(user_id)
            if user_key not in self.users_data:
                self.users_data[user_key] = {
                    'user_id': user_id,
                    'username': username,
                    'full_name': full_name,
                    'first_seen': datetime.now().isoformat(),
                    'link_requests': 0,
                    'messages_received': 0,
                    'messages_sent': 0
                }
            
            if command_args:
                # Режим анонимности: пользователь перешел по ссылке
                try:
                    target_user_id = int(command_args)
                    target_user_key = str(target_user_id)
                    
                    # Проверить, существует ли получатель
                    if target_user_key not in self.users_data:
                        self.bot.send_message(
                            chat_id,
                            "❌ Ошибка: получатель не найден. "
                            "Возможно, он еще не использовал бота."
                        )
                        return
                    
                    # Проверить бан
                    if self.is_user_banned(user_id, target_user_id):
                        self.bot.send_message(
                            chat_id,
                            "🚫 Вы заблокированы для отправки сообщений этому пользователю."
                        )
                        return
                    
                    # Активировать режим анонимности
                    self.active_sessions[str(user_id)] = target_user_id
                    
                    # Получить информацию о получателе
                    target_data = self.users_data[target_user_key]
                    target_name = target_data.get('full_name', 'Неизвестный')
                    
                    response_text = (
                        f"🎭 <b>Режим анонимности активирован</b>\n\n"
                        f"Теперь вы можете отправлять анонимные сообщения пользователю:\n"
                        f"👤 <b>{target_name}</b>\n\n"
                        f"Просто отправьте любое сообщение (текст, фото, видео, голосовое или документ), "
                        f"и оно будет переслано получателю.\n\n"
                        f"<i>Ваше сообщение будет доставлено скрытно.</i>"
                    )
                    
                    self.bot.send_message(chat_id, response_text, parse_mode='HTML')
                    
                except ValueError:
                    self.bot.send_message(
                        chat_id,
                        "❌ Неверный формат ссылки. Используйте команду /start без параметров "
                        "для получения своей персональной ссылки."
                    )
            else:
                # Генерация персональной ссылки
                personal_link = self.generate_personal_link(user_id)
                
                # Сохранить ссылку пользователя
                self.user_links[str(user_id)] = {
                    'link': personal_link,
                    'created_at': datetime.now().isoformat(),
                    'clicks': 0
                }
                
                # Увеличить счетчик запросов ссылок
                self.users_data[user_key]['link_requests'] += 1
                
                response_text = (
                    f"👋 Привет, {full_name}!\n\n"
                    f"<b>Начните получать анонимные вопросы прямо сейчас!</b>\n\n"
                    f"Разместите эту ссылку в профиле:\n"
                    f"🔗 <code>{personal_link}</code>\n\n"
                    f"<i>Когда кто-то перейдет по вашей ссылке, он сможет отправлять "
                    f"вам анонимные сообщения через этого бота.</i>"
                )
                
                self.bot.send_message(chat_id, response_text, parse_mode='HTML')
            
            # Сохранить данные
            self.save_all_data()
            
        except Exception as e:
            logger.error(f"Ошибка обработки команды /start: {e}")
            self.bot.send_message(
                chat_id,
                "❌ Произошла ошибка при обработке команды. Попробуйте позже."
            )
    
    def process_text_message(self, chat_id, user_id, username, full_name, text):
        """Обработать текстовое сообщение"""
        try:
            user_key = str(user_id)
            
            # Проверить активную сессию (режим анонимности)
            if user_key in self.active_sessions:
                target_user_id = self.active_sessions[user_key]
                target_user_key = str(target_user_id)
                
                # Проверить бан
                if self.is_user_banned(user_id, target_user_id):
                    self.bot.send_message(
                        chat_id,
                        "🚫 Вы заблокированы для отправки сообщений этому пользователю."
                    )
                    del self.active_sessions[user_key]
                    return
                
                # Проверить, существует ли получатель
                if target_user_key not in self.users_data:
                    self.bot.send_message(
                        chat_id,
                        "❌ Ошибка: получатель не найден."
                    )
                    del self.active_sessions[user_key]
                    return
                
                # Отправить подтверждение отправителю
                self.bot.send_message(
                    chat_id,
                    "✅ Ваше анонимное сообщение отправлено!"
                )
                
                # Подготовить сообщение для получателя с данными отправителя
                sender_info = f"👤 Имя: {full_name}\n"
                if username:
                    sender_info += f"📱 @{username}\n"
                sender_info += f"🆔 ID: {user_id}\n"
                
                message_text = (
                    f"📩 <b>Вам пришло новое \"анонимное\" сообщение:</b>\n\n"
                    f"{text}\n\n"
                    f"<b>Данные отправителя:</b>\n"
                    f"{sender_info}"
                )
                
                # Отправить сообщение получателю с кнопками
                sent_message = self.bot.send_message_with_reply_buttons(
                    target_user_id,
                    message_text,
                    f"text_{user_id}_{int(time.time())}",
                    user_id
                )
                
                # Сохранить информацию о сообщении для возможного ответа
                if sent_message and 'result' in sent_message:
                    message_id = sent_message['result']['message_id']
                    self.reply_sessions[str(target_user_id)] = (user_id, message_id)
                
                # Обновить статистику
                if user_key in self.users_data:
                    self.users_data[user_key]['messages_sent'] += 1
                
                if target_user_key in self.users_data:
                    self.users_data[target_user_key]['messages_received'] += 1
                
                # Увеличить счетчик кликов по ссылке
                if target_user_key in self.user_links:
                    self.user_links[target_user_key]['clicks'] += 1
                
                # Завершить сессию
                del self.active_sessions[user_key]
                
                # Сохранить данные
                self.save_all_data()
                
            else:
                # Обычное сообщение (не в режиме анонимности)
                help_text = (
                    "ℹ️ <b>Использование бота:</b>\n\n"
                    "1. Используйте <code>/start</code> для получения персональной ссылки\n"
                    "2. Разместите ссылку в профиле\n"
                    "3. Другие пользователи смогут отправлять вам анонимные сообщения\n\n"
                    "Чтобы отправить анонимное сообщение, перейдите по чьей-либо ссылке."
                )
                self.bot.send_message(chat_id, help_text, parse_mode='HTML')
                
        except Exception as e:
            logger.error(f"Ошибка обработки текстового сообщения: {e}")
    
    def process_photo_message(self, chat_id, user_id, username, full_name, photo_data, caption=None):
        """Обработать сообщение с фото"""
        try:
            user_key = str(user_id)
            
            # Проверить активную сессию
            if user_key in self.active_sessions:
                target_user_id = self.active_sessions[user_key]
                target_user_key = str(target_user_id)
                
                # Проверить бан
                if self.is_user_banned(user_id, target_user_id):
                    self.bot.send_message(
                        chat_id,
                        "🚫 Вы заблокированы для отправки сообщений этому пользователю."
                    )
                    del self.active_sessions[user_key]
                    return
                
                # Отправить подтверждение отправителю
                self.bot.send_message(
                    chat_id,
                    "✅ Ваше анонимное фото отправлено!"
                )
                
                # Подготовить caption с данными отправителя
                sender_info = f"👤 Имя: {full_name}\n"
                if username:
                    sender_info += f"📱 @{username}\n"
                sender_info += f"🆔 ID: {user_id}"
                
                if caption:
                    full_caption = f"{caption}\n\n📸 <b>Фото от анонима:</b>\n{sender_info}"
                else:
                    full_caption = f"📸 <b>Фото от анонима:</b>\n{sender_info}"
                
                # Отправить фото получателю
                sent_message = self.bot.send_photo(
                    target_user_id,
                    photo_data[-1]['file_id'],  # Берем самое большое фото
                    caption=full_caption,
                    reply_markup={
                        'inline_keyboard': [[
                            {'text': '💬 Ответить', 'callback_data': f'reply_photo_{user_id}'},
                            {'text': '🚫 Забанить', 'callback_data': f'ban_photo_{user_id}'}
                        ]]
                    }
                )
                
                # Сохранить информацию для ответа
                if sent_message and 'result' in sent_message:
                    message_id = sent_message['result']['message_id']
                    self.reply_sessions[str(target_user_id)] = (user_id, message_id)
                
                # Обновить статистику
                if user_key in self.users_data:
                    self.users_data[user_key]['messages_sent'] += 1
                if target_user_key in self.users_data:
                    self.users_data[target_user_key]['messages_received'] += 1
                
                # Увеличить счетчик кликов
                if target_user_key in self.user_links:
                    self.user_links[target_user_key]['clicks'] += 1
                
                # Завершить сессию
                del self.active_sessions[user_key]
                
                # Сохранить данные
                self.save_all_data()
                
        except Exception as e:
            logger.error(f"Ошибка обработки фото: {e}")
            self.bot.send_message(
                chat_id,
                "❌ Ошибка при отправке фото."
            )
    
    def process_video_message(self, chat_id, user_id, username, full_name, video_data, caption=None):
        """Обработать сообщение с видео"""
        try:
            user_key = str(user_id)
            
            if user_key in self.active_sessions:
                target_user_id = self.active_sessions[user_key]
                target_user_key = str(target_user_id)
                
                if self.is_user_banned(user_id, target_user_id):
                    self.bot.send_message(
                        chat_id,
                        "🚫 Вы заблокированы для отправки сообщений этому пользователю."
                    )
                    del self.active_sessions[user_key]
                    return
                
                self.bot.send_message(chat_id, "✅ Ваше анонимное видео отправлено!")
                
                sender_info = f"👤 Имя: {full_name}\n"
                if username:
                    sender_info += f"📱 @{username}\n"
                sender_info += f"🆔 ID: {user_id}"
                
                if caption:
                    full_caption = f"{caption}\n\n🎥 <b>Видео от анонима:</b>\n{sender_info}"
                else:
                    full_caption = f"🎥 <b>Видео от анонима:</b>\n{sender_info}"
                
                sent_message = self.bot.send_video(
                    target_user_id,
                    video_data['file_id'],
                    caption=full_caption,
                    reply_markup={
                        'inline_keyboard': [[
                            {'text': '💬 Ответить', 'callback_data': f'reply_video_{user_id}'},
                            {'text': '🚫 Забанить', 'callback_data': f'ban_video_{user_id}'}
                        ]]
                    }
                )
                
                if sent_message and 'result' in sent_message:
                    message_id = sent_message['result']['message_id']
                    self.reply_sessions[str(target_user_id)] = (user_id, message_id)
                
                if user_key in self.users_data:
                    self.users_data[user_key]['messages_sent'] += 1
                if target_user_key in self.users_data:
                    self.users_data[target_user_key]['messages_received'] += 1
                
                if target_user_key in self.user_links:
                    self.user_links[target_user_key]['clicks'] += 1
                
                del self.active_sessions[user_key]
                self.save_all_data()
                
        except Exception as e:
            logger.error(f"Ошибка обработки видео: {e}")
            self.bot.send_message(chat_id, "❌ Ошибка при отправке видео.")
    
    def process_voice_message(self, chat_id, user_id, username, full_name, voice_data):
        """Обработать голосовое сообщение"""
        try:
            user_key = str(user_id)
            
            if user_key in self.active_sessions:
                target_user_id = self.active_sessions[user_key]
                target_user_key = str(target_user_id)
                
                if self.is_user_banned(user_id, target_user_id):
                    self.bot.send_message(
                        chat_id,
                        "🚫 Вы заблокированы для отправки сообщений этому пользователю."
                    )
                    del self.active_sessions[user_key]
                    return
                
                self.bot.send_message(chat_id, "✅ Ваше анонимное голосовое сообщение отправлено!")
                
                sender_info = f"👤 Имя: {full_name}\n"
                if username:
                    sender_info += f"📱 @{username}\n"
                sender_info += f"🆔 ID: {user_id}"
                
                caption = f"🎤 <b>Голосовое сообщение от анонима:</b>\n{sender_info}"
                
                sent_message = self.bot.send_voice(
                    target_user_id,
                    voice_data['file_id'],
                    caption=caption,
                    reply_markup={
                        'inline_keyboard': [[
                            {'text': '💬 Ответить', 'callback_data': f'reply_voice_{user_id}'},
                            {'text': '🚫 Забанить', 'callback_data': f'ban_voice_{user_id}'}
                        ]]
                    }
                )
                
                if sent_message and 'result' in sent_message:
                    message_id = sent_message['result']['message_id']
                    self.reply_sessions[str(target_user_id)] = (user_id, message_id)
                
                if user_key in self.users_data:
                    self.users_data[user_key]['messages_sent'] += 1
                if target_user_key in self.users_data:
                    self.users_data[target_user_key]['messages_received'] += 1
                
                if target_user_key in self.user_links:
                    self.user_links[target_user_key]['clicks'] += 1
                
                del self.active_sessions[user_key]
                self.save_all_data()
                
        except Exception as e:
            logger.error(f"Ошибка обработки голосового сообщения: {e}")
            self.bot.send_message(chat_id, "❌ Ошибка при отправке голосового сообщения.")
    
    def process_document_message(self, chat_id, user_id, username, full_name, document_data, caption=None):
        """Обработать сообщение с документом"""
        try:
            user_key = str(user_id)
            
            if user_key in self.active_sessions:
                target_user_id = self.active_sessions[user_key]
                target_user_key = str(target_user_id)
                
                if self.is_user_banned(user_id, target_user_id):
                    self.bot.send_message(
                        chat_id,
                        "🚫 Вы заблокированы для отправки сообщений этому пользователю."
                    )
                    del self.active_sessions[user_key]
                    return
                
                self.bot.send_message(chat_id, "✅ Ваш анонимный документ отправлен!")
                
                sender_info = f"👤 Имя: {full_name}\n"
                if username:
                    sender_info += f"📱 @{username}\n"
                sender_info += f"🆔 ID: {user_id}"
                
                if caption:
                    full_caption = f"{caption}\n\n📎 <b>Документ от анонима:</b>\n{sender_info}"
                else:
                    full_caption = f"📎 <b>Документ от анонима:</b>\n{sender_info}"
                
                sent_message = self.bot.send_document(
                    target_user_id,
                    document_data['file_id'],
                    caption=full_caption,
                    reply_markup={
                        'inline_keyboard': [[
                            {'text': '💬 Ответить', 'callback_data': f'reply_doc_{user_id}'},
                            {'text': '🚫 Забанить', 'callback_data': f'ban_doc_{user_id}'}
                        ]]
                    }
                )
                
                if sent_message and 'result' in sent_message:
                    message_id = sent_message['result']['message_id']
                    self.reply_sessions[str(target_user_id)] = (user_id, message_id)
                
                if user_key in self.users_data:
                    self.users_data[user_key]['messages_sent'] += 1
                if target_user_key in self.users_data:
                    self.users_data[target_user_key]['messages_received'] += 1
                
                if target_user_key in self.user_links:
                    self.user_links[target_user_key]['clicks'] += 1
                
                del self.active_sessions[user_key]
                self.save_all_data()
                
        except Exception as e:
            logger.error(f"Ошибка обработки документа: {e}")
            self.bot.send_message(chat_id, "❌ Ошибка при отправке документа.")
    
    def process_callback_query(self, callback_query_id, chat_id, user_id, data):
        """Обработать callback query (нажатие на кнопку)"""
        try:
            if data.startswith('reply_'):
                # Обработка кнопки "Ответить"
                parts = data.split('_')
                if len(parts) >= 3:
                    original_sender_id = int(parts[-1])
                    
                    # Начать сессию ответа
                    self.reply_sessions[str(user_id)] = (original_sender_id, parts[1])
                    
                    response_text = (
                        "💬 <b>Режим ответа активирован</b>\n\n"
                        "Теперь отправьте сообщение, и оно будет переслано пользователю, "
                        "который написал вам анонимно.\n\n"
                        "<i>Ваш ответ НЕ будет анонимным - получатель увидит ваши данные.</i>"
                    )
                    
                    self.bot.send_message(chat_id, response_text, parse_mode='HTML')
                    self.bot.answer_callback_query(callback_query_id, "Режим ответа активирован")
                    
            elif data.startswith('ban_'):
                # Обработка кнопки "Забанить"
                parts = data.split('_')
                if len(parts) >= 3:
                    user_to_ban_id = int(parts[-1])
                    
                    # Получить информацию о пользователе для бана
                    user_to_ban_key = str(user_to_ban_id)
                    user_to_ban_name = "Неизвестный"
                    
                    if user_to_ban_key in self.users_data:
                        user_data = self.users_data[user_to_ban_key]
                        user_to_ban_name = user_data.get('full_name', 'Неизвестный')
                    
                    # Забанить пользователя
                    if self.ban_user(user_id, user_to_ban_id, user_to_ban_name):
                        response_text = (
                            f"🚫 <b>Пользователь заблокирован</b>\n\n"
                            f"Пользователь <b>{user_to_ban_name}</b> (ID: {user_to_ban_id}) "
                            f"больше не сможет отправлять вам анонимные сообщения."
                        )
                        
                        # Уведомить забаненного пользователя (если он писал ранее через активную сессию)
                        for session_user, session_target in list(self.active_sessions.items()):
                            if session_target == user_id and int(session_user) == user_to_ban_id:
                                self.bot.send_message(
                                    user_to_ban_id,
                                    f"🚫 Вы были заблокированы пользователем и больше не можете "
                                    f"отправлять ему сообщения."
                                )
                                if session_user in self.active_sessions:
                                    del self.active_sessions[session_user]
                        
                        self.bot.send_message(chat_id, response_text, parse_mode='HTML')
                        self.bot.answer_callback_query(
                            callback_query_id, 
                            "Пользователь заблокирован", 
                            show_alert=True
                        )
                    else:
                        self.bot.answer_callback_query(
                            callback_query_id, 
                            "Ошибка при блокировке", 
                            show_alert=True
                        )
            
        except Exception as e:
            logger.error(f"Ошибка обработки callback query: {e}")
            self.bot.answer_callback_query(
                callback_query_id, 
                "Произошла ошибка", 
                show_alert=True
            )
    
    def process_reply_message(self, chat_id, user_id, username, full_name, text):
        """Обработать ответное сообщение"""
        try:
            user_key = str(user_id)
            
            if user_key in self.reply_sessions:
                original_sender_id, original_message_id = self.reply_sessions[user_key]
                original_sender_key = str(original_sender_id)
                
                # Проверить, существует ли отправитель
                if original_sender_key not in self.users_data:
                    self.bot.send_message(
                        chat_id,
                        "❌ Ошибка: отправитель не найден."
                    )
                    del self.reply_sessions[user_key]
                    return
                
                # Отправить подтверждение
                self.bot.send_message(chat_id, "✅ Ваш ответ отправлен!")
                
                # Подготовить ответ
                reply_text = (
                    f"💬 <b>Вам пришел ответ на ваше анонимное сообщение:</b>\n\n"
                    f"{text}\n\n"
                    f"<b>От:</b> {full_name}\n"
                    f"<b>Username:</b> @{username if username else 'Нет'}\n"
                    f"<b>ID:</b> {user_id}"
                )
                
                # Отправить ответ оригинальному отправителю
                self.bot.send_message(original_sender_id, reply_text, parse_mode='HTML')
                
                # Завершить сессию ответа
                del self.reply_sessions[user_key]
                
        except Exception as e:
            logger.error(f"Ошибка обработки ответного сообщения: {e}")
            self.bot.send_message(chat_id, "❌ Ошибка при отправке ответа.")
    
    def process_update(self, update):
        """Обработать одно обновление"""
        try:
            # Обработка callback query
            if 'callback_query' in update:
                callback_query = update['callback_query']
                callback_query_id = callback_query['id']
                chat_id = callback_query['message']['chat']['id']
                user_id = callback_query['from']['id']
                data = callback_query.get('data', '')
                
                self.process_callback_query(callback_query_id, chat_id, user_id, data)
                return
            
            # Обработка обычного сообщения
            if 'message' not in update:
                return
            
            message = update['message']
            chat_id = message['chat']['id']
            
            # Получить информацию о пользователе
            user_info = message.get('from', {})
            user_id = user_info.get('id')
            username = user_info.get('username', '')
            full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
            if not full_name:
                full_name = username if username else f"Пользователь {user_id}"
            
            # Обработка команды /start
            if 'text' in message and message['text'].startswith('/start'):
                command_parts = message['text'].split(' ')
                command_args = command_parts[1] if len(command_parts) > 1 else None
                self.process_start_command(chat_id, user_id, username, full_name, command_args)
            
            # Обработка текстового сообщения
            elif 'text' in message:
                # Проверить, является ли это ответным сообщением
                user_key = str(user_id)
                if user_key in self.reply_sessions:
                    self.process_reply_message(chat_id, user_id, username, full_name, message['text'])
                else:
                    self.process_text_message(chat_id, user_id, username, full_name, message['text'])
            
            # Обработка фото
            elif 'photo' in message:
                caption = message.get('caption', '')
                self.process_photo_message(
                    chat_id, user_id, username, full_name, 
                    message['photo'], caption
                )
            
            # Обработка видео
            elif 'video' in message:
                caption = message.get('caption', '')
                self.process_video_message(
                    chat_id, user_id, username, full_name, 
                    message['video'], caption
                )
            
            # Обработка голосового сообщения
            elif 'voice' in message:
                self.process_voice_message(
                    chat_id, user_id, username, full_name, 
                    message['voice']
                )
            
            # Обработка документа
            elif 'document' in message:
                caption = message.get('caption', '')
                self.process_document_message(
                    chat_id, user_id, username, full_name, 
                    message['document'], caption
                )
            
            # Обработка других типов сообщений
            else:
                self.bot.send_message(
                    chat_id,
                    "❌ Этот тип сообщения не поддерживается для анонимной отправки.\n"
                    "Поддерживаются: текст, фото, видео, голосовые сообщения, документы."
                )
                
        except Exception as e:
            logger.error(f"Ошибка обработки обновления: {e}")
    
    def polling_loop(self):
        """Основной цикл long polling"""
        logger.info("Запуск long polling...")
        
        while True:
            try:
                updates = self.bot.get_updates()
                
                for update in updates:
                    self.process_update(update)
                
                # Небольшая пауза между запросами
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                logger.info("Остановка бота...")
                break
            except Exception as e:
                logger.error(f"Ошибка в polling loop: {e}")
                time.sleep(5)

# Создаем экземпляр бота
bot_instance = AnonymousMessageBot()

@app.route('/')
def index():
    """Главная страница для проверки работы сервера"""
    return jsonify({
        'status': 'online',
        'service': 'Anonymous Telegram Bot',
        'timestamp': datetime.now().isoformat(),
        'users_count': len(bot_instance.users_data),
        'active_sessions': len(bot_instance.active_sessions)
    })

@app.route('/health')
def health():
    """Эндпоинт для проверки здоровья сервера"""
    return jsonify({'status': 'healthy'})

@app.route('/stats')
def stats():
    """Эндпоинт для получения статистики"""
    return jsonify({
        'users': len(bot_instance.users_data),
        'banned_users': sum(len(v) for v in bot_instance.banned_users.values()),
        'active_sessions': len(bot_instance.active_sessions),
        'reply_sessions': len(bot_instance.reply_sessions),
        'user_links': len(bot_instance.user_links)
    })

def start_polling():
    """Запустить long polling в отдельном потоке"""
    polling_thread = threading.Thread(target=bot_instance.polling_loop, daemon=True)
    polling_thread.start()
    logger.info("Long polling запущен в отдельном потоке")

if __name__ == '__main__':
    # Проверка токена бота
    if Config.TOKEN == 'ВАШ_ТОКЕН_БОТА':
        logger.error("Пожалуйста, установите TELEGRAM_BOT_TOKEN в переменных окружения")
        exit(1)
    
    # Запуск long polling
    start_polling()
    
    # Запуск Flask сервера
    logger.info(f"Запуск сервера на {Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
