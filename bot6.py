import os
import io
import requests
import telebot
import json
import html
from flask import Flask
from threading import Thread
from datetime import datetime

# --- КОНФИГУРАЦИЯ (ЗАПОЛНИ!) ---
TG_TOKEN = "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4"
GEMINI_KEY = "AIzaSyAcxo8c_uO6OI-tpThvuVZeJ7RB71K98C4"
MODEL = "gemini-2.5-flash"  # или твоя версия модели

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = telebot.TeleBot(TG_TOKEN)
app = Flask('')

# --- ХРАНИЛИЩЕ КОНТЕКСТА ---
user_contexts = {}

# --- СИСТЕМНЫЙ ПРОМПТ ДЛЯ ГЕМИНИ ---
SYSTEM_PROMPT = """Ты — ПРОФЕССИОНАЛЬНЫЙ ПИСАТЕЛЬ ФАНФИКОВ с 20-летним опытом.

ТВОИ КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. ДЛИНА: Каждая глава должна быть ОЧЕНЬ ДЛИННОЙ (4000-6000 слов)
2. ДЕТАЛИ: Используй максимальную детализацию:
   • Каждое движение, жест, мимика
   • Все запахи, звуки, текстуры
   • Полные внутренние монологи
   • Подробные описания локаций
3. СТИЛЬ: Художественный, кинематографичный, immersive
4. ФОРМАТ: Используй HTML теги для оформления:
   • <h3> для заголовков глав и сцен
   • <p> для абзацев
   • <b> для важных моментов
   • <i> для мыслей и выделения
5. НИКОГДА не сокращай текст! Если кажется "достаточно" — добавь еще деталей.

СТРУКТУРА ГЛАВЫ:
1. Начало (установка сцены, 2-3 абзаца)
2. Развитие (основные события, диалоги)
3. Кульминация (напряженный момент)
4. Завершение (интрига для следующей главы)"""

# --- ФУНКЦИЯ ДЛЯ ВЫЗОВА GEMINI API ---
def get_gemini_text(prompt, context=None):
    """Отправляет запрос к Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # Собираем полный промпт с контекстом
    full_prompt = SYSTEM_PROMPT
    
    if context and context.get('history'):
        full_prompt += "\n\n=== КОНТЕКСТ ПРЕДЫДУЩИХ ГЛАВ ==="
        for entry in context['history'][-2:]:  # Берем последние 2 главы
            full_prompt += f"\nГлава {entry['chapter']}: {entry['text'][:300]}..."
    
    if context and context.get('story_info'):
        full_prompt += f"\n\n=== ИНФОРМАЦИЯ ОБ ИСТОРИИ ===\n"
        full_prompt += f"Название: {context['story_info'].get('title', 'Без названия')}\n"
        full_prompt += f"Сюжет: {context['story_info'].get('plot', '')}\n"
        full_prompt += f"Персонажи: {', '.join(context['story_info'].get('characters', []))}"
    
    full_prompt += f"\n\n=== ЗАДАНИЕ ===\n{prompt}"
    
    data = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 8192,  # Максимальная длина
            "temperature": 0.85,      # Креативность
            "topP": 0.95,
            "topK": 40
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=120)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"❌ Ошибка API: {response.status_code} - {response.text[:100]}"
    except Exception as e:
        return f"❌ Ошибка сети: {str(e)}"

# --- HTML ШАБЛОН ДЛЯ КНИГИ ---
def create_html_book(title, chapter_num, content, total_chapters):
    """Создает красивый HTML файл в стиле книги"""
    html_template = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} - Глава {chapter_num}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Old+Standard+TT&family=Cormorant+Garamond&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            padding: 40px 20px;
            font-family: 'Cormorant Garamond', serif;
            color: #2c1810;
            line-height: 1.8;
        }}
        
        .book-container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 60px 50px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.15);
            border-radius: 8px;
            position: relative;
            border: 1px solid #e0d6c9;
        }}
        
        .book-container::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: linear-gradient(90deg, #8b4513, #d2691e, #8b4513);
            border-radius: 8px 8px 0 0;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 50px;
            padding-bottom: 30px;
            border-bottom: 3px double #8b4513;
        }}
        
        h1 {{
            font-family: 'Old Standard TT', serif;
            font-size: 2.8em;
            color: #2c1810;
            margin-bottom: 10px;
            font-weight: 700;
            letter-spacing: 1px;
        }}
        
        .chapter-title {{
            font-size: 1.6em;
            color: #8b4513;
            font-style: italic;
            margin: 20px 0;
            padding: 10px 0;
            border-bottom: 1px solid #e0d6c9;
        }}
        
        .content {{
            font-size: 1.25em;
            text-align: justify;
        }}
        
        .content h3 {{
            font-family: 'Old Standard TT', serif;
            color: #5d4037;
            margin: 30px 0 15px 0;
            font-size: 1.4em;
        }}
        
        .content p {{
            margin-bottom: 1.5em;
            text-indent: 2em;
            text-align: justify;
        }}
        
        .content p:first-of-type::first-letter {{
            font-size: 3.5em;
            float: left;
            line-height: 0.85;
            margin: 0.1em 0.15em 0 0;
            color: #8b4513;
            font-weight: bold;
            font-family: 'Old Standard TT', serif;
        }}
        
        .content b {{
            color: #5d4037;
            font-weight: 700;
        }}
        
        .content i {{
            color: #6d4c41;
            font-style: italic;
        }}
        
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e0d6c9;
            text-align: center;
            color: #795548;
            font-size: 0.9em;
        }}
        
        .chapter-nav {{
            display: flex;
            justify-content: space-between;
            margin-top: 40px;
            padding: 15px;
            background: #faf3e8;
            border-radius: 5px;
        }}
        
        .page-number {{
            position: absolute;
            bottom: 20px;
            right: 30px;
            color: #a1887f;
            font-size: 0.9em;
        }}
        
        @media (max-width: 768px) {{
            .book-container {{ padding: 30px 20px; }}
            h1 {{ font-size: 2em; }}
            .content {{ font-size: 1.1em; }}
        }}
    </style>
</head>
<body>
    <div class="book-container">
        <div class="header">
            <h1>{html.escape(title)}</h1>
            <div class="chapter-title">Глава {chapter_num} из {total_chapters}</div>
        </div>
        
        <div class="content">
            {content}
        </div>
        
        <div class="footer">
            Создано Фанфик-Ботом с использованием {MODEL}<br>
            {datetime.now().strftime("%d %B %Y г., %H:%M")}
        </div>
        
        <div class="page-number">Страница {chapter_num}</div>
    </div>
</body>
</html>'''
    return html_template

# --- КОМАНДЫ БОТА ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
📚 <b>ФАНФИК-БОТ с Gemini 2.5 Flash</b>

<u>Как начать:</u>
Просто напиши: <b>"напиши фанфик про [тема]"</b>

<u>Примеры:</u>
• напиши фанфик про вампиров в школе магии
• напиши фанфик по вселенной Наруто
• напиши фанфик про попаданца в средневековье

<u>Управление главами:</u>
• "глава 1" - начать первую главу
• "глава 2" - следующая глава
• "дальше" или "продолжение"
• /new - начать новую историю
• /status - статус текущей истории
• /clear - удалить контекст

<u>Формат вывода:</u>
Бот отправляет 2 файла:
1. 📄 <b>TXT</b> - чистый текст для чтения
2. 🌐 <b>HTML</b> - красивое оформление в стиле книги

<u>Важно:</u>
Бот пишет <b>ОЧЕНЬ ДЛИННЫЕ</b> главы (4000+ слов)!
"""
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

@bot.message_handler(commands=['new'])
def new_story(message):
    user_id = message.chat.id
    user_contexts[user_id] = {
        'story_info': {
            'title': '',
            'plot': '',
            'characters': [],
            'total_chapters': 0,
            'created_at': datetime.now().isoformat()
        },
        'current_chapter': 0,
        'history': []
    }
    bot.send_message(message.chat.id, "✨ <b>Готово!</b> Контекст очищен.\n\nНапиши: <i>\"напиши фанфик про...\"</i>", parse_mode='HTML')

@bot.message_handler(commands=['clear'])
def clear_context(message):
    user_id = message.chat.id
    if user_id in user_contexts:
        del user_contexts[user_id]
    bot.send_message(message.chat.id, "✅ Контекст полностью удален!", parse_mode='HTML')

@bot.message_handler(commands=['status'])
def check_status(message):
    user_id = message.chat.id
    if user_id in user_contexts and user_contexts[user_id]['story_info']['plot']:
        ctx = user_contexts[user_id]
        info = ctx['story_info']
        
        status = f"""
📖 <b>ТЕКУЩАЯ ИСТОРИЯ</b>

<b>Название:</b> {info['title'] or 'Без названия'}
<b>Сюжет:</b> {info['plot'][:100]}...
<b>Глав написано:</b> {ctx['current_chapter']} из {info['total_chapters']}
<b>Персонажи:</b> {', '.join(info['characters'][:3]) if info['characters'] else 'Еще не созданы'}
<b>Начата:</b> {info['created_at'][:10]}

<b>Что дальше:</b>
"""
        if ctx['current_chapter'] < info['total_chapters']:
            next_chapter = ctx['current_chapter'] + 1
            status += f"Напиши <b>\"глава {next_chapter}\"</b> для продолжения"
        elif info['total_chapters'] > 0:
            status += f"✅ <b>История завершена!</b> Все {info['total_chapters']} глав написаны.\n/new - начать новую"
        else:
            status += "Напиши <b>\"напиши фанфик про...\"</b> чтобы начать"
            
        bot.send_message(message.chat.id, status, parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "📭 Нет активной истории. Начни через: <b>\"напиши фанфик про...\"</b>", parse_mode='HTML')

# --- ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ---
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.chat.id
    user_message = message.text.strip()
    
    # Инициализация контекста пользователя
    if user_id not in user_contexts:
        user_contexts[user_id] = {
            'story_info': {
                'title': '',
                'plot': '',
                'characters': [],
                'total_chapters': 0,
                'created_at': datetime.now().isoformat()
            },
            'current_chapter': 0,
            'history': []
        }
    
    ctx = user_contexts[user_id]
    
    # 1. ОБРАБОТКА ЗАПРОСА НОВОГО ФАНФИКА
    if user_message.lower().startswith('напиши фанфик'):
        theme = user_message.lower().replace('напиши фанфик', '').replace('про', '').strip()
        
        if not theme or len(theme) < 3:
            bot.send_message(user_id, "📝 <b>Опиши тему подробнее!</b>\n\nПримеры:\n• напиши фанфик про <i>любовь вампира и оборотня</i>\n• напиши фанфик про <i>попаданца в игровой мир</i>\n• напиши фанфик про <i>школу магии в современном мире</i>", parse_mode='HTML')
            return
        
        # Сохраняем тему
        ctx['story_info']['plot'] = theme
        ctx['story_info']['title'] = f"Фанфик: {theme[:40]}..."
        ctx['current_chapter'] = 0
        ctx['history'] = []
        
        # Создаем клавиатуру для выбора количества глав
        markup = telebot.types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True, one_time_keyboard=True)
        buttons = ['1', '3', '5', '7', '10', '15']
        markup.add(*buttons)
        
        bot.send_message(
            user_id,
            f"🎬 <b>Отличная идея!</b>\n\n<i>«{theme}»</i>\n\n<b>Сколько глав будет в истории?</b>",
            reply_markup=markup,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_chapter_count)
    
    # 2. ОБРАБОТКА ЗАПРОСА ГЛАВЫ
    elif any(keyword in user_message.lower() for keyword in ['глава', 'дальше', 'продолжи', 'следующая']):
        if ctx['story_info']['total_chapters'] == 0:
            bot.send_message(user_id, "❌ <b>Сначала укажи количество глав!</b>\n\nНапиши: <i>\"напиши фанфик про...\"</i>", parse_mode='HTML')
            return
        
        # Определяем номер главы
        if 'глава' in user_message.lower():
            try:
                words = user_message.lower().split()
                chapter_num = None
                for word in words:
                    if word.isdigit():
                        chapter_num = int(word)
                        break
                if not chapter_num:
                    chapter_num = ctx['current_chapter'] + 1
            except:
                chapter_num = ctx['current_chapter'] + 1
        else:
            chapter_num = ctx['current_chapter'] + 1
        
        # Проверяем границы
        if chapter_num > ctx['story_info']['total_chapters']:
            bot.send_message(user_id, f"✅ <b>История завершена!</b>\n\nВсе {ctx['story_info']['total_chapters']} глав написаны.\n\n/new - начать новую историю", parse_mode='HTML')
            return
        
        if chapter_num <= ctx['current_chapter']:
            bot.send_message(user_id, f"ℹ️ Эта глава уже написана.\nСледующая: <b>глава {ctx['current_chapter'] + 1}</b>", parse_mode='HTML')
            return
        
        # Запускаем написание главы
        ctx['current_chapter'] = chapter_num
        write_chapter(user_id, chapter_num)
    
    else:
        # Если непонятный запрос
        bot.send_message(user_id, "📝 <b>Чтобы начать:</b>\n\nНапиши: <i>\"напиши фанфик про [тема]\"</i>\n\nИли используй команды:\n/status - статус\n/new - новая история\n/help - справка", parse_mode='HTML')

def process_chapter_count(message):
    """Обрабатывает выбор количества глав"""
    user_id = message.chat.id
    try:
        chapters = int(message.text.strip())
        if 1 <= chapters <= 20:
            ctx = user_contexts[user_id]
            ctx['story_info']['total_chapters'] = chapters
            
            # Убираем клавиатуру
            remove_markup = telebot.types.ReplyKeyboardRemove()
            bot.send_message(
                user_id,
                f"✅ <b>Отлично!</b> Будет <b>{chapters}</b> глав.\n\nТеперь напиши <b>\"глава 1\"</b> чтобы начать первую <i>очень длинную</i> главу!",
                reply_markup=remove_markup,
                parse_mode='HTML'
            )
        else:
            bot.send_message(user_id, "⚠️ Укажи число от 1 до 20", parse_mode='HTML')
    except:
        bot.send_message(user_id, "⚠️ Пожалуйста, укажи цифрой (например: 5)", parse_mode='HTML')

def write_chapter(user_id, chapter_num):
    """Пишет главу фанфика"""
    ctx = user_contexts[user_id]
    
    # Статус сообщение
    status_msg = bot.send_message(
        user_id,
        f"✍️ <b>Пишу главу {chapter_num}/{ctx['story_info']['total_chapters']}...</b>\n\n<i>Это займет 20-40 секунд</i>\n\n⏳ Генерация через {MODEL}...",
        parse_mode='HTML'
    )
    
    try:
        # Готовим промпт для Gemini
        prompt = f"Напиши ГЛАВУ {chapter_num} фанфика. Тема: {ctx['story_info']['plot']}. "
        
        if chapter_num == 1:
            prompt += "Это ПЕРВАЯ глава. Представь персонажей, установи сеттинг, начни сюжет. "
        else:
            prompt += f"Продолжи историю с предыдущей главы. "
        
        prompt += "Глава должна быть ОЧЕНЬ ДЛИННОЙ И ПОДРОБНОЙ (4000-6000 слов). "
        prompt += "Используй HTML теги: <h3> для заголовков, <p> для абзацев, <b> для выделения, <i> для мыслей."
        
        # Вызываем Gemini API
        chapter_text = get_gemini_text(prompt, ctx)
        
        # Проверяем на ошибки
        if chapter_text.startswith("❌"):
            bot.edit_message_text(chapter_text, user_id, status_msg.message_id, parse_mode='HTML')
            return
        
        # Сохраняем в историю
        ctx['history'].append({
            'chapter': chapter_num,
            'text': chapter_text[:500] + '...',
            'timestamp': datetime.now().isoformat()
        })
        
        # Очищаем текст для TXT версии
        txt_content = chapter_text
        for tag in ['<b>', '</b>', '<i>', '</i>', '<h3>', '</h3>']:
            txt_content = txt_content.replace(tag, '')
        txt_content = txt_content.replace('<p>', '\n\n').replace('</p>', '')
        
        # Добавляем заголовок
        title = ctx['story_info']['title'] or f"Глава_{chapter_num}"
        txt_full = f"{title}\nГлава {chapter_num}\n\n{txt_content}\n\nСоздано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        # Создаем HTML версию
        html_content = create_html_book(
            title=title,
            chapter_num=chapter_num,
            content=chapter_text,
            total_chapters=ctx['story_info']['total_chapters']
        )
        
        # Отправляем файлы
        # 1. TXT файл
        with io.BytesIO(txt_full.encode('utf-8')) as txt_file:
            txt_file.name = f"{title.replace(':', '_')}_Глава_{chapter_num}.txt"
            caption = f"📖 <b>{title}</b>\nГлава {chapter_num}/{ctx['story_info']['total_chapters']}"
            
            if chapter_num < ctx['story_info']['total_chapters']:
                caption += f"\n\nДля следующей главы напиши <b>«глава {chapter_num + 1}»</b>"
            else:
                caption += "\n\n🎉 <b>История завершена!</b>\n/new - начать новую"
            
            bot.send_document(user_id, txt_file, caption=caption, parse_mode='HTML')
        
        # 2. HTML файл
        with io.BytesIO(html_content.encode('utf-8')) as html_file:
            html_file.name = f"{title.replace(':', '_')}_Глава_{chapter_num}.html"
            bot.send_document(user_id, html_file, caption="📚 HTML версия в стиле книги (открой в браузере)")
        
        # Удаляем статус
        bot.delete_message(user_id, status_msg.message_id)
        
        # Статистика
        word_count = len(txt_content.split())
        bot.send_message(
            user_id,
            f"✅ <b>Глава {chapter_num} готова!</b>\n\n📊 <b>Статистика:</b>\n├ Слов: {word_count:,}\n├ Символов: {len(txt_content):,}\n└ {'🎉 Последняя глава истории!' if chapter_num == ctx['story_info']['total_chapters'] else f'➡️ Следующая: глава {chapter_num + 1}'}",
            parse_mode='HTML'
        )
        
    except Exception as e:
        error_msg = f"❌ <b>Ошибка при создании главы:</b>\n\n{str(e)[:200]}"
        bot.edit_message_text(error_msg, user_id, status_msg.message_id, parse_mode='HTML')

# --- FLASK ДЛЯ RENDER ---
@app.route('/')
def home():
    active = len([uid for uid, ctx in user_contexts.items() if ctx['current_chapter'] > 0])
    return f"""
    <h1>📚 Фанфик-Бот с Gemini 2.5 Flash</h1>
    <p>👥 Пользователей: {len(user_contexts)}</p>
    <p>📖 Активных историй: {active}</p>
    <p>⚡ Модель: {MODEL}</p>
    <p>🕐 Время: {datetime.now().strftime('%H:%M:%S')}</p>
    """

@app.route('/ping')
def ping():
    return "pong"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- ЗАПУСК ---
if __name__ == "__main__":
    print("=" * 50)
    print(f"🤖 ФАНФИК-БОТ ЗАПУСКАЕТСЯ")
    print(f"📚 Модель: {MODEL}")
    print(f"🔑 API ключ: {'✅ Установлен' if GEMINI_KEY and 'ВАШ' not in GEMINI_KEY else '❌ НЕ НАСТРОЕН!'}")
    print(f"🤖 Токен бота: {'✅ Установлен' if TG_TOKEN and 'ВАШ' not in TG_TOKEN else '❌ НЕ НАСТРОЕН!'}")
    print("=" * 50)
    
    # Проверяем API
    if GEMINI_KEY and "ВАШ" not in GEMINI_KEY:
        print("🔍 Проверяю подключение к Gemini API...")
        try:
            test_url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_KEY}"
            response = requests.post(test_url, json={"contents": [{"parts": [{"text": "Тест"}]}]})
            if response.status_code == 200:
                print("✅ Gemini API подключен успешно!")
            else:
                print(f"⚠️ Gemini API: код {response.status_code}")
        except:
            print("⚠️ Не удалось проверить Gemini API")
    
    # Запускаем Flask в фоне
    Thread(target=run_flask, daemon=True).start()
    
    # Запускаем бота
    print("🚀 Бот запущен! Ожидаю сообщения...")
    bot.infinity_polling()
