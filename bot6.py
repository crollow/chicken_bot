import os
import io
import requests
import telebot
from flask import Flask
from threading import Thread
from datetime import datetime

# --- КОНФИГУРАЦИЯ (заполни своими данными) ---
API_KEY = "sk-MmL4liaBAGKxeVZ_3WaJ9w" 
BOT_TOKEN = "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4"
API_URL = "https://litellm.tokengate.ru/v1/chat/completions"  # или другой прокси

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# Хранилище контекста для каждого пользователя
user_contexts = {}

# Промпт для писателя
WRITER_PROMPT = """Ты — профессиональный писатель фанфиков с 20-летним опытом. 
ТВОИ ОСНОВНЫЕ ПРАВИЛА:
1. Каждая глава должна быть ОЧЕНЬ подробной (минимум 2500-3000 слов)
2. Используй: детальные описания, внутренние монологи, диалоги, метафоры
3. Создавай атмосферу через детали: запахи, звуки, текстуры
4. Развивай персонажей в каждой главе
5. ОСТАНАВЛИВАЙСЯ в конце главы на интригующем моменте

ТЕМПЕРАТУРА: 0.9 (будь креативным)
СТИЛЬ: Живой, эмоциональный, кинематографичный"""

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
📚 *Фанфик-Бот Писатель*

*Основные команды:*
/start - начало работы
/help - эта справка
/new - начать новую историю (сброс контекста)
/status - посмотреть прогресс
/continue - продолжить последнюю историю

*Как писать фанфики:*
1. Скажи "Напиши фанфик про [тема]"
2. Бот спросит количество глав
3. Пиши "глава 1" для начала
4. Для продолжения: "глава 2", "следующая глава" или просто "дальше"

Пример: "Напиши фанфик про вампиров в школе магии"
"""
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['new'])
def new_story(message):
    user_id = message.chat.id
    user_contexts[user_id] = {
        'story_title': None,
        'current_chapter': 0,
        'total_chapters': 0,
        'plot_summary': '',
        'characters': [],
        'history': [],
        'last_request': None
    }
    bot.send_message(message.chat.id, "✨ Новая история готова! Опиши идею для фанфика.")

@bot.message_handler(commands=['status'])
def check_status(message):
    user_id = message.chat.id
    if user_id in user_contexts:
        ctx = user_contexts[user_id]
        status = f"""
📖 *Текущая история:*
├ Название: {ctx['story_title'] or 'Еще не задано'}
├ Глава: {ctx['current_chapter']}/{ctx['total_chapters']}
├ Персонажи: {', '.join(ctx['characters'][:3]) if ctx['characters'] else 'Еще не созданы'}
└ Сюжет: {ctx['plot_summary'][:100]}...
        """
        bot.send_message(message.chat.id, status, parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "📭 У тебя нет активной истории. Начни новую через /new")

@bot.message_handler(commands=['continue'])
def continue_story(message):
    user_id = message.chat.id
    if user_id in user_contexts and user_contexts[user_id]['current_chapter'] > 0:
        ctx = user_contexts[user_id]
        if ctx['current_chapter'] < ctx['total_chapters']:
            bot.send_message(message.chat.id, f"Продолжаем историю! Пиши 'глава {ctx['current_chapter'] + 1}' или 'дальше'")
        else:
            bot.send_message(message.chat.id, "✅ История завершена! Начни новую через /new")
    else:
        bot.send_message(message.chat.id, "У тебя нет незавершенной истории. Начни новую!")

def initialize_user(user_id):
    """Инициализирует контекст пользователя"""
    if user_id not in user_contexts:
        user_contexts[user_id] = {
            'story_title': None,
            'current_chapter': 0,
            'total_chapters': 0,
            'plot_summary': '',
            'characters': [],
            'history': [],
            'last_request': None
        }
    return user_contexts[user_id]

def build_conversation_history(ctx, user_message):
    """Строит историю диалога для контекста"""
    messages = [
        {"role": "system", "content": WRITER_PROMPT}
    ]
    
    # Добавляем общую информацию о истории
    if ctx['plot_summary']:
        messages.append({
            "role": "system", 
            "content": f"ОБЩАЯ ИНФОРМАЦИЯ ОБ ИСТОРИИ:\nНазвание: {ctx['story_title']}\nСюжет: {ctx['plot_summary']}\nПерсонажи: {', '.join(ctx['characters'])}"
        })
    
    # Добавляем предыдущие главы
    for entry in ctx['history'][-5:]:  # Последние 5 записей для контекста
        messages.append({"role": "user", "content": entry['request']})
        messages.append({"role": "assistant", "content": entry['response'][:500] + "..."})
    
    # Текущий запрос
    chapter_info = f"Сейчас пишем главу {ctx['current_chapter']} из {ctx['total_chapters']}."
    if ctx['current_chapter'] > 1:
        chapter_info += f" Предыдущая глава закончилась на: {ctx['history'][-1]['response'][-200:] if ctx['history'] else 'начало'}"
    
    final_prompt = f"{chapter_info}\n\nЗАДАНИЕ: {user_message}\n\nВАЖНО: Пиши ОЧЕНЬ длинную и подробную главу (2500+ слов)."
    
    messages.append({"role": "user", "content": final_prompt})
    return messages

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.chat.id
    user_message = message.text.lower().strip()
    ctx = initialize_user(user_id)
    
    # Определяем тип запроса
    if 'напиши фанфик' in user_message or 'хочу фанфик' in user_message:
        # Запрос новой истории
        theme = message.text.replace('напиши фанфик', '').replace('хочу фанфик', '').strip()
        if not theme:
            bot.send_message(user_id, "📝 О какой теме должен быть фанфик? Например: 'про вампиров в школе' или 'по вселенной Гарри Поттера'")
            return
        
        ctx['plot_summary'] = theme
        ctx['story_title'] = f"Фанфик: {theme[:30]}..."
        ctx['current_chapter'] = 0
        
        # Спрашиваем количество глав
        markup = telebot.types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
        for i in [1, 3, 5, 7, 10]:
            markup.add(str(i))
        msg = bot.send_message(
            user_id, 
            f"🎬 Отлично! Фанфик '{theme}'.\nСколько глав будет в истории? (1-10)",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, ask_chapters)
        
    elif 'глава' in user_message or 'дальше' in user_message or 'следующая' in user_message:
        # Запрос следующей главы
        if ctx['total_chapters'] == 0:
            bot.send_message(user_id, "Сначала определи, сколько глав будет в истории. Напиши 'напиши фанфик про...'")
            return
            
        # Определяем номер главы
        if 'глава' in user_message:
            try:
                # Извлекаем номер из текста
                words = user_message.split()
                for word in words:
                    if word.isdigit():
                        chapter_num = int(word)
                        break
                else:
                    chapter_num = ctx['current_chapter'] + 1
            except:
                chapter_num = ctx['current_chapter'] + 1
        else:
            chapter_num = ctx['current_chapter'] + 1
        
        # Проверяем границы
        if chapter_num > ctx['total_chapters']:
            bot.send_message(user_id, f"✅ История завершена! Все {ctx['total_chapters']} глав написаны.\nНачни новую через /new")
            return
        
        if chapter_num <= ctx['current_chapter']:
            bot.send_message(user_id, f"Эта глава уже написана. Сейчас на очереди глава {ctx['current_chapter'] + 1}")
            return
        
        # Пишем главу
        ctx['current_chapter'] = chapter_num
        write_chapter(message, chapter_num)
        
    else:
        # Обычное сообщение - пытаемся понять
        bot.send_message(user_id, "📝 Чтобы начать, напиши: 'Напиши фанфик про [тема]'\n\nИли используй команды:\n/new - новая история\n/continue - продолжить\n/status - статус")

def ask_chapters(message):
    """Обрабатывает выбор количества глав"""
    user_id = message.chat.id
    try:
        chapters = int(message.text)
        if 1 <= chapters <= 20:
            ctx = user_contexts[user_id]
            ctx['total_chapters'] = chapters
            
            # Удаляем клавиатуру
            remove_markup = telebot.types.ReplyKeyboardRemove()
            bot.send_message(user_id, f"✅ Отлично! Будет {chapters} глав.\n\nПиши 'глава 1' чтобы начать первую главу!", reply_markup=remove_markup)
        else:
            bot.send_message(user_id, "Пожалуйста, укажи число от 1 до 20")
    except:
        bot.send_message(user_id, "Пожалуйста, укажи цифрой (например: 5)")

def write_chapter(message, chapter_num):
    """Пишет главу фанфика"""
    user_id = message.chat.id
    ctx = user_contexts[user_id]
    
    # Статус сообщение
    status_msg = bot.send_message(user_id, f"✍️ Пишу главу {chapter_num}/{ctx['total_chapters']}... Это займет 30-60 секунд")
    
    # Готовим промпт
    prompt = f"Напиши главу {chapter_num} фанфика. Тема: {ctx['plot_summary']}. Глава должна быть ОЧЕНЬ длинной и подробной."
    
    # Строим историю диалога
    messages = build_conversation_history(ctx, prompt)
    
    # Отправляем запрос к API
    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": messages,
                "temperature": 0.9,
                "max_tokens": 4000
            },
            timeout=90
        )
        
        if response.status_code != 200:
            bot.edit_message_text(f"❌ Ошибка API: {response.status_code}", user_id, status_msg.message_id)
            return
        
        result = response.json()
        chapter_text = result['choices'][0]['message']['content']
        
        # Сохраняем в историю
        ctx['history'].append({
            'request': prompt,
            'response': chapter_text,
            'chapter': chapter_num,
            'timestamp': datetime.now().isoformat()
        })
        
        # Отправляем пользователю
        with io.BytesIO(chapter_text.encode('utf-8')) as file:
            file.name = f"Глава_{chapter_num}_{ctx['story_title']}.txt"
            caption = f"📖 Глава {chapter_num}: {ctx['story_title']}"
            
            if chapter_num < ctx['total_chapters']:
                caption += f"\n\nДля следующей главы напиши 'глава {chapter_num + 1}' или 'дальше'"
            else:
                caption += "\n\n🎉 История завершена! /new - начать новую"
            
            bot.send_document(user_id, file, caption=caption)
        
        bot.delete_message(user_id, status_msg.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", user_id, status_msg.message_id)

# Flask для веб-сервера (для деплоя)
@app.route('/')
def home():
    return "Фанфик-бот работает! Пользователей: " + str(len(user_contexts))

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Запуск
if __name__ == "__main__":
    print("Бот запускается...")
    # Запускаем Flask в отдельном потоке
    Thread(target=run_flask, daemon=True).start()
    # Запускаем бота
    bot.infinity_polling()
