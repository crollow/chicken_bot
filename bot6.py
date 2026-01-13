import asyncio
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict
from openai import OpenAI
from aiohttp import web
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ========== КОНФИГУРАЦИЯ ==========
GROQ_API_KEY = "gsk_твой_ключ_сюда"  # Получи на platform.groq.com
BOT_TOKEN = "токен_твоего_бота"      # От @BotFather

# Модель Groq (используй llama-3.3-70b-versatile или mixtral-8x7b)
GROQ_MODEL = "llama-3.3-70b-versatile"

# ========== НАСТРОЙКА ЛОГГИНГА ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Инициализация клиента Groq (через OpenAI совместимый API)
groq_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

# ========== ХРАНИЛИЩЕ ДАННЫХ ==========
# Структура для хранения контекста пользователей
class UserStory:
    def __init__(self):
        self.theme: str = ""
        self.characters: str = ""
        self.total_chapters: int = 0
        self.current_chapter: int = 0
        self.messages: List[Dict] = []
        self.created_at: datetime = datetime.now()

user_stories: Dict[int, UserStory] = defaultdict(UserStory)

# ========== FSM (Finite State Machine) СОСТОЯНИЯ ==========
class StoryStates(StatesGroup):
    waiting_theme = State()
    waiting_characters = State()
    waiting_chapters = State()

# ========== СИСТЕМНЫЙ ПРОМПТ ==========
SYSTEM_PROMPT = """Ты — талантливый профессиональный писатель с многолетним опытом. Твоя задача — писать ОЧЕНЬ длинные, детальные и художественные фанфики.

ТВОИ ПРАВИЛА НАПИСАНИЯ:
1. ДЛИНА: Каждая глава должна быть НЕ МЕНЕЕ 1500 слов. Пиши максимально подробно!
2. ДЕТАЛИ: Используй богатые описания: чувства персонажей, атмосфера, запахи, звуки, текстуры, внутренние монологи.
3. ДИАЛОГИ: Включай реалистичные диалоги, которые раскрывают персонажей.
4. СТРУКТУРА: Каждая глава должна иметь: завязку, развитие, кульминацию и интригующий финал.
5. СТИЛЬ: Избегай клише, будь оригинальным. Используй литературные приемы: метафоры, сравнения, символизм.
6. ЭМОЦИИ: Передавай эмоции через действия и мысли, а не просто называй их.

ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ:
- Формат: художественная проза
- Язык: современный русский литературный
- Тон: соответствующий жанру
- В каждой главе развивай сюжет и персонажей"""

# ========== ВЕБ-СЕРВЕР ДЛЯ PING ==========
async def handle_healthcheck(request):
    """Обработчик для проверки работоспособности"""
    return web.Response(text="Bot is alive! Users: {}".format(len(user_stories)))

async def start_web_server():
    """Запуск веб-сервера на aiohttp"""
    app = web.Application()
    app.router.add_get('/', handle_healthcheck)
    app.router.add_get('/health', handle_healthcheck)
    
    # Получаем порт из переменной окружения (для Render)
    port = int(os.environ.get("PORT", 8080))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"Web server started on port {port}")
    return runner

# ========== КОМАНДЫ БОТА ==========
@router.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start - приветствие"""
    welcome_text = """
📚 *Добро пожаловать в Фанфик-Писатель 2.0!* 📚

Я — профессиональный автор, который поможет тебе создать эпичную историю!

*Как работать со мной:*

1️⃣ *Начать новую историю:*
   Напиши "напиши фанфик" или /new

2️⃣ *Процесс создания:*
   • Я спрошу тему (о чем история)
   • Персонажей (кто главные герои)
   • Количество глав

3️⃣ *Генерация:*
   • Я пишу ОЧЕНЬ длинные главы (1500+ слов)
   • Каждую главу присылаю отдельным файлом
   • После главы — кнопка для продолжения

4️⃣ *Команды:*
   /start - это сообщение
   /new - начать новую историю
   /reset - забыть текущую историю
   /status - узнать прогресс
   /continue - продолжить последнюю историю

*Пример:* напиши "напиши фанфик" и следуй инструкциям!
    """
    
    await message.answer(welcome_text, parse_mode="Markdown")
    logger.info(f"User {message.from_user.id} started the bot")

@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    """Команда /reset - сброс контекста"""
    user_id = message.from_user.id
    
    # Очищаем историю пользователя
    if user_id in user_stories:
        del user_stories[user_id]
    
    # Сбрасываем состояние FSM
    await state.clear()
    
    await message.answer("✅ Контекст полностью очищен! Я забыл все о предыдущей истории.")
    logger.info(f"User {message.from_user.id} reset their story")

@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext):
    """Команда /new - начать новую историю"""
    await state.set_state(StoryStates.waiting_theme)
    await message.answer(
        "🎬 Отлично! Начинаем новую историю!\n\n"
        "*Шаг 1 из 3:* Опиши тему фанфика.\n"
        "Например: 'романтика между вампиром и ведьмой в современном городе' или "
        "'детектив в школе магии, где ученики исчезают'",
        parse_mode="Markdown"
    )
    logger.info(f"User {message.from_user.id} started new story")

@router.message(Command("status"))
async def cmd_status(message: Message):
    """Команда /status - статус текущей истории"""
    user_id = message.from_user.id
    story = user_stories.get(user_id)
    
    if not story or story.current_chapter == 0:
        await message.answer("📭 У тебя нет активной истории. Начни новую через /new")
        return
    
    status_text = f"""
📖 *Текущая история:*

*Тема:* {story.theme[:100]}...
*Персонажи:* {story.characters[:100]}...
*Прогресс:* Глава {story.current_chapter} из {story.total_chapters}
*Начата:* {story.created_at.strftime('%d.%m.%Y %H:%M')}

Для продолжения нажми кнопку "Следующая глава" или напиши "дальше".
"""
    await message.answer(status_text, parse_mode="Markdown")

@router.message(F.text.lower().contains("напиши фанфик"))
async def start_story_creation(message: Message, state: FSMContext):
    """Обработчик фразы 'напиши фанфик'"""
    await cmd_new(message, state)

# ========== FSM ОБРАБОТЧИКИ ==========
@router.message(StoryStates.waiting_theme)
async def process_theme(message: Message, state: FSMContext):
    """Обработка темы истории"""
    user_id = message.from_user.id
    
    # Сохраняем тему
    user_stories[user_id].theme = message.text
    
    # Переходим к следующему шагу
    await state.set_state(StoryStates.waiting_characters)
    await message.answer(
        "✅ Тема сохранена!\n\n"
        "*Шаг 2 из 3:* Опиши главных персонажей.\n"
        "Например: 'Лина — юная ведьма с тайной силой, Маркус — вампир-одиночка с темным прошлым'",
        parse_mode="Markdown"
    )
    logger.info(f"User {user_id} set theme: {message.text[:50]}")

@router.message(StoryStates.waiting_characters)
async def process_characters(message: Message, state: FSMContext):
    """Обработка персонажей"""
    user_id = message.from_user.id
    
    # Сохраняем персонажей
    user_stories[user_id].characters = message.text
    
    # Переходим к выбору количества глав
    await state.set_state(StoryStates.waiting_chapters)
    
    # Создаем клавиатуру для выбора количества глав
    builder = InlineKeyboardBuilder()
    chapters_options = [1, 3, 5, 7, 10, 15]
    for num in chapters_options:
        builder.button(text=f"{num} глав", callback_data=f"chapters_{num}")
    builder.adjust(3, 2)  # 3 кнопки в первом ряду, 2 во втором
    
    await message.answer(
        "✅ Персонажи сохранены!\n\n"
        "*Шаг 3 из 3:* Сколько глав будет в истории?\n"
        "Выбери количество или напиши свою цифру (от 1 до 20):",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    logger.info(f"User {user_id} set characters: {message.text[:50]}")

@router.message(StoryStates.waiting_chapters)
async def process_chapters_text(message: Message, state: FSMContext):
    """Обработка текстового ввода количества глав"""
    user_id = message.from_user.id
    
    try:
        chapters = int(message.text)
        if 1 <= chapters <= 20:
            await save_chapters(user_id, chapters, message, state)
        else:
            await message.answer("Пожалуйста, введите число от 1 до 20")
    except ValueError:
        await message.answer("Пожалуйста, введите число (например: 5)")

@router.callback_query(F.data.startswith("chapters_"))
async def process_chapters_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора количества глав через кнопки"""
    user_id = callback.from_user.id
    
    chapters = int(callback.data.split("_")[1])
    await save_chapters(user_id, chapters, callback.message, state)
    await callback.answer()

async def save_chapters(user_id: int, chapters: int, message: Message, state: FSMContext):
    """Сохранение количества глав и запуск первой главы"""
    story = user_stories[user_id]
    story.total_chapters = chapters
    story.current_chapter = 0
    
    # Сбрасываем состояние FSM
    await state.clear()
    
    # Отправляем подтверждение
    confirmation = f"""
🎉 Отлично! Начинаем писать историю!

*Тема:* {story.theme}
*Персонажи:* {story.characters}
*Глав:* {story.total_chapters}

Сейчас напишу первую главу. Это займет 30-60 секунд...
    """
    
    await message.answer(confirmation, parse_mode="Markdown")
    logger.info(f"User {user_id} set {chapters} chapters")
    
    # Запускаем написание первой главы
    await write_chapter(user_id, message.chat.id)

# ========== ГЕНЕРАЦИЯ ГЛАВ ==========
async def write_chapter(user_id: int, chat_id: int):
    """Генерация одной главы через Groq API"""
    story = user_stories[user_id]
    story.current_chapter += 1
    
    # Статус сообщение
    status_msg = await bot.send_message(
        chat_id,
        f"✍️ Пишу главу {story.current_chapter}/{story.total_chapters}...\n"
        f"⏱️ Это займет 30-60 секунд",
    )
    
    # Формируем промпт для главы
    chapter_prompt = f"""
ТЕМА ИСТОРИИ: {story.theme}
ПЕРСОНАЖИ: {story.characters}

ЗАДАНИЕ: Напиши ГЛАВУ {story.current_chapter} из {story.total_chapters}.

ОСОБЫЕ УКАЗАНИЯ:
1. Эта глава должна быть САМОСТОЯТЕЛЬНОЙ, но при этом продолжать общий сюжет
2. Длина: НЕ МЕНЕЕ 1500 СЛОВ
3. Если это не первая глава, плавно продолжай с того места, где остановились
4. В конце главы создай интригу для следующей главы
5. Используй художественный, литературный стиль
"""
    
    # Если это не первая глава, добавляем контекст
    if story.current_chapter > 1 and story.messages:
        chapter_prompt += f"\nПРЕДЫДУЩИЙ КОНТЕКСТ: [продолжи историю с учетом предыдущих событий]"
    
    try:
        # Подготовка сообщений для API
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        
        # Добавляем историю сообщений (последние 3 обмена)
        for msg in story.messages[-6:]:  # Берем последние 3 пары вопрос-ответ
            messages.append(msg)
        
        # Добавляем текущий запрос
        messages.append({"role": "user", "content": chapter_prompt})
        
        # Вызов Groq API
        logger.info(f"Calling Groq API for user {user_id}, chapter {story.current_chapter}")
        
        response = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.85,
            max_tokens=4000,  # Максимум для длинных текстов
            top_p=0.9,
        )
        
        # Получаем текст главы
        chapter_text = response.choices[0].message.content
        
        # Сохраняем в историю
        story.messages.append({"role": "user", "content": chapter_prompt})
        story.messages.append({"role": "assistant", "content": chapter_text})
        
        # Ограничиваем историю (чтобы не переполнять контекст)
        if len(story.messages) > 20:
            story.messages = story.messages[-20:]
        
        # Создаем HTML файл с главой
        html_content = create_html_chapter(story, chapter_text)
        
        # Отправляем файл пользователю
        await send_chapter_as_file(chat_id, story, chapter_text, html_content)
        
        # Удаляем статус сообщение
        await bot.delete_message(chat_id, status_msg.message_id)
        
        logger.info(f"Chapter {story.current_chapter} completed for user {user_id}")
        
        # Показываем кнопку для следующей главы (если есть еще главы)
        if story.current_chapter < story.total_chapters:
            await show_next_chapter_button(chat_id, story)
        else:
            await bot.send_message(
                chat_id,
                f"🎉 *История завершена!*\n\n"
                f"Написано {story.total_chapters} глав.\n"
                f"Чтобы начать новую историю, напиши /new",
                parse_mode="Markdown"
            )
    
    except Exception as e:
        logger.error(f"Error generating chapter for user {user_id}: {e}")
        error_msg = f"❌ Ошибка при генерации главы: {str(e)}"
        
        # Проверяем специфичные ошибки Groq
        if "429" in str(e):
            error_msg = "🔄 Слишком много запросов. Подожди 1 минуту и попробуй снова."
        elif "403" in str(e):
            error_msg = "🔑 Проблема с API ключом. Проверь настройки."
        elif "timeout" in str(e).lower():
            error_msg = "⏱️ Таймаут запроса. Попробуй еще раз."
        
        await bot.edit_message_text(
            error_msg,
            chat_id,
            status_msg.message_id
        )

def create_html_chapter(story: UserStory, chapter_text: str) -> str:
    """Создает HTML файл с главой"""
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Глава {story.current_chapter} - {story.theme[:50]}</title>
    <style>
        body {{
            font-family: 'Georgia', serif;
            line-height: 1.8;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #fefefe;
            color: #333;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }}
        .chapter-title {{
            font-size: 2.5em;
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .chapter-number {{
            font-size: 1.2em;
            color: #7f8c8d;
            font-style: italic;
        }}
        .meta {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            font-size: 0.9em;
        }}
        .content {{
            font-size: 1.1em;
            text-align: justify;
            white-space: pre-line;
        }}
        .content p {{
            margin-bottom: 1.5em;
            text-indent: 1.5em;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            text-align: center;
            font-size: 0.9em;
            color: #7f8c8d;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1 class="chapter-title">Глава {story.current_chapter}</h1>
        <div class="chapter-number">{story.current_chapter} из {story.total_chapters}</div>
    </div>
    
    <div class="meta">
        <strong>Тема:</strong> {story.theme}<br>
        <strong>Персонажи:</strong> {story.characters}<br>
        <strong>Сгенерировано:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}<br>
        <strong>Слов:</strong> {len(chapter_text.split())}
    </div>
    
    <div class="content">
        {chapter_text}
    </div>
    
    <div class="footer">
        Создано с помощью Фанфик-Писатель Bot • {datetime.now().year}
    </div>
</body>
</html>"""
    return html

async def send_chapter_as_file(chat_id: int, story: UserStory, chapter_text: str, html_content: str):
    """Отправляет главу как текстовый и HTML файл"""
    
    # Отправляем сначала текстовую версию (для быстрого чтения)
    await bot.send_message(
        chat_id,
        f"📖 *Глава {story.current_chapter} из {story.total_chapters}*\n\n"
        f"{chapter_text[:500]}...\n\n"
        f"📊 *Статистика:* {len(chapter_text.split())} слов",
        parse_mode="Markdown"
    )
    
    # Создаем и отправляем HTML файл
    html_bytes = html_content.encode('utf-8')
    html_file = io.BytesIO(html_bytes)
    html_file.name = f"Глава_{story.current_chapter}_{story.theme[:30]}.html"
    
    await bot.send_document(
        chat_id,
        document=FSInputFile(html_file, filename=html_file.name),
        caption=f"📄 HTML-версия главы {story.current_chapter}"
    )
    
    # Также отправляем текстовый файл
    text_file = io.BytesIO(chapter_text.encode('utf-8'))
    text_file.name = f"Глава_{story.current_chapter}_текст.txt"
    
    await bot.send_document(
        chat_id,
        document=FSInputFile(text_file, filename=text_file.name),
        caption=f"📝 Текстовая версия главы {story.current_chapter}"
    )

async def show_next_chapter_button(chat_id: int, story: UserStory):
    """Показывает кнопку для следующей главы"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Написать главу {story.current_chapter + 1}",
        callback_data="next_chapter"
    )
    builder.button(
        text="Продолжить позже",
        callback_data="later"
    )
    builder.adjust(1)
    
    await bot.send_message(
        chat_id,
        f"✅ *Глава {story.current_chapter} готова!*\n\n"
        f"Осталось глав: {story.total_chapters - story.current_chapter}\n\n"
        f"Хочешь продолжить сейчас или позже?",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "next_chapter")
async def next_chapter_handler(callback: CallbackQuery):
    """Обработчик кнопки 'Следующая глава'"""
    user_id = callback.from_user.id
    
    if user_id not in user_stories:
        await callback.answer("Начни новую историю через /new")
        return
    
    story = user_stories[user_id]
    
    if story.current_chapter >= story.total_chapters:
        await callback.answer("История уже завершена! Начни новую через /new")
        return
    
    await callback.answer("Начинаю писать следующую главу...")
    await callback.message.delete()  # Удаляем кнопку
    
    # Запускаем написание следующей главы
    await write_chapter(user_id, callback.message.chat.id)

@router.callback_query(F.data == "later")
async def later_handler(callback: CallbackQuery):
    """Обработчик кнопки 'Продолжить позже'"""
    await callback.answer("Окей, продолжим позже! Напиши 'дальше' когда будешь готов.")
    await callback.message.delete()

@router.message(F.text.lower().in_(["дальше", "следующая глава", "продолжить"]))
async def continue_story_handler(message: Message):
    """Обработчик текстовых команд для продолжения"""
    user_id = message.from_user.id
    
    if user_id not in user_stories:
        await message.answer("Начни новую историю через /new")
        return
    
    story = user_stories[user_id]
    
    if story.current_chapter >= story.total_chapters:
        await message.answer("История уже завершена! Начни новую через /new")
        return
    
    if story.current_chapter == 0:
        await message.answer("Сначала начни историю через /new")
        return
    
    # Запускаем написание следующей главы
    await write_chapter(user_id, message.chat.id)

# ========== ОБРАБОТКА ОШИБОК ==========
@router.message()
async def handle_other_messages(message: Message):
    """Обработчик всех остальных сообщений"""
    if message.text:
        await message.answer(
            "Я специализируюсь на написании фанфиков! 🖋️\n\n"
            "Чтобы начать, напиши:\n"
            "• 'напиши фанфик'\n"
            "• или используй команду /new\n\n"
            "Другие команды:\n"
            "/start - справка\n"
            "/reset - сбросить историю\n"
            "/status - прогресс"
        )

# ========== ЗАПУСК БОТА ==========
async def main():
    """Основная функция запуска"""
    logger.info("Starting bot...")
    
    # Запускаем веб-сервер в фоне
    web_runner = await start_web_server()
    
    try:
        # Запускаем бота
        await dp.start_polling(bot)
    finally:
        # Очищаем ресурсы
        await bot.session.close()
        await web_runner.cleanup()

if __name__ == "__main__":
    # Проверяем наличие обязательных переменных
    if GROQ_API_KEY == "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":
        logger.error("❌ Установи GROQ_API_KEY в коде!")
        exit(1)
    
    if BOT_TOKEN == "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4":
        logger.error("❌ Установи BOT_TOKEN в коде!")
        exit(1)
    
    # Запускаем бота
    asyncio.run(main())
