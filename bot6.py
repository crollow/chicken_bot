import os
import io
import telebot
import google.generativeai as genai
from flask import Flask
from threading import Thread
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
GEMINI_API_KEY = "AIzaSyAcxo8c_uO6OI-tpThvuVZeJ7RB71K98C4"  # Твой Gemini API ключ
BOT_TOKEN = "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4"  # Твой токен бота

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')
genai.configure(api_key=GEMINI_API_KEY)

# Хранилище контекста
user_contexts = {}

# МЕГА-ПРОМПТ ДЛЯ ОЧЕНЬ ДЛИННЫХ ТЕКСТОВ
WRITER_SYSTEM_PROMPT = """ТЫ — ПРОФЕССИОНАЛЬНЫЙ ПИСАТЕЛЬ-ФАНФИКЕР С 25-ЛЕТНИМ ОПЫТОМ.
but
ТВОИ ГЛАВНЫЕ ПРАВИЛА:
1. ОБЪЕМ: КАЖДАЯ ГЛАВА МИНИМУМ 5000-7000 СЛОВ. НИКОГДА НЕ СОКРАЩАЙ!
2. ДЕТАЛИЗАЦИЯ МАКСИМАЛЬНАЯ:
   • Каждую локацию описывай 10-15 предложениями
   • Каждого персонажа описывай внешность + характер + история
   • Каждую эмоцию расписывай через физические ощущения
   • Каждый диалог — минимум 20 реплик с уникальными речевыми оборотами
3. СТРУКТУРА:
   Начало (500 слов) → Развитие (3000 слов) → Кульминация (1500 слов) → Интрига (500 слов)
4. СТИЛЬ: Кинематографичный, погружающий, сенсорный.
5. ФОРМАТ: ТОЛЬКО СПЛОШНОЙ ТЕКСТ.

СЕЙЧАС: Глава {chapter_num} из {total_chapters}
ТЕМА: {theme}
ПРЕДЫДУЩЕЕ: {previous_context}

НАЧИНАЙ ПИСАТЬ СЕЙЧАС:"""

def initialize_user(user_id):
    if user_id not in user_contexts:
        user_contexts[user_id] = {
            'theme': '',
            'current_chapter': 0,
            'total_chapters': 0,
            'history': [],
            'created_at': datetime.now().isoformat()
        }
    return user_contexts[user_id]

def generate_html_content(text, title, chapter_num):
    """Создает красивый HTML файл с подсчетом статистики"""
    word_count = len(text.split())
    char_count = len(text)
    
    # Разбиваем текст на абзацы для HTML
    paragraphs = text.split('\n\n')
    html_paragraphs = ''.join([f'<p>{p.replace(chr(10), "<br>")}</p>' for p in paragraphs if p.strip()])
    
    html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Глава {chapter_num}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            line-height: 1.9;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #2d3436;
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .book-container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 60px 50px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            position: relative;
            border: 1px solid #e0e0e0;
        }}
        .book-container::before {{
            content: '';
            position: absolute;
            top: 10px;
            left: 10px;
            right: 10px;
            bottom: 10px;
            border: 2px solid #764ba2;
            border-radius: 15px;
            pointer-events: none;
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            font-size: 2.8em;
            margin-bottom: 10px;
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }}
        .chapter-info {{
            text-align: center;
            color: #7f8c8d;
            font-size: 1.2em;
            margin-bottom: 50px;
            font-style: italic;
            border-bottom: 2px dashed #3498db;
            padding-bottom: 20px;
        }}
        .content {{
            font-size: 1.15em;
            text-align: justify;
        }}
        .content p {{
            margin-bottom: 35px;
            text-indent: 40px;
            position: relative;
        }}
        .content p:first-of-type:first-letter {{
            font-size: 4.5em;
            float: left;
            line-height: 0.8;
            margin: 15px 15px 5px 0;
            color: #e74c3c;
            font-weight: bold;
            font-family: 'Georgia', serif;
        }}
        .stats {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            margin: 50px 0;
            display: flex;
            justify-content: space-around;
            font-size: 1.1em;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        .stat-item {{ text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; }}
        .stat-label {{ font-size: 0.9em; opacity: 0.9; }}
        .footer {{
            margin-top: 60px;
            padding-top: 30px;
            border-top: 3px solid #3498db;
            text-align: center;
            color: #636e72;
            font-size: 0.95em;
        }}
        .bot-info {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 10px;
            display: inline-block;
            margin-top: 20px;
            font-weight: bold;
        }}
        @media print {{
            body {{ background: white !important; }}
            .book-container {{ box-shadow: none; border: 1px solid #ccc; }}
            .stats {{ background: #f8f9fa !important; color: black; }}
        }}
    </style>
</head>
<body>
    <div class="book-container">
        <h1>{title}</h1>
        <div class="chapter-info">
            📖 Глава {chapter_num} • 📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}
        </div>
        
        <div class="content">
            {html_paragraphs}
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-value">{word_count}</div>
                <div class="stat-label">СЛОВ</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{char_count}</div>
                <div class="stat-label">СИМВОЛОВ</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{chapter_num}</div>
                <div class="stat-label">ГЛАВА</div>
            </div>
        </div>
        
        <div class="footer">
            <div class="bot-info">
                ✨ Создано Фанфик-Ботом с Gemini 2.5 Flash ✨
            </div>
            <p style="margin-top: 15px;">
                Бот: @{bot.get_me().username if hasattr(bot, 'get_me') else 'fanfic_writer_bot'}<br>
                Формат: HTML + TXT
            </p>
        </div>
    </div>
</body>
</html>"""
    return html_template

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
🔥 *ФАНФИК-БОТ НА GEMINI 2.5 FLASH*

📊 *ВОЗМОЖНОСТИ:*
• Пишет СУПЕР-ДЛИННЫЕ главы (5000-7000+ слов)
• Сохраняет контекст и персонажей
• Отправляет в 2-х форматах:
  📄 HTML — красивый вид для чтения
  📝 TXT — чистый текст для редактирования

🚀 *КОМАНДЫ:*
/new — начать новую историю
/status — прогресс текущей истории
/continue — продолжить писать
/help — эта справка

✍️ *КАК ПИСАТЬ:*
1. "Напиши фанфик про [любая тема]"
2. Укажи количество глав (1-15)
3. "глава 1", "дальше", "следующая" — для новых глав

💎 *ПРИМЕР:*
"Напиши фанфик про киберпанк-детектива в Токио 2077"
"""
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['new'])
def new_story(message):
    user_id = message.chat.id
    user_contexts[user_id] = {
        'theme': '',
        'current_chapter': 0,
        'total_chapters': 0,
        'history': [],
        'created_at': datetime.now().isoformat()
    }
    bot.send_message(message.chat.id, "✨ *НОВАЯ ИСТОРИЯ!*\n\nОпиши идею:\n\"Напиши фанфик про...\"", parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def check_status(message):
    user_id = message.chat.id
    if user_id in user_contexts and user_contexts[user_id]['theme']:
        ctx = user_contexts[user_id]
        total_words = sum(len(h.get('text', '').split()) for h in ctx['history'])
        
        status = f"""
📚 *СТАТУС ИСТОРИИ*

🎭 *Тема:* {ctx['theme']}
📖 *Прогресс:* {ctx['current_chapter']}/{ctx['total_chapters']} глав
📊 *Написано слов:* {total_words:,}
⏰ *Создана:* {datetime.fromisoformat(ctx['created_at']).strftime('%d.%m в %H:%M')}

🔄 Для продолжения: \"глава {ctx['current_chapter'] + 1}\" или \"дальше\"
"""
        bot.send_message(message.chat.id, status, parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "📭 *Нет активной истории!*\n\nНачни: \"Напиши фанфик про...\"", parse_mode='Markdown')

@bot.message_handler(commands=['continue'])
def continue_story(message):
    user_id = message.chat.id
    if user_id in user_contexts and user_contexts[user_id]['current_chapter'] > 0:
        ctx = user_contexts[user_id]
        if ctx['current_chapter'] < ctx['total_chapters']:
            bot.send_message(message.chat.id, f"🔄 *ПРОДОЛЖАЕМ!*\n\nСледующая глава: {ctx['current_chapter'] + 1}\n\nНапиши: \"глава {ctx['current_chapter'] + 1}\"", parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, "🎉 *ИСТОРИЯ ЗАВЕРШЕНА!*\n\nВсе главы написаны!\n\n/new — начать новую", parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "❌ *Нет незавершенной истории*\n\nНачни новую через /new", parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.chat.id
    user_message = message.text.strip()
    ctx = initialize_user(user_id)
    
    # Обработка новой истории
    if 'напиши фанфик' in user_message.lower():
        theme = user_message.lower().replace('напиши фанфик', '').replace('напиши фанфик про', '').replace('хочу фанфик про', '').strip()
        
        if not theme:
            bot.send_message(user_id, "❓ *Уточни тему!*\n\nПример: \"Напиши фанфик про вампиров в космосе\"", parse_mode='Markdown')
            return
        
        ctx['theme'] = theme
        ctx['current_chapter'] = 0
        
        # Создаем клавиатуру для выбора количества глав
        from telebot import types
        markup = types.ReplyKeyboardMarkup(row_width=5, resize_keyboard=True)
        buttons = [types.KeyboardButton(str(i)) for i in [1, 3, 5, 7, 10, 12, 15]]
        markup.add(*buttons)
        
        bot.send_message(
            user_id,
            f"🎬 *ОТЛИЧНАЯ ИДЕЯ!*\n\nТема: *{theme}*\n\n*Сколько глав будет в истории?* (1-15)",
            parse_mode='Markdown',
            reply_markup=markup
        )
    
    # Обработка выбора количества глав
    elif user_message.isdigit() and 1 <= int(user_message) <= 15 and ctx['theme'] and ctx['total_chapters'] == 0:
        chapters = int(user_message)
        ctx['total_chapters'] = chapters
        
        # Убираем клавиатуру
        from telebot import types
        remove_markup = types.ReplyKeyboardRemove()
        
        bot.send_message(
            user_id,
            f"✅ *ГОТОВО!*\n\n📚 *{chapters} глав* по *5000-7000 слов*\n\n🎭 *Тема:* {ctx['theme']}\n\n🚀 *Пиши:* \"глава 1\" чтобы начать!",
            parse_mode='Markdown',
            reply_markup=remove_markup
        )
    
    # Обработка запроса главы
    elif any(word in user_message.lower() for word in ['глава', 'дальше', 'следующая', 'продолжи', 'следующую']):
        if ctx['total_chapters'] == 0:
            bot.send_message(user_id, "⚠️ *Сначала укажи количество глав!*\n\nНапиши: \"Напиши фанфик про...\"", parse_mode='Markdown')
            return
        
        # Определяем номер главы
        chapter_num = ctx['current_chapter'] + 1
        
        if chapter_num > ctx['total_chapters']:
            bot.send_message(user_id, f"🎉 *ИСТОРИЯ ЗАВЕРШЕНА!*\n\nНаписаны все {ctx['total_chapters']} глав!\n\n/new — начать новую", parse_mode='Markdown')
            return
        
        # ПИШЕМ ГЛАВУ
        write_chapter(message, chapter_num)
    
    else:
        bot.send_message(user_id, "🤔 *Не понял...*\n\nЧтобы начать: \"Напиши фанфик про [тема]\"\n\nИли используй команды:\n/new — новая история\n/status — статус", parse_mode='Markdown')

def write_chapter(message, chapter_num):
    """Пишет ОЧЕНЬ длинную главу через Gemini 2.5 Flash"""
    user_id = message.chat.id
    ctx = user_contexts[user_id]
    
    # Обновляем номер текущей главы
    ctx['current_chapter'] = chapter_num
    
    # Статус-сообщение
    status_msg = bot.send_message(
        user_id,
        f"⚡ *GEMINI 2.5 FLASH В РАБОТЕ!*\n\n✍️ Пишу главу *{chapter_num}* из *{ctx['total_chapters']}*\n📊 Объем: *5000-7000 слов*\n⏱️ Время: *60-90 секунд*\n\nТема: *{ctx['theme']}*",
        parse_mode='Markdown'
    )
    
    try:
        # Готовим промпт
        previous_context = ""
        if ctx['history']:
            last_chapter = ctx['history'][-1]
            previous_context = f"Предыдущая глава ({last_chapter['chapter']}) закончилась: {last_chapter['text'][-500:]}..."
        
        prompt = WRITER_SYSTEM_PROMPT.format(
            chapter_num=chapter_num,
            total_chapters=ctx['total_chapters'],
            theme=ctx['theme'],
            previous_context=previous_context
        )
        
        # Запрос к Gemini 2.5 Flash с максимальными токенами
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.85,
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,  # Максимум для длинного текста
            )
        )
        
        if not response.text:
            bot.edit_message_text("❌ *Gemini не вернул текст!*", user_id, status_msg.message_id, parse_mode='Markdown')
            return
        
        chapter_text = response.text.strip()
        
        # Сохраняем в историю
        ctx['history'].append({
            'chapter': chapter_num,
            'text': chapter_text,
            'word_count': len(chapter_text.split()),
            'timestamp': datetime.now().isoformat()
        })
        
        # Создаем HTML
        title = f"Фанфик: {ctx['theme'][:50]}"
        html_content = generate_html_content(chapter_text, title, chapter_num)
        
        # Отправляем ОБА файла
        # 1. TXT файл
        with io.BytesIO(chapter_text.encode('utf-8')) as txt_file:
            txt_file.name = f"Глава_{chapter_num}_{title[:30]}.txt"
            
            # 2. HTML файл
            with io.BytesIO(html_content.encode('utf-8')) as html_file:
                html_file.name = f"Глава_{chapter_num}_{title[:30]}.html"
                
                caption = f"""
📚 *ГЛАВА {chapter_num} ГОТОВА!*

🎭 *Тема:* {ctx['theme']}
📊 *Прогресс:* {chapter_num}/{ctx['total_chapters']}
🔤 *Слов:* {len(chapter_text.split()):,}
🔡 *Символов:* {len(chapter_text):,}

💾 *2 файла:*
📄 HTML — красивый вид
📝 TXT — чистый текст
                """
                
                # Отправляем оба файла одним сообщением
                bot.send_media_group(user_id, [
                    telebot.types.InputMediaDocument(txt_file, caption=caption if chapter_num == ctx['total_chapters'] else None),
                    telebot.types.InputMediaDocument(html_file)
                ])
        
        # Дополнительное сообщение если не последняя глава
        if chapter_num < ctx['total_chapters']:
            bot.send_message(
                user_id,
                f"🔄 *СЛЕДУЮЩАЯ ГЛАВА ГОТОВА К НАПИСАНИЮ!*\n\nНапиши: \"глава {chapter_num + 1}\" или \"дальше\"\n\nВсего глав осталось: {ctx['total_chapters'] - chapter_num}",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(
                user_id,
                f"🎉 *ИСТОРИЯ ЗАВЕРШЕНА!*\n\n✅ Все {ctx['total_chapters']} глав написаны!\n📚 Общий объем: {sum(h['word_count'] for h in ctx['history']):,} слов\n\n/new — начать новую историю",
                parse_mode='Markdown'
            )
        
        # Удаляем статус
        bot.delete_message(user_id, status_msg.message_id)
        
    except Exception as e:
        error_msg = str(e)
        bot.edit_message_text(
            f"❌ *ОШИБКА GEMINI!*\n\n{error_msg[:100]}\n\nПопробуй снова: \"глава {chapter_num}\"",
            user_id,
            status_msg.message_id,
            parse_mode='Markdown'
        )

# Flask для веб-сервера
@app.route('/')
def home():
    return f"Фанфик-бот на Gemini 2.5 Flash работает! Пользователей: {len(user_contexts)}"

@app.route('/ping')
def ping():
    return "pong"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Запуск
if __name__ == "__main__":
    print("🚀 Фанфик-бот на Gemini 2.5 Flash запускается...")
    print(f"🔑 API ключ: {'Установлен' if GEMINI_API_KEY and len(GEMINI_API_KEY) > 10 else 'НЕ НАСТРОЕН!'}")
    print(f"🤖 Токен бота: {'Установлен' if BOT_TOKEN and len(BOT_TOKEN) > 10 else 'НЕ НАСТРОЕН!'}")
    
    # Запускаем Flask в отдельном потоке
    Thread(target=run_flask, daemon=True).start()
    
    # Запускаем бота
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")
