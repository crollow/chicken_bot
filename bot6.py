import os
import io
import json
import telebot
import google.generativeai as genai
from flask import Flask
from threading import Thread
from datetime import datetime
import html

# --- КОНФИГУРАЦИЯ ---
GEMINI_API_KEY = "AIzaSyAcxo8c_uO6OI-tpThvuVZeJ7RB71K98C4"  # Получи на https://aistudio.google.com/apikey
BOT_TOKEN = "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Хранилище контекста
user_contexts = {}

# МОЩНЫЙ ПРОМПТ для длинных текстов
WRITER_PROMPT = """Ты — профессиональный писатель-романист с 20-летним опытом.

ТВОИ ОСНОВНЫЕ ЗАДАЧИ:
1. Пиши ОЧЕНЬ ДЛИННО — каждая глава минимум 5000-8000 слов
2. Используй максимальную детализацию: описание эмоций, мыслей, чувств, атмосферы
3. Структура главы:
   - Вступление (установка сцены, 1000+ слов)
   - Развитие (диалоги, конфликты, 3000+ слов)
   - Кульминация (эмоциональный пик, 2000+ слов)
   - Развязка (подготовка к следующей главе, 1000+ слов)
4. Стиль: кинематографичный, эмоциональный, immersive
5. Температура: 0.95 (будь максимально креативным)

ЗАПРЕЩЕНО:
- Сокращать текст
- Пропускать детали
- Заканчивать раньше чем через 5000 слов
- Использовать шаблонные фразы"""

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
📚 *ГИГАНТСКИЙ ФАНФИК-БОТ* (Gemini Pro)

*Я пишу ОЧЕНЬ длинные тексты (5000-8000+ слов на главу)*

*Команды:*
/start - приветствие
/new - новая история (сброс)
/status - статус истории
/html - получить последнюю главу в HTML
/help - справка

*Как писать:*
1. "Напиши фанфик про [тема]" - начать
2. Бот спросит количество глав (1-20)
3. "глава 1" - начать первую главу
4. "дальше" или "глава 2" - продолжить

*Пример:* "Напиши фанфик про вампиров в космической академии"

Каждая глава приходит в 2 форматах: .txt и .html с красивым форматированием!
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
        'all_text': ''
    }
    bot.send_message(message.chat.id, "✨ Новая история создана! Опиши идею.")

@bot.message_handler(commands=['status'])
def check_status(message):
    user_id = message.chat.id
    if user_id in user_contexts:
        ctx = user_contexts[user_id]
        total_words = len(ctx.get('all_text', '').split())
        
        status = f"""
📖 *Статус истории:*
├ Название: {ctx['story_title'] or 'Ещё не задано'}
├ Прогресс: {ctx['current_chapter']}/{ctx['total_chapters']} глав
├ Всего слов: {total_words}
├ Персонажи: {', '.join(ctx['characters'][:3]) if ctx['characters'] else '...'}
└ Тема: {ctx['plot_summary'][:80]}...
        """
        bot.send_message(message.chat.id, status, parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "📭 Нет активной истории. /new - начать")

@bot.message_handler(commands=['html'])
def send_last_html(message):
    user_id = message.chat.id
    if user_id in user_contexts and user_contexts[user_id]['history']:
        last_chapter = user_contexts[user_id]['history'][-1]
        html_content = create_html_chapter(
            last_chapter['response'],
            user_contexts[user_id],
            last_chapter['chapter']
        )
        
        with io.BytesIO(html_content.encode('utf-8')) as f:
            f.name = f"Глава_{last_chapter['chapter']}.html"
            bot.send_document(user_id, f, caption="📄 HTML-версия последней главы")
    else:
        bot.send_message(user_id, "Нет написанных глав")

def initialize_user(user_id):
    if user_id not in user_contexts:
        user_contexts[user_id] = {
            'story_title': None,
            'current_chapter': 0,
            'total_chapters': 0,
            'plot_summary': '',
            'characters': [],
            'history': [],
            'all_text': ''
        }
    return user_contexts[user_id]

def create_html_chapter(text, ctx, chapter_num):
    """Создает красивый HTML из главы"""
    # Экранируем HTML символы
    safe_text = html.escape(text)
    
    # Разбиваем на абзацы
    paragraphs = safe_text.split('\n\n')
    formatted_paragraphs = []
    
    for para in paragraphs:
        if para.strip():
            # Выделяем диалоги (строки в кавычках)
            if ('"' in para or '—' in para or '«' in para) and len(para) < 200:
                formatted_paragraphs.append(f'<p class="dialogue">{para}</p>')
            else:
                formatted_paragraphs.append(f'<p>{para}</p>')
    
    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Глава {chapter_num}: {ctx['story_title']}</title>
    <style>
        body {{
            font-family: 'Georgia', serif;
            line-height: 1.8;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px;
            background: #f5f5f0;
            color: #333;
        }}
        .header {{
            text-align: center;
            border-bottom: 3px double #8b4513;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }}
        .chapter-title {{
            font-size: 2.5em;
            color: #8b4513;
            font-variant: small-caps;
            letter-spacing: 2px;
        }}
        .story-title {{
            font-size: 1.2em;
            color: #666;
            font-style: italic;
        }}
        p {{
            text-align: justify;
            margin: 1.5em 0;
            text-indent: 2em;
            font-size: 1.1em;
        }}
        .dialogue {{
            margin-left: 4em;
            font-style: italic;
            color: #2f4f4f;
            text-indent: 0;
        }}
        .first-letter::first-letter {{
            font-size: 3em;
            float: left;
            line-height: 1;
            margin-right: 10px;
            color: #8b4513;
            font-weight: bold;
        }}
        .word-count {{
            text-align: right;
            font-size: 0.9em;
            color: #888;
            margin-top: 40px;
            border-top: 1px solid #ddd;
            padding-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="chapter-title">Глава {chapter_num}</div>
        <div class="story-title">{html.escape(ctx['story_title'] or 'Фанфик')}</div>
    </div>
    
    <div class="content">
        <p class="first-letter">{formatted_paragraphs[0] if formatted_paragraphs else ''}</p>
        {"".join(formatted_paragraphs[1:])}
    </div>
    
    <div class="word-count">
        Слов: {len(text.split())} | Символов: {len(text)}
    </div>
</body>
</html>"""
    
    return html_content

def generate_long_chapter(prompt, history, chapter_num, total_chapters):
    """Генерирует ОЧЕНЬ длинную главу через Gemini"""
    
    # Строим системный промпт с историей
    system_prompt = f"""{WRITER_PROMPT}

КОНТЕКСТ ИСТОРИИ:
Тема: {history.get('plot_summary', 'не задано')}
Персонажи: {', '.join(history.get('characters', []))}
Глава {chapter_num} из {total_chapters}

ПРЕДЫДУЩИЙ КОНТЕКСТ (последние 2 главы):
{history.get('last_chapters_preview', '')}

ТВОЯ ЗАДАЧА:
Напиши главу {chapter_num}. Она должна быть САМОЙ ДЛИННОЙ из возможных.
Минимум 5000 слов, в идеале 8000+ слов.
Используй максимальную детализацию каждого момента.

ПРОМПТ ПОЛЬЗОВАТЕЛЯ: {prompt}

НАЧИНАЙ ПИСАТЬ СЕЙЧАС:"""
    
    try:
        # Первый запрос - основа главы
        response = model.generate_content(
            system_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.95,
                top_p=0.95,
                top_k=50,
                max_output_tokens=4000  # Максимум для Gemini
            )
        )
        
        chapter_text = response.text
        
        # Если текст короткий, делаем дополнительный запрос для продолжения
        if len(chapter_text.split()) < 3000:
            continuation_prompt = f"""
ПРОДОЛЖИ ЭТУ ГЛАВУ. Ты написал только {len(chapter_text.split())} слов, а нужно минимум 5000.

Текст пока:
{chapter_text[:2000]}...

ДОПИШИ ОЧЕНЬ ПОДРОБНО:
1. Добавь диалоги между персонажами (минимум 3 длинных диалога)
2. Опиши детально окружение: запахи, звуки, текстуры, свет
3. Добавь внутренние монологи персонажей
4. Создай дополнительный конфликт или поворот сюжета
5. Растяни каждую сцену в 2-3 раза подробнее

ПРОДОЛЖЕНИЕ:"""
            
            continuation = model.generate_content(continuation_prompt)
            chapter_text += "\n\n" + continuation.text
        
        return chapter_text
        
    except Exception as e:
        return f"Ошибка генерации: {str(e)}\n\nПопробуй еще раз или измени промпт."

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.chat.id
    text = message.text.strip()
    
    if 'напиши фанфик' in text.lower() or 'хочу фанфик' in text.lower():
        theme = text.replace('напиши фанфик', '').replace('хочу фанфик', '').strip()
        if not theme:
            bot.send_message(user_id, "📝 О какой теме фанфик? Например: 'про вампиров в школе'")
            return
        
        ctx = initialize_user(user_id)
        ctx['plot_summary'] = theme
        ctx['story_title'] = f"Фанфик: {theme[:30]}..."
        
        markup = telebot.types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True)
        buttons = ['1', '3', '5', '7', '10', '15', '20']
        for btn in buttons:
            markup.add(btn)
        
        msg = bot.send_message(
            user_id,
            f"🎬 Тема: '{theme}'\nСколько глав будет? (1-20)\n\nЧем больше глав — тем эпичнее сага!",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, ask_chapters)
    
    elif 'глава' in text.lower() or 'дальше' in text.lower() or 'следующ' in text.lower():
        ctx = initialize_user(user_id)
        
        if ctx['total_chapters'] == 0:
            bot.send_message(user_id, "Сначала задай количество глав. Напиши 'напиши фанфик про...'")
            return
        
        # Определяем номер главы
        chapter_num = 1
        if 'глава' in text.lower():
            words = text.lower().split()
            for word in words:
                if word.isdigit():
                    chapter_num = int(word)
                    break
            else:
                chapter_num = ctx['current_chapter'] + 1
        else:
            chapter_num = ctx['current_chapter'] + 1
        
        if chapter_num > ctx['total_chapters']:
            bot.send_message(user_id, f"🎉 История завершена! Написано {ctx['total_chapters']} глав.\n/new - новая история")
            return
        
        if chapter_num <= ctx['current_chapter']:
            bot.send_message(user_id, f"Эта глава уже написана. Следующая: {ctx['current_chapter'] + 1}")
            return
        
        # ПИШЕМ ГЛАВУ
        ctx['current_chapter'] = chapter_num
        write_chapter(message, chapter_num)
    
    else:
        bot.send_message(user_id, "📝 Чтобы начать: 'Напиши фанфик про [тема]'\n\nИли команды:\n/new - новая история\n/status - статус\n/html - получить HTML")

def ask_chapters(message):
    user_id = message.chat.id
    try:
        chapters = int(message.text)
        if 1 <= chapters <= 20:
            ctx = user_contexts[user_id]
            ctx['total_chapters'] = chapters
            
            remove_markup = telebot.types.ReplyKeyboardRemove()
            bot.send_message(
                user_id,
                f"🔥 Отлично! Будет {chapters} глав!\n\nКаждая глава будет ОЧЕНЬ длинной (5000-8000+ слов).\n\nНапиши 'глава 1' чтобы начать эпическую сагу!",
                reply_markup=remove_markup
            )
        else:
            bot.send_message(user_id, "Укажи число от 1 до 20")
    except:
        bot.send_message(user_id, "Напиши цифрой: 1, 3, 5, 7, 10...")

def write_chapter(message, chapter_num):
    user_id = message.chat.id
    ctx = user_contexts[user_id]
    
    # Статус
    status_msg = bot.send_message(
        user_id,
        f"✍️ *Пишу ГЛАВУ {chapter_num}/{ctx['total_chapters']}*\n\n"
        f"⏳ Это займет 30-60 секунд\n"
        f"📝 Цель: 5000-8000+ слов\n"
        f"🎯 Тема: {ctx['plot_summary'][:50]}...",
        parse_mode='Markdown'
    )
    
    # Готовим промпт
    prompt = f"Напиши подробнейшую главу {chapter_num} на тему: {ctx['plot_summary']}"
    
    # Добавляем контекст предыдущих глав
    if ctx['history']:
        last_chapters = ctx['history'][-2:]  # Последние 2 главы
        context_preview = "\n\n".join([
            f"Глава {h['chapter']} (фрагмент): {h['response'][:500]}..." 
            for h in last_chapters
        ])
        ctx['last_chapters_preview'] = context_preview
    
    # Генерация
    try:
        chapter_text = generate_long_chapter(prompt, ctx, chapter_num, ctx['total_chapters'])
        
        # Сохраняем
        ctx['history'].append({
            'request': prompt,
            'response': chapter_text,
            'chapter': chapter_num,
            'timestamp': datetime.now().isoformat(),
            'word_count': len(chapter_text.split())
        })
        
        ctx['all_text'] += "\n\n" + chapter_text
        
        # Отправляем TXT
        word_count = len(chapter_text.split())
        with io.BytesIO(chapter_text.encode('utf-8')) as txt_file:
            txt_file.name = f"Глава_{chapter_num}_{ctx['story_title'].replace(' ', '_')}.txt"
            caption_txt = f"📖 *Глава {chapter_num}: {ctx['story_title']}*\n\n"
            caption_txt += f"📊 Статистика:\n"
            caption_txt += f"• Слов: {word_count}\n"
            caption_txt += f"• Символов: {len(chapter_text)}\n"
            caption_txt += f"• Глав: {chapter_num}/{ctx['total_chapters']}\n\n"
            
            if chapter_num < ctx['total_chapters']:
                caption_txt += f"Для следующей главы напиши 'глава {chapter_num + 1}'"
            else:
                caption_txt += f"🎉 *ИСТОРИЯ ЗАВЕРШЕНА!*\n/new - начать новую"
            
            bot.send_document(user_id, txt_file, caption=caption_txt, parse_mode='Markdown')
        
        # Отправляем HTML
        html_content = create_html_chapter(chapter_text, ctx, chapter_num)
        with io.BytesIO(html_content.encode('utf-8')) as html_file:
            html_file.name = f"Глава_{chapter_num}_Красивый.html"
            bot.send_document(
                user_id, 
                html_file, 
                caption=f"🎨 HTML-версия главы {chapter_num} (открой в браузере)"
            )
        
        bot.delete_message(user_id, status_msg.message_id)
        
        # Автоматически добавляем персонажей из текста
        if not ctx['characters'] and chapter_num == 1:
            extract_characters(user_id, chapter_text)
            
    except Exception as e:
        bot.edit_message_text(
            f"❌ Ошибка при генерации:\n```{str(e)[:300]}```",
            user_id,
            status_msg.message_id,
            parse_mode='Markdown'
        )

def extract_characters(user_id, text):
    """Извлекает имена персонажей из текста"""
    try:
        prompt = f"Извлеки имена персонажей из текста, верни только через запятую:\n\n{text[:1000]}"
        response = model.generate_content(prompt)
        
        if response.text:
            characters = [c.strip() for c in response.text.split(',') if len(c.strip()) > 2]
            if characters:
                user_contexts[user_id]['characters'] = characters[:5]  # максимум 5 персонажей
    except:
        pass

# Flask сервер для Render
@app.route('/')
def home():
    return f"📚 Фанфик-бот (Gemini) работает! Пользователей: {len(user_contexts)}"

@app.route('/ping')
def ping():
    return "pong"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    print("=== Запуск Gemini Фанфик-Бота ===")
    print(f"API ключ: {'Установлен' if GEMINI_API_KEY and 'AIza' in GEMINI_API_KEY else 'ОШИБКА!'}")
    
    # Запускаем Flask в фоне
    Thread(target=run_flask, daemon=True).start()
    
    # Запускаем бота
    print("=== Бот запущен ===")
    bot.infinity_polling()
