import os
import io
import google.generativeai as genai
import telebot
from flask import Flask
from threading import Thread
from datetime import datetime
import html

# --- КОНФИГУРАЦИЯ ---
GEMINI_API_KEY = "AIzaSyAcxo8c_uO6OI-tpThvuVZeJ7RB71K98C4"  # ⬅️ ВСТАВЬ СВОЙ КЛЮЧ
BOT_TOKEN = "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4"  # ⬅️ ВСТАВЬ ТОКЕН БОТА

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Хранилище контекста
user_contexts = {}

# МОЩНЫЙ ПРОМПТ ДЛЯ ГЕМИНИ
WRITER_PROMPT = """Ты — профессиональный писатель с 20-летним опытом. 
ТВОИ ОБЯЗАННОСТИ:

1. ДЛИНА: Каждая глава должна быть ОЧЕНЬ ДЛИННОЙ (3000-5000 слов)
2. ДЕТАЛИ: Используй максимально подробные описания:
   - Пейзажи (запахи, звуки, текстуры, цвета)
   - Эмоции (внутренние монологи, чувства, переживания)
   - Диалоги (естественные, с характерными репликами)
   - Действия (пошагово, с деталями движений)

3. СТРУКТУРА ГЛАВЫ:
   - Начало: установка сцены (2-3 абзаца)
   - Развитие: события и диалоги (основная часть)
   - Кульминация: напряженный момент
   - Завершение: интрига для следующей главы

4. СТИЛЬ: Кинематографичный, эмоциональный, immersive
5. НИКОГДА не сокращай текст! Если кажется, что достаточно — добавь еще деталей.

Примерный объем: 15-20 страниц текста."""

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
📚 <b>Фанфик-Бот с Gemini 1.5 Flash</b>

<u>Основные команды:</u>
/start - начало работы
/help - эта справка
/new - новая история (сброс)
/status - прогресс истории
/continue - продолжить

<u>Как работать:</u>
1. "Напиши фанфик про [тема]"
2. Выбери количество глав
3. "глава 1" - начать
4. "дальше" или "глава 2" - продолжать

<u>Примеры:</u>
• "Напиши фанфик про вампиров в школе магии"
• "Хочу фанфик по вселенной Наруто"
• "Создай историю про попаданца в средневековье"

Бот пишет <b>ОЧЕНЬ длинные</b> главы (3000+ слов)!
"""
    bot.send_message(message.chat.id, help_text, parse_mode='HTML')

@bot.message_handler(commands=['new'])
def new_story(message):
    user_id = message.chat.id
    user_contexts[user_id] = {
        'story_title': '',
        'current_chapter': 0,
        'total_chapters': 0,
        'plot_summary': '',
        'characters': [],
        'history': [],
        'style': 'подробный',
        'created_at': datetime.now().isoformat()
    }
    bot.send_message(message.chat.id, "✨ <b>Новая история начата!</b>\n\nОпиши идею для фанфика.\n\nНапример: <i>«про любовь вампира и оборотня в академии магии»</i>", parse_mode='HTML')

@bot.message_handler(commands=['status'])
def check_status(message):
    user_id = message.chat.id
    if user_id in user_contexts:
        ctx = user_contexts[user_id]
        
        status = f"""
📖 <b>ТЕКУЩАЯ ИСТОРИЯ</b>
├ <b>Название:</b> {ctx['story_title'] or 'Еще не задано'}
├ <b>Глава:</b> {ctx['current_chapter']}/{ctx['total_chapters']}
├ <b>Сюжет:</b> {ctx['plot_summary'][:80]}...
├ <b>Персонажи:</b> {', '.join(ctx['characters'][:3]) if ctx['characters'] else 'Еще не созданы'}
└ <b>Создана:</b> {ctx['created_at'][:10]}
"""
        if ctx['current_chapter'] > 0:
            last_chapter = ctx['history'][-1]['response'][:100].replace('\n', ' ') + '...' if ctx['history'] else 'нет'
            status += f"\n📝 <b>Последняя глава:</b>\n{last_chapter}"
        
        bot.send_message(message.chat.id, status, parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "📭 У тебя нет активной истории.\nНапиши <b>«напиши фанфик про...»</b>", parse_mode='HTML')

@bot.message_handler(commands=['continue'])
def continue_story(message):
    user_id = message.chat.id
    if user_id in user_contexts:
        ctx = user_contexts[user_id]
        if ctx['current_chapter'] < ctx['total_chapters']:
            next_chapter = ctx['current_chapter'] + 1
            bot.send_message(message.chat.id, f"🔄 <b>Продолжаем историю!</b>\n\nНапиши <b>«глава {next_chapter}»</b>", parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "✅ <b>История завершена!</b>\nВсе главы написаны.\n\n/new - начать новую", parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "У тебя нет незавершенной истории.", parse_mode='HTML')

def initialize_user(user_id):
    if user_id not in user_contexts:
        user_contexts[user_id] = {
            'story_title': '',
            'current_chapter': 0,
            'total_chapters': 0,
            'plot_summary': '',
            'characters': [],
            'history': [],
            'style': 'подробный',
            'created_at': datetime.now().isoformat()
        }
    return user_contexts[user_id]

def build_gemini_prompt(ctx, chapter_num):
    """Строит промпт для Gemini"""
    
    # Базовый промпт
    prompt_parts = [WRITER_PROMPT]
    
    # Информация о истории
    if ctx['plot_summary']:
        prompt_parts.append(f"\n\n=== ИНФОРМАЦИЯ ОБ ИСТОРИИ ===")
        prompt_parts.append(f"НАЗВАНИЕ: {ctx['story_title']}")
        prompt_parts.append(f"СЮЖЕТ: {ctx['plot_summary']}")
        if ctx['characters']:
            prompt_parts.append(f"ПЕРСОНАЖИ: {', '.join(ctx['characters'])}")
    
    # Контекст предыдущих глав
    if ctx['history']:
        prompt_parts.append(f"\n\n=== ПРЕДЫДУЩИЕ ГЛАВЫ ===")
        for i, entry in enumerate(ctx['history'][-3:], 1):
            prompt_parts.append(f"Глава {entry['chapter']}: {entry['response'][:300]}...")
    
    # Задание для текущей главы
    prompt_parts.append(f"\n\n=== ЗАДАНИЕ: ГЛАВА {chapter_num} ===")
    prompt_parts.append(f"Всего глав в истории: {ctx['total_chapters']}")
    
    if chapter_num == 1:
        prompt_parts.append(f"Напиши ПЕРВУЮ главу фанфика. {ctx['plot_summary']}")
        prompt_parts.append("Эта глава должна: 1) представить персонажей, 2) установить сеттинг, 3) начать основной конфликт.")
    else:
        prompt_parts.append(f"Напиши главу {chapter_num}. Продолжи историю естественно.")
        if ctx['history']:
            last_chapter_end = ctx['history'][-1]['response'][-500:] if ctx['history'] else ''
            prompt_parts.append(f"Предыдущая глава закончилась так: ...{last_chapter_end}")
    
    prompt_parts.append(f"\n\nТРЕБОВАНИЯ К ГЛАВЕ {chapter_num}:")
    prompt_parts.append("1. ОБЪЕМ: 3000-5000 слов (очень длинная)")
    prompt_parts.append("2. СТРУКТУРА: начало-развитие-кульминация-интрига")
    prompt_parts.append("3. ДЕТАЛИ: максимально подробные описания ВСЕГО")
    prompt_parts.append("4. ДИАЛОГИ: естественные, раскрывающие персонажей")
    prompt_parts.append("5. ЭМОЦИИ: глубокие внутренние переживания")
    prompt_parts.append("6. ЗАВЕРШЕНИЕ: интригующая концовка для продолжения")
    
    return "\n".join(prompt_parts)

def generate_html_chapter(chapter_num, title, text):
    """Создает HTML версию главы"""
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Глава {chapter_num}</title>
    <style>
        body {{
            font-family: 'Georgia', serif;
            line-height: 1.8;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #fefefe;
            color: #333;
        }}
        .header {{
            text-align: center;
            border-bottom: 3px double #ccc;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }}
        h1 {{
            color: #2c3e50;
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .chapter-number {{
            font-size: 1.2em;
            color: #7f8c8d;
            font-style: italic;
        }}
        .content {{
            font-size: 1.1em;
            text-align: justify;
        }}
        .content p {{
            margin-bottom: 1.5em;
            text-indent: 2em;
        }}
        .content p:first-of-type::first-letter {{
            font-size: 2.5em;
            float: left;
            line-height: 1;
            margin-right: 8px;
            color: #2c3e50;
            font-weight: bold;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{html.escape(title)}</h1>
        <div class="chapter-number">Глава {chapter_num}</div>
    </div>
    
    <div class="content">
"""
    
    # Форматируем абзацы
    paragraphs = text.split('\n\n')
    for para in paragraphs:
        if para.strip():
            html_content += f"        <p>{html.escape(para.strip())}</p>\n"
    
    html_content += """    </div>
    
    <div class="footer">
        Создано Фанфик-Ботом с Gemini 1.5 Flash<br>
        """ + datetime.now().strftime("%d.%m.%Y %H:%M") + """
    </div>
</body>
</html>"""
    
    return html_content

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.chat.id
    user_message = message.text.strip()
    ctx = initialize_user(user_id)
    
    # Обработка новой истории
    if 'напиши фанфик' in user_message.lower() or 'хочу фанфик' in user_message.lower():
        theme = user_message.lower().replace('напиши фанфик', '').replace('хочу фанфик', '').strip()
        
        if not theme or len(theme) < 5:
            bot.send_message(user_id, "📝 <b>Опиши тему подробнее!</b>\n\nНапример:\n<i>• про любовь вампира и оборотня\n• по вселенной Гарри Поттера\n• про попаданца в игровой мир</i>", parse_mode='HTML')
            return
        
        ctx['plot_summary'] = theme
        ctx['story_title'] = f"Фанфик: {theme[:40]}..."
        ctx['current_chapter'] = 0
        
        # Создаем клавиатуру для выбора глав
        markup = telebot.types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True, one_time_keyboard=True)
        buttons = ['1', '3', '5', '7', '10', '15', '20']
        markup.add(*buttons)
        
        bot.send_message(
            user_id,
            f"🎬 <b>Отличная идея!</b>\n\n<i>«{theme}»</i>\n\nСколько глав будет в истории?",
            reply_markup=markup,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, ask_chapters)
        
    # Обработка запроса главы
    elif any(word in user_message.lower() for word in ['глава', 'дальше', 'следующая', 'продолжи']):
        if ctx['total_chapters'] == 0:
            bot.send_message(user_id, "❌ <b>Сначала определи количество глав!</b>\n\nНапиши «напиши фанфик про...»", parse_mode='HTML')
            return
        
        # Определяем номер главы
        if 'глава' in user_message.lower():
            try:
                words = user_message.lower().split()
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
            bot.send_message(user_id, f"✅ <b>История завершена!</b>\n\nНаписано всех {ctx['total_chapters']} глав.\n\n/new - начать новую историю", parse_mode='HTML')
            return
        
        if chapter_num <= ctx['current_chapter']:
            bot.send_message(user_id, f"ℹ️ Эта глава уже написана.\nСледующая: <b>глава {ctx['current_chapter'] + 1}</b>", parse_mode='HTML')
            return
        
        # Запускаем написание главы
        ctx['current_chapter'] = chapter_num
        write_chapter(user_id, chapter_num)
        
    else:
        # Если не понял запрос
        bot.send_message(user_id, "📝 <b>Чтобы начать:</b>\n\n1. Напиши <i>«напиши фанфик про [тема]»</i>\n2. Выбери количество глав\n3. Пиши <i>«глава 1»</i> для начала\n\nИли используй /new", parse_mode='HTML')

def ask_chapters(message):
    """Обрабатывает выбор количества глав"""
    user_id = message.chat.id
    try:
        chapters = int(message.text.strip())
        if 1 <= chapters <= 50:
            ctx = user_contexts[user_id]
            ctx['total_chapters'] = chapters
            
            # Убираем клавиатуру
            remove_markup = telebot.types.ReplyKeyboardRemove()
            bot.send_message(
                user_id,
                f"✅ <b>Отлично!</b> Будет <b>{chapters}</b> глав.\n\nТеперь напиши <b>«глава 1»</b> чтобы начать первую <i>очень длинную</i> главу!",
                reply_markup=remove_markup,
                parse_mode='HTML'
            )
        else:
            bot.send_message(user_id, "⚠️ Укажи число от 1 до 50", parse_mode='HTML')
    except:
        bot.send_message(user_id, "⚠️ Пожалуйста, укажи цифрой (например: 5)", parse_mode='HTML')

def write_chapter(user_id, chapter_num):
    """Пишет главу через Gemini"""
    ctx = user_contexts[user_id]
    
    # Статус сообщение
    status_msg = bot.send_message(
        user_id,
        f"✍️ <b>Пишу главу {chapter_num}/{ctx['total_chapters']}...</b>\n\nЭто займет 30-60 секунд\nGemini создает <i>очень длинный</i> текст...",
        parse_mode='HTML'
    )
    
    try:
        # Строим промпт
        prompt = build_gemini_prompt(ctx, chapter_num)
        
        # Отправляем запрос к Gemini
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.9,  # Креативность
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,  # Максимум для длинных текстов
            )
        )
        
        # Получаем текст
        chapter_text = response.text
        
        # Сохраняем в историю
        ctx['history'].append({
            'chapter': chapter_num,
            'request': prompt[:200] + '...',
            'response': chapter_text,
            'timestamp': datetime.now().isoformat(),
            'word_count': len(chapter_text.split())
        })
        
        # Создаем файлы
        title = ctx['story_title'] or f"Глава_{chapter_num}"
        
        # 1. TXT файл
        txt_content = f"{title}\nГлава {chapter_num}\n\n{chapter_text}\n\nСоздано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        # 2. HTML файл
        html_content = generate_html_chapter(chapter_num, title, chapter_text)
        
        # Отправляем пользователю
        # Сначала TXT
        with io.BytesIO(txt_content.encode('utf-8')) as txt_file:
            txt_file.name = f"{title}_Глава_{chapter_num}.txt"
            caption = f"📖 <b>{title}</b>\nГлава {chapter_num}/{ctx['total_chapters']}\n\n"
            
            if chapter_num < ctx['total_chapters']:
                caption += f"Для следующей главы напиши <b>«глава {chapter_num + 1}»</b>"
            else:
                caption += "🎉 <b>История завершена!</b>\n/new - начать новую"
            
            bot.send_document(user_id, txt_file, caption=caption, parse_mode='HTML')
        
        # Затем HTML
        with io.BytesIO(html_content.encode('utf-8')) as html_file:
            html_file.name = f"{title}_Глава_{chapter_num}.html"
            bot.send_document(user_id, html_file, caption="🎨 HTML версия (открой в браузере)")
        
        # Удаляем статус
        bot.delete_message(user_id, status_msg.message_id)
        
        # Статистика
        word_count = len(chapter_text.split())
        bot.send_message(
            user_id,
            f"✅ <b>Глава {chapter_num} готова!</b>\n\n📊 Статистика:\n├ Слов: {word_count:,}\n├ Символов: {len(chapter_text):,}\n└ {'Последняя глава!' if chapter_num == ctx['total_chapters'] else f'Следующая: глава {chapter_num + 1}'}",
            parse_mode='HTML'
        )
        
    except Exception as e:
        error_msg = f"❌ <b>Ошибка Gemini:</b>\n\n{str(e)}\n\nПопробуй еще раз или проверь API ключ."
        bot.edit_message_text(error_msg, user_id, status_msg.message_id, parse_mode='HTML')

# Flask сервер для Render
@app.route('/')
def home():
    active_users = len([uid for uid, ctx in user_contexts.items() if ctx['current_chapter'] > 0])
    return f"""
    <h1>Фанфик-Бот с Gemini 1.5 Flash</h1>
    <p>Активных пользователей: {len(user_contexts)}</p>
    <p>Пишущих истории: {active_users}</p>
    <p>Запущен: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
    """

@app.route('/ping')
def ping():
    return "pong"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Запуск
if __name__ == "__main__":
    print("=== Фанфик-бот с Gemini запускается ===")
    print(f"Модель: gemini-1.5-flash")
    print(f"API ключ: {'Установлен' if GEMINI_API_KEY and 'YOUR' not in GEMINI_API_KEY else 'НЕ НАСТРОЕН!'}")
    
    # Запускаем Flask в фоне
    Thread(target=run_flask, daemon=True).start()
    
    # Запускаем бота
    print("=== Бот запущен ===")
    bot.infinity_polling()
