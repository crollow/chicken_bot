#!/usr/bin/env python3
"""
Hogwarts Legacy Bot - Бот для Telegram по вселенной Гарри Поттера
Волшебный помощник для настоящих магов!
"""

import os
import logging
import random
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from enum import Enum
import aiohttp
from collections import defaultdict

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    ChatMember,
    User
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8586966137:AAF-9gOezr9qNdA0K301tI3K-Xn6oS2oG5s")
PORT = int(os.environ.get('PORT', 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://webhook.site/4b214fae-9b32-4971-8f44-e43d2b58ec17")

# Состояния для ConversationHandler
SELECTING_HOUSE, QUIZ_QUESTION, DUEL_ACTION, POTION_MAKING, OWL_POST = range(5)

# Базы данных в памяти (в реальном проекте используйте SQLite или PostgreSQL)
user_data = defaultdict(dict)
quiz_scores = defaultdict(int)
user_houses = {}
duel_requests = {}
active_duels = {}
owl_messages = defaultdict(list)

# ========== МАГИЧЕСКИЕ КОНСТАНТЫ И ДАННЫЕ ==========

class Houses(Enum):
    GRYFFINDOR = "Гриффиндор"
    SLYTHERIN = "Слизерин"
    RAVENCLAW = "Когтевран"
    HUFFLEPUFF = "Пуффендуй"
    UNKNOWN = "Неизвестно"

class Spells(Enum):
    EXPECTO_PATRONUM = ("Ожидаю патронум", 25, "Защита от дементоров")
    STUPEFY = ("Оглушающий", 15, "Оглушение противника")
    EXPELLIARMUS = ("Разоружение", 20, "Выбивание палочки")
    WINGARDIUM_LEVIOSA = ("Вингардиум Левиоса", 10, "Левитация предметов")
    LUMOS = ("Люмос", 5, "Свет на конце палочки")
    NOX = ("Нокс", 5, "Гашение света")
    ACCIO = ("Притяжение", 15, "Призыв предмета")
    PROTEGO = ("Защита", 20, "Защитный щит")
    CRUCIO = ("Круциатус", 30, "Невыносимая боль")
    IMPERIO = ("Империус", 30, "Контроль над разумом")
    AVADA_KEDAVRA = ("Убивающее", 40, "Мгновенная смерть")
    SECTUMSEMPRA = ("Сектумсемпра", 25, "Нанесение ран")
    EXPECT = ("Ожидание", 0, "Ничего не делает")

    def __init__(self, name, damage, description):
        self.display_name = name
        self.damage = damage
        self.description = description

class Potions(Enum):
    POLYJUICE = ("Оборотное зелье", ["пояс удавленника", "пиявки", "рогатый слизень", "северный жаброслив"], 60)
    FELIX_FELICIS = ("Фелицис", ["счастливчик", "мутный корень", "трава пижмы", "источник удачи"], 90)
    AMORTENTIA = ("Амортенция", ["розовые лепестки", "жемчужная пыль", "лунный камень", "вздохи влюбленных"], 75)
    VERITASERUM = ("Зелье правды", ["правдолюб", "серебряная роса", "клык честности"], 50)
    WOLFSBANE = ("Порошок мандрагоры", ["корень мандрагоры", "лунный свет", "серебряная вода"], 40)

    def __init__(self, name, ingredients, brew_time):
        self.display_name = name
        self.ingredients = ingredients
        self.brew_time = brew_time

# ========== ВИКТОРИНА ==========

QUIZ_QUESTIONS = [
    {
        "question": "Что такое магла?",
        "options": ["Волшебное существо", "Человек без магических способностей", "Вид магического транспорта", "Заклинание"],
        "correct": 1,
        "difficulty": "easy",
        "points": 10
    },
    {
        "question": "Как зовут привидение, живущее в женском туалете на третьем этаже?",
        "options": ["Кровавый Барон", "Серая Дама", "Плакса Миртл", "Толстый Монах"],
        "correct": 2,
        "difficulty": "medium",
        "points": 15
    },
    {
        "question": "Какое заклинание использует Гарри, чтобы победить василиска?",
        "options": ["Экспеллиармус", "Круциатус", "Авада Кедавра", "Сектумсемпра"],
        "correct": 0,
        "difficulty": "hard",
        "points": 20
    },
    {
        "question": "Кто является крестным отцом Гарри Поттера?",
        "options": ["Альбус Дамблдор", "Римус Люпин", "Сириус Блэк", "Северус Снейп"],
        "correct": 2,
        "difficulty": "easy",
        "points": 10
    },
    {
        "question": "Какой предмет преподает Профессор Снейп?",
        "options": ["Трансфигурация", "Заклинания", "Зельеварение", "Защита от темных искусств"],
        "correct": 2,
        "difficulty": "easy",
        "points": 10
    },
    {
        "question": "Какое животное является патронусом Гарри Поттера?",
        "options": ["Лев", "Олень", "Феникс", "Собака"],
        "correct": 1,
        "difficulty": "medium",
        "points": 15
    },
    {
        "question": "Как называется газета в мире волшебников?",
        "options": ["Вестник Визенгамота", "Ежедневный Пророк", "Волшебные Новости", "Совы Мерлин"],
        "correct": 1,
        "difficulty": "easy",
        "points": 10
    },
    {
        "question": "Кто является призраком Слизерина?",
        "options": ["Серая Дама", "Кровавый Барон", "Плакса Миртл", "Толстый Монах"],
        "correct": 1,
        "difficulty": "medium",
        "points": 15
    },
    {
        "question": "Какой предмет нужно найти в Турнире Трех Волшебников первым?",
        "options": ["Золотое яйцо", "Кубок огня", "Первое задание", "Второе задание"],
        "correct": 0,
        "difficulty": "hard",
        "points": 20
    },
    {
        "question": "Кто написал книгу 'Чудовищная книга о чудовищах'?",
        "options": ["Ньютон Скамандер", "Гилдерой Локхарт", "Альбус Дамблдор", "Баттильда Бэгшот"],
        "correct": 0,
        "difficulty": "hard",
        "points": 20
    },
    {
        "question": "Как называется магическая тюрьма?",
        "options": ["Нурменгард", "Азкабан", "Годрикова Впадина", "Малфой Мэнор"],
        "correct": 1,
        "difficulty": "easy",
        "points": 10
    },
    {
        "question": "Кто является директором Хогвартса в первой книге?",
        "options": ["Минерва МакГонагалл", "Альбус Дамблдор", "Северус Снейп", "Долорес Амбридж"],
        "correct": 1,
        "difficulty": "easy",
        "points": 10
    },
    {
        "question": "Как зовут домового эльфа на кухне Хогвартса?",
        "options": ["Кричер", "Добби", "Винки", "Хокси"],
        "correct": 1,
        "difficulty": "medium",
        "points": 15
    },
    {
        "question": "Какой вид спорта популярен в мире волшебников?",
        "options": ["Квиддич", "Волшебные шахматы", "Гоблинские бои", "Трансфигурационный футбол"],
        "correct": 0,
        "difficulty": "easy",
        "points": 10
    },
    {
        "question": "Кто является автором учебника 'Продвинутое зельеварение'?",
        "options": ["Либиций Борари", "Арсенius Жигнар", "Северус Снейп", "Гораций Слизнорт"],
        "correct": 0,
        "difficulty": "hard",
        "points": 20
    }
]

# ========== ВОЛШЕБНЫЕ ПРЕДМЕТЫ И СУЩЕСТВА ==========

MAGICAL_CREATURES = [
    {"name": "Феникс", "description": "Волшебная птица, способная воскресать из пепла", "danger": "низкая"},
    {"name": "Единорог", "description": "Чистейшее существо с магической кровью", "danger": "низкая"},
    {"name": "Дракон", "description": "Огнедышащее летающее существо", "danger": "очень высокая"},
    {"name": "Гиппогриф", "description": "Существо с головой орла и телом лошади", "danger": "средняя"},
    {"name": "Василиск", "description": "Гигантский змей, взгляд которого убивает", "danger": "смертельная"},
    {"name": "Тролль", "description": "Большое глупое существо с дубинкой", "danger": "высокая"},
    {"name": "Фея", "description": "Крошечное существо с крыльями", "danger": "очень низкая"},
    {"name": "Кентавр", "description": "Существо с телом лошади и торсом человека", "danger": "средняя"},
    {"name": "Дементор", "description": "Существо, питающееся положительными эмоциями", "danger": "очень высокая"},
    {"name": "Боггарт", "description": "Существо, принимающее облик вашего страха", "danger": "переменная"}
]

MAGICAL_ITEMS = [
    {"name": "Распределяющая Шляпа", "description": "Шляпа, распределяющая студентов по факультетам"},
    {"name": "Мантия-невидимка", "description": "Мантия, делающая владельца невидимым"},
    {"name": "Карта Мародеров", "description": "Карта, показывающая всех в Хогвартсе"},
    {"name": "Воскрешающий камень", "description": "Один из Даров Смерти"},
    {"name": "Бузинная палочка", "description": "Самая мощная палочка в мире"},
    {"name": "Ловец снов", "description": "Защищает от кошмаров"},
    {"name": "Зеркало Еиналеж", "description": "Показывает самое сокровенное желание"},
    {"name": "Часы Визли", "description": "Показывают местоположение каждого члена семьи"},
    {"name": "Галерея предков", "description": "Портреты, которые могут перемещаться и разговаривать"},
    {"name": "Омут памяти", "description": "Хранилище для просмотра воспоминаний"}
]

# ========== СЛОВАРЬ ЗАКЛИНАНИЙ ==========

SPELLS_DICT = {
    "экспекто патронум": Spells.EXPECTO_PATRONUM,
    "оглушающий": Spells.STUPEFY,
    "разоружение": Spells.EXPELLIARMUS,
    "вингардиум левиоса": Spells.WINGARDIUM_LEVIOSA,
    "люмос": Spells.LUMOS,
    "нокс": Spells.NOX,
    "притяжение": Spells.ACCIO,
    "защита": Spells.PROTEGO,
    "круциатус": Spells.CRUCIO,
    "империус": Spells.IMPERIO,
    "авада кедавра": Spells.AVADA_KEDAVRA,
    "сектумсемпра": Spells.SECTUMSEMPRA,
    "ожидание": Spells.EXPECT
}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def get_house_emoji(house: str) -> str:
    """Возвращает эмодзи для факультета"""
    emojis = {
        "Гриффиндор": "🦁",
        "Слизерин": "🐍",
        "Когтевран": "🦅",
        "Пуффендуй": "🦡",
        "Неизвестно": "❓"
    }
    return emojis.get(house, "🏰")

def get_wand(user_id: int) -> str:
    """Генерирует уникальную волшебную палочку для пользователя"""
    cores = ["перо феникса", "сердце дракона", "волос единорога", "волос вейлы", "чешуя василиска"]
    woods = ["падуб", "орешник", "кипарис", "дуб", "клен", "тис", "вишня", "ивовое дерево"]
    lengths = [str(round(random.uniform(10, 15), 1)) for _ in range(10)]
    
    random.seed(user_id)
    core = random.choice(cores)
    wood = random.choice(woods)
    length = random.choice(lengths)
    random.seed()
    
    return f"{wood}, {core}, {length} дюймов"

def get_patronus(user_id: int) -> str:
    """Определяет патронуса пользователя"""
    animals = ["Олень", "Волк", "Кошка", "Собака", "Лошадь", "Феникс", "Дельфин", 
               "Сова", "Лев", "Тигр", "Медведь", "Заяц", "Лисица", "Орел", "Лебедь"]
    
    random.seed(user_id + 12345)  # Разное семя для разнообразия
    patronus = random.choice(animals)
    random.seed()
    
    return patronus

def calculate_house_points(answers: List[int]) -> Houses:
    """Распределяет на факультет на основе ответов"""
    gryffindor = 0
    slytherin = 0
    ravenclaw = 0
    hufflepuff = 0
    
    for answer in answers:
        if answer == 0:
            gryffindor += 3
        elif answer == 1:
            slytherin += 3
        elif answer == 2:
            ravenclaw += 2
            hufflepuff += 1
        elif answer == 3:
            hufflepuff += 3
            ravenclaw += 1
    
    points = [gryffindor, slytherin, ravenclaw, hufflepuff]
    max_points = max(points)
    
    if max_points == gryffindor:
        return Houses.GRYFFINDOR
    elif max_points == slytherin:
        return Houses.SLYTHERIN
    elif max_points == ravenclaw:
        return Houses.RAVENCLAW
    elif max_points == hufflepuff:
        return Houses.HUFFLEPUFF
    else:
        return Houses.UNKNOWN

# ========== КОМАНДЫ БОТА ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - приветствие и начало работы"""
    user = update.effective_user
    user_id = user.id
    
    welcome_text = f"""
✨ *Добро пожаловать в Хогвартс, {user.first_name}!* ✨

Я — волшебный помощник Хогвартса, созданный чтобы сопровождать тебя в магическом мире.

🎓 *Твоя магическая информация:*
• Волшебная палочка: `{get_wand(user_id)}`
• Патронус: `{get_patronus(user_id)}`

🏰 *Что я умею:*
/start - Начать магическое путешествие
/house - Определить свой факультет
/quiz - Викторина по Гарри Поттеру
/spells - Изучить заклинания
/duel - Вызвать на дуэль
/potions - Варить зелья
/creatures - Узнать о волшебных существах
/items - Волшебные предметы
/owl - Отправить совиную почту
/points - Узнать очки факультета
/profile - Твой магический профиль
/help - Помощь по командам

📚 *Да начнется твое магическое приключение!*
    """
    
    keyboard = [
        [InlineKeyboardButton("🏰 Распределиться", callback_data="select_house")],
        [InlineKeyboardButton("📚 Викторина", callback_data="start_quiz"),
         InlineKeyboardButton("⚔️ Дуэль", callback_data="start_duel")],
        [InlineKeyboardButton("🧪 Зелья", callback_data="brew_potion"),
         InlineKeyboardButton("🦉 Сова", callback_data="send_owl")],
        [InlineKeyboardButton("✨ Заклинания", callback_data="show_spells")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help - помощь по боту"""
    help_text = """
*✨ Помощь по волшебному боту Хогвартса ✨*

🎓 *Основные команды:*
/start - Начать магическое путешествие
/house - Определить свой факультет
/quiz - Викторина по вселенной Гарри Поттера
/spells - Изучить заклинания и их применение
/duel - Вызвать друга на магическую дуэль
/potions - Варить волшебные зелья
/creatures - Узнать о магических существах
/items - Изучить волшебные предметы
/owl - Отправить совиную почту другому волшебнику
/points - Узнать текущие очки факультета
/profile - Показать твой магический профиль
/rules - Правила Хогвартса

⚡ *Быстрые действия:*
Напиши "заклинание" чтобы увидеть список заклинаний
Напиши "факультет" чтобы узнать о факультетах
Напиши "квидич" чтобы узнать о квидиче

🎮 *Особенности:*
• Набирай очки для своего факультета
• Соревнуйся с друзьями в викторине
• Изучай темные искусства (осторожно!)
• Общайся через совиную почту

*Примечание:* Используй кнопки под сообщениями для быстрой навигации!
    """
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def house_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /house - распределение по факультету"""
    user_id = update.effective_user.id
    
    # Если пользователь уже распределен
    if user_id in user_houses:
        house = user_houses[user_id]
        emoji = get_house_emoji(house.value)
        house_info = {
            Houses.GRYFFINDOR: "*Гриффиндор 🦁*\n\nДоблесть, храбрость, честь и благородство! Основан Годриком Гриффиндором. Цвета: алый и золотой.",
            Houses.SLYTHERIN: "*Слизерин 🐍*\n\nАмбициозность, хитрость, находчивость и стремление к величию! Основан Салазаром Слизерином. Цвета: изумрудный и серебряный.",
            Houses.RAVENCLAW: "*Когтевран 🦅*\n\nМудрость, ум, творчество и остроумие! Основан Кандидой Когтевран. Цвета: синий и бронзовый.",
            Houses.HUFFLEPUFF: "*Пуффендуй 🦡*\n\nТрудолюбие, верность, терпение и честность! Основан Пенелопой Пуффендуй. Цвета: желтый и черный."
        }
        
        await update.message.reply_text(
            f"{emoji} Ты уже принадлежишь к {house.value}!\n\n{house_info.get(house, '')}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Начало распределения
    await update.message.reply_text(
        "🎩 *Время распределения!*\n\n"
        "Сейчас Распределяющая Шляпа определит твой факультет.\n"
        "Ответь на несколько вопросов честно!",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Вопросы для распределения
    sorting_questions = [
        "Что ты ценишь больше всего?",
        "Как бы ты описал себя?",
        "Что бы ты сделал, если нашел потерянный кошелек?",
        "Какое животное тебе ближе?"
    ]
    
    options = [
        ["Храбрость и честь", "Амбиции и власть", "Мудрость и знания", "Верность и трудолюбие"],
        ["Смелый и решительный", "Хитрый и амбициозный", "Умный и творческий", "Терпеливый и справедливый"],
        ["Поищу владельца", "Возьму себе", "Проанализирую содержимое", "Отнесу в полицию"],
        ["Лев", "Змея", "Орел", "Барсук"]
    ]
    
    # Сохраняем вопросы в контексте
    context.user_data['sorting_questions'] = sorting_questions
    context.user_data['sorting_options'] = options
    context.user_data['sorting_answers'] = []
    context.user_data['current_question'] = 0
    
    # Отправляем первый вопрос
    keyboard = []
    for i, option in enumerate(options[0]):
        keyboard.append([InlineKeyboardButton(option, callback_data=f"sort_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"*Вопрос 1:* {sorting_questions[0]}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    
    return SELECTING_HOUSE

async def sorting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответов на вопросы распределения"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    answer_index = int(data.split("_")[1])
    
    # Сохраняем ответ
    context.user_data['sorting_answers'].append(answer_index)
    current_q = context.user_data['current_question'] + 1
    
    if current_q < len(context.user_data['sorting_questions']):
        # Следующий вопрос
        context.user_data['current_question'] = current_q
        
        keyboard = []
        options = context.user_data['sorting_options'][current_q]
        for i, option in enumerate(options):
            keyboard.append([InlineKeyboardButton(option, callback_data=f"sort_{i}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"*Вопрос {current_q + 1}:* {context.user_data['sorting_questions'][current_q]}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        # Все вопросы отвечены, определяем факультет
        house = calculate_house_points(context.user_data['sorting_answers'])
        user_houses[user_id] = house
        emoji = get_house_emoji(house.value)
        
        house_messages = {
            Houses.GRYFFINDOR: f"🎉 {emoji} *ГРИФФИНДОР!* {emoji}\n\n"
                               "Поздравляю! Распределяющая Шляпа видит в тебе настоящего гриффиндорца!\n"
                               "Ты обладаешь храбростью, доблестью и благородством.\n"
                               "Твой девиз: 'Действуй смело, защищай слабых!'",
            Houses.SLYTHERIN: f"🎉 {emoji} *СЛИЗЕРИН!* {emoji}\n\n"
                              "Поздравляю! Распределяющая Шляпа видит в тебе истинного слизеринца!\n"
                              "Ты амбициозен, хитёр и стремишься к величию.\n"
                              "Твой девиз: 'Победитель получает всё!'",
            Houses.RAVENCLAW: f"🎉 {emoji} *КОГТЕВРАН!* {emoji}\n\n"
                              "Поздравляю! Распределяющая Шляпа видит в тебе настоящего когтевранца!\n"
                              "Ты умен, мудр и всегда стремишься к знаниям.\n"
                              "Твой девиз: 'Ум превыше всего!'",
            Houses.HUFFLEPUFF: f"🎉 {emoji} *ПУФФЕНДУЙ!* {emoji}\n\n"
                               "Поздравляю! Распределяющая Шляпа видит в тебе истинного пуффендуйца!\n"
                               "Ты трудолюбив, верен и справедлив.\n"
                               "Твой девиз: 'Справедливость и честность!'"
        }
        
        message = house_messages.get(house, "Хм... Шляпа не может определиться. Попробуй еще раз!")
        
        # Добавляем информацию о факультете
        message += f"\n\n✨ *Информация о факультете:*\n"
        message += f"• Основатель: {get_founder(house)}\n"
        message += f"• Призрак: {get_ghost(house)}\n"
        message += f"• Гостиная: {get_common_room(house)}\n"
        message += f"• Цвета: {get_colors(house)}\n"
        message += f"• Черты характера: {get_traits(house)}"
        
        keyboard = [[InlineKeyboardButton("✨ Начать приключение", callback_data="start_adventure")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        # Очищаем данные
        context.user_data.clear()
        return ConversationHandler.END

def get_founder(house: Houses) -> str:
    """Возвращает основателя факультета"""
    founders = {
        Houses.GRYFFINDOR: "Годрик Гриффиндор",
        Houses.SLYTHERIN: "Салазар Слизерин",
        Houses.RAVENCLAW: "Кандида Когтевран",
        Houses.HUFFLEPUFF: "Пенелопа Пуффендуй"
    }
    return founders.get(house, "Неизвестно")

def get_ghost(house: Houses) -> str:
    """Возвращает призрака факультета"""
    ghosts = {
        Houses.GRYFFINDOR: "Почти Безголовый Ник",
        Houses.SLYTHERIN: "Кровавый Барон",
        Houses.RAVENCLAW: "Серая Дама",
        Houses.HUFFLEPUFF: "Толстый Монах"
    }
    return ghosts.get(house, "Без призрака")

def get_common_room(house: Houses) -> str:
    """Возвращает описание гостиной факультета"""
    rooms = {
        Houses.GRYFFINDOR: "В башне, за портретом Полной Дамы",
        Houses.SLYTHERIN: "В подземельях, под озером",
        Houses.RAVENCLAW: "В башне, за дверью с загадкой",
        Houses.HUFFLEPUFF: "Рядом с кухнями, за бочками"
    }
    return rooms.get(house, "Секретное место")

def get_colors(house: Houses) -> str:
    """Возвращает цвета факультета"""
    colors = {
        Houses.GRYFFINDOR: "Алый и золотой",
        Houses.SLYTHERIN: "Изумрудный и серебряный",
        Houses.RAVENCLAW: "Синий и бронзовый",
        Houses.HUFFLEPUFF: "Желтый и черный"
    }
    return colors.get(house, "Радужные")

def get_traits(house: Houses) -> str:
    """Возвращает черты характера факультета"""
    traits = {
        Houses.GRYFFINDOR: "Храбрость, благородство, честь",
        Houses.SLYTHERIN: "Амбициозность, хитрость, находчивость",
        Houses.RAVENCLAW: "Мудрость, ум, творчество",
        Houses.HUFFLEPUFF: "Трудолюбие, верность, справедливость"
    }
    return traits.get(house, "Разные")

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /quiz - начать викторину"""
    user_id = update.effective_user.id
    
    # Проверяем, есть ли активная викторина
    if 'quiz_active' in context.user_data:
        await update.message.reply_text(
            "У тебя уже есть активная викторина! Закончи ее сначала.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Начинаем новую викторину
    context.user_data['quiz_score'] = 0
    context.user_data['quiz_questions'] = random.sample(QUIZ_QUESTIONS, 10)
    context.user_data['current_question'] = 0
    context.user_data['quiz_active'] = True
    
    # Отправляем первый вопрос
    await send_quiz_question(update, context)
    
    return QUIZ_QUESTION

async def send_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет вопрос викторины"""
    current_q = context.user_data['current_question']
    questions = context.user_data['quiz_questions']
    question_data = questions[current_q]
    
    keyboard = []
    for i, option in enumerate(question_data['options']):
        keyboard.append([InlineKeyboardButton(f"{chr(65 + i)}. {option}", callback_data=f"quiz_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"*Вопрос {current_q + 1}/10* ({question_data['difficulty']})\n\n"
    message += f"📚 {question_data['question']}\n\n"
    message += f"🏆 Очков за правильный ответ: {question_data['points']}"
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответов викторины"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    answer_index = int(data.split("_")[1])
    
    current_q = context.user_data['current_question']
    questions = context.user_data['quiz_questions']
    question_data = questions[current_q]
    
    # Проверяем ответ
    is_correct = answer_index == question_data['correct']
    
    if is_correct:
        context.user_data['quiz_score'] += question_data['points']
        result_text = f"✅ *Правильно!* +{question_data['points']} очков"
    else:
        correct_answer = question_data['options'][question_data['correct']]
        result_text = f"❌ *Неправильно!* Правильный ответ: {correct_answer}"
    
    # Обновляем общий счет пользователя
    if is_correct:
        quiz_scores[user_id] += question_data['points']
    
    await query.edit_message_text(
        f"{result_text}\n\nТвой текущий счет: {context.user_data['quiz_score']} очков"
    )
    
    # Переход к следующему вопросу или завершение
    context.user_data['current_question'] += 1
    
    if context.user_data['current_question'] < len(questions):
        await asyncio.sleep(2)
        await send_quiz_question(update, context)
    else:
        # Завершение викторины
        final_score = context.user_data['quiz_score']
        total_possible = sum(q['points'] for q in questions)
        
        # Определяем оценку
        percentage = (final_score / total_possible) * 100
        if percentage >= 90:
            grade = "📚 *Отлично!* Ты настоящий знаток магии!"
            house_points = 50
        elif percentage >= 70:
            grade = "📗 *Хорошо!* Ты хорошо разбираешься в магии!"
            house_points = 30
        elif percentage >= 50:
            grade = "📘 *Удовлетворительно!* Продолжай изучать магию!"
            house_points = 20
        else:
            grade = "📙 *Нужно подучиться!* Перечитай книги о Гарри Поттере!"
            house_points = 10
        
        # Начисляем очки факультету
        if user_id in user_houses:
            house = user_houses[user_id]
            # В реальном проекте здесь должно быть сохранение в базу данных
            house_points_text = f"\n🏆 Твой факультет получает {house_points} очков!"
        else:
            house_points_text = "\n🏰 Сначала определи свой факультет (/house)!"
        
        final_message = f"""
✨ *Викторина завершена!* ✨

📊 Твой результат: {final_score} из {total_possible} очков
{grade}

🏆 Твой общий счет в викторинах: {quiz_scores[user_id]} очков
{house_points_text}

🎮 Хочешь сыграть еще раз? Используй /quiz
        """
        
        keyboard = [
            [InlineKeyboardButton("🔄 Еще викторину", callback_data="start_quiz"),
             InlineKeyboardButton("🏠 В меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            final_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        # Очищаем данные викторины
        context.user_data.pop('quiz_active', None)
        context.user_data.pop('quiz_score', None)
        context.user_data.pop('quiz_questions', None)
        context.user_data.pop('current_question', None)
        
        return ConversationHandler.END

async def spells_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /spells - список заклинаний"""
    spells_text = """
✨ *Волшебные заклинания* ✨

Вот список основных заклинаний, которые ты можешь использовать:

⚡ *Защитные заклинания:*
• *Ожидаю патронум* - Защита от дементоров
• *Защита* - Создание защитного щита
• *Разоружение* - Выбивание палочки у противника

💥 *Наступательные заклинания:*
• *Оглушающий* - Оглушение противника
• *Сектумсемпра* - Нанесение ран
• *Притяжение* - Призыв предмета

🌙 *Заклинания света:*
• *Люмос* - Создание света
• *Нокс* - Гашение света

🌀 *Заклинания перемещения:*
• *Вингардиум Левиоса* - Левитация предметов

☠️ *Непростительные заклинания (осторожно!):*
• *Круциатус* - Невыносимая боль
• *Империус* - Контроль над разумом
• *Убивающее* - Мгновенная смерть

📝 *Как использовать:* Напиши название заклинания, чтобы узнать о нем подробнее!
        """
    
    keyboard = []
    spells_list = list(Spells)[:8]  # Первые 8 заклинаний
    for i in range(0, len(spells_list), 2):
        row = []
        for j in range(2):
            if i + j < len(spells_list):
                spell = spells_list[i + j]
                row.append(InlineKeyboardButton(spell.display_name, callback_data=f"spell_{spell.name}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🌀 Все заклинания", callback_data="all_spells")])
    keyboard.append([InlineKeyboardButton("⚔️ Использовать в дуэли", callback_data="start_duel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        spells_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def spell_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детали заклинания"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    spell_name = data.split("_")[1]
    
    try:
        spell = Spells[spell_name]
        spell_text = f"""
*{spell.display_name}*

💫 *Сила:* {spell.damage} единиц
📖 *Описание:* {spell.description}
✨ *Тип:* {'Непростительное' if spell.damage >= 30 else 'Обычное'}
⚡ *Сложность:* {'Высокая' if spell.damage >= 20 else 'Средняя' if spell.damage >= 10 else 'Низкая'}

📚 *Интересный факт:* {get_spell_fact(spell_name)}
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к заклинаниям", callback_data="show_spells"),
             InlineKeyboardButton("⚔️ Использовать в дуэли", callback_data="start_duel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            spell_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    except KeyError:
        await query.edit_message_text("Заклинание не найдено!")

def get_spell_fact(spell_name: str) -> str:
    """Возвращает интересный факт о заклинании"""
    facts = {
        "EXPECTO_PATRONUM": "Это заклинание требует счастливого воспоминания",
        "STUPEFY": "Самое распространенное заклинание в бою",
        "EXPELLIARMUS": "Любимое заклинание Гарри Поттера",
        "AVADA_KEDAVRA": "Одно из трех непростительных заклинаний",
        "CRUCIO": "Запрещено Министерством магии",
        "IMPERIO": "Позволяет контролировать волю жертвы"
    }
    return facts.get(spell_name, "Это заклинание изучается в Хогвартсе")

async def duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /duel - начать дуэль"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    duel_text = f"""
⚔️ *Магическая Дуэль* ⚔️

{username}, ты готов к волшебной дуэли?

🎯 *Правила дуэли:*
1. У каждого дуэлянта 100 единиц здоровья
2. Заклинания наносят разный урон
3. Непростительные заклинания могут быть заблокированы
4. Первый, кто потеряет все здоровье, проигрывает

🛡️ *Доступные действия:*
• Атаковать заклинанием
• Защититься щитом
• Использовать зелье (если есть)

👥 *Выбери противника или создай вызов:*
        """
    
    keyboard = [
        [InlineKeyboardButton("🎮 Случайный противник", callback_data="duel_random")],
        [InlineKeyboardButton("👥 Список игроков", callback_data="duel_list")],
        [InlineKeyboardButton("📝 Создать вызов", callback_data="duel_challenge")],
        [InlineKeyboardButton("📊 Мои дуэли", callback_data="duel_stats")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        duel_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def duel_challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание вызова на дуэль"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    # Создаем уникальный ID для вызова
    challenge_id = f"{user_id}_{int(datetime.now().timestamp())}"
    duel_requests[challenge_id] = {
        'challenger_id': user_id,
        'challenger_name': username,
        'created_at': datetime.now(),
        'status': 'waiting'
    }
    
    challenge_text = f"""
🎯 *Вызов на дуэль создан!*

👤 Вызывающий: {username}
🆔 Код вызова: `{challenge_id}`
⏱️ Действителен: 10 минут

📋 *Как присоединиться:*
1. Поделись этим кодом с другом
2. Или подожди случайного противника
3. Противник должен использовать команду /duel_join {challenge_id}

⚡ *Готов к битве!*
        """
    
    keyboard = [
        [InlineKeyboardButton("🔗 Поделиться вызовом", 
         url=f"https://t.me/share/url?url=Присоединяйся%20к%20моей%20дуэли!%20Код:%20{challenge_id}&text=⚔️%20Вызов%20на%20магическую%20дуэль!")],
        [InlineKeyboardButton("❌ Отменить вызов", callback_data=f"cancel_duel_{challenge_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        challenge_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def potions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /potions - варить зелья"""
    potions_text = """
🧪 *Мастерская зельеварения* 🧪

Добро пожаловать в подвал профессора Снейпа!
Здесь ты можешь варить магические зелья.

📚 *Доступные зелья:*
• *Оборотное зелье* - Позволяет принять облик другого человека
• *Фелицис* - Зелье удачи (осторожно с дозировкой!)
• *Амортенция* - Самое сильное приворотное зелье
• *Зелье правды* - Заставляет говорить только правду
• *Порошок мандрагоры* - Лечит окаменевших

⚗️ *Процесс варки:*
1. Выбери рецепт
2. Собери ингредиенты
3. Следуй инструкциям
4. Дождись готовности

⚠️ *Предупреждение:* Неправильное зелье может быть опасно!
        """
    
    keyboard = []
    potions_list = list(Potions)
    for potion in potions_list:
        keyboard.append([InlineKeyboardButton(
            f"🧪 {potion.display_name}", 
            callback_data=f"potion_{potion.name}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("📦 Мои ингредиенты", callback_data="my_ingredients"),
        InlineKeyboardButton("🏺 Мои зелья", callback_data="my_potions")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        potions_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def potion_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детали зелья и процесс варки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    potion_name = data.split("_")[1]
    
    try:
        potion = Potions[potion_name]
        
        # Проверяем, есть ли у пользователя ингредиенты
        user_id = query.from_user.id
        has_ingredients = check_ingredients(user_id, potion)
        
        potion_text = f"""
*🧪 {potion.display_name}*

📖 *Описание:* {get_potion_description(potion_name)}
⏱️ *Время варки:* {potion.brew_time} минут
⚗️ *Сложность:* {get_potion_difficulty(potion)}

🔮 *Ингредиенты:*
"""
        
        for ingredient in potion.ingredients:
            potion_text += f"• {ingredient}\n"
        
        if has_ingredients:
            potion_text += f"\n✅ У тебя есть все ингредиенты!\n"
            keyboard = [[InlineKeyboardButton("⚗️ Начать варку", callback_data=f"brew_{potion.name}")]]
        else:
            potion_text += f"\n❌ Не хватает некоторых ингредиентов\n"
            keyboard = [[InlineKeyboardButton("🛒 Найти ингредиенты", callback_data=f"find_ingredients_{potion.name}")]]
        
        keyboard.append([InlineKeyboardButton("🔙 Назад к зельям", callback_data="brew_potion")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            potion_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    except KeyError:
        await query.edit_message_text("Зелье не найдено!")

def check_ingredients(user_id: int, potion: Potions) -> bool:
    """Проверяет, есть ли у пользователя ингредиенты для зелья"""
    # В реальном проекте здесь должна быть проверка из базы данных
    # Для демо всегда возвращаем True для некоторых зелий
    return potion.name in ["POLYJUICE", "FELIX_FELICIS"]

def get_potion_description(potion_name: str) -> str:
    """Возвращает описание зелья"""
    descriptions = {
        "POLYJUICE": "Позволяет принять облик другого человека на 1 час",
        "FELIX_FELICIS": "Приносит удачу, но вызывает привыкание",
        "AMORTENTIA": "Самое сильное приворотное зелье в мире",
        "VERITASERUM": "Заставляет говорить только правду в течение 10 минут",
        "WOLFSBANE": "Лечит окаменевших и успокаивает оборотней"
    }
    return descriptions.get(potion_name, "Магическое зелье")

def get_potion_difficulty(potion: Potions) -> str:
    """Возвращает сложность варки зелья"""
    if potion.brew_time >= 80:
        return "Очень сложное"
    elif potion.brew_time >= 60:
        return "Сложное"
    elif potion.brew_time >= 40:
        return "Среднее"
    else:
        return "Простое"

async def creatures_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /creatures - информация о магических существах"""
    creatures_text = """
🦄 *Магические существа* 🦄

Мир волшебников населен удивительными существами!
От безобидных фей до смертельно опасных драконов.

📚 *Категории существ:*
• ⭐ **XXXXX** - Известный убийца волшебников
• ⭐⭐⭐⭐ **XXXX** - Опасный, требует специальных знаний
• ⭐⭐⭐ **XXX** - Опытный волшебник может справиться
• ⭐⭐ **XX** - Безобидное / может быть приручено
• ⭐ **X** - Скучное

🔍 *Выбери категорию для изучения:*
        """
    
    keyboard = [
        [
            InlineKeyboardButton("⭐ Безопасные", callback_data="creatures_safe"),
            InlineKeyboardButton("⭐⭐ Обычные", callback_data="creatures_normal")
        ],
        [
            InlineKeyboardButton("⭐⭐⭐ Опасные", callback_data="creatures_dangerous"),
            InlineKeyboardButton("⭐⭐⭐⭐ Очень опасные", callback_data="creatures_very_dangerous")
        ],
        [
            InlineKeyboardButton("⭐⭐⭐⭐⭐ Смертельные", callback_data="creatures_deadly"),
            InlineKeyboardButton("🔍 Поиск существа", callback_data="search_creature")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        creatures_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def creatures_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список существ по категории"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    category = data.split("_")[1]
    
    # Фильтруем существ по опасности
    danger_map = {
        'safe': ['очень низкая', 'низкая'],
        'normal': ['средняя'],
        'dangerous': ['высокая'],
        'very_dangerous': ['очень высокая'],
        'deadly': ['смертельная']
    }
    
    filtered_creatures = [c for c in MAGICAL_CREATURES if c['danger'] in danger_map.get(category, [])]
    
    if not filtered_creatures:
        await query.edit_message_text("В этой категории пока нет существ!")
        return
    
    # Создаем сообщение с существами
    creatures_text = f"""
🦄 *Магические существа ({category})*

"""
    
    for creature in filtered_creatures[:10]:  # Ограничиваем 10 существами
        danger_emoji = get_danger_emoji(creature['danger'])
        creatures_text += f"""
*{creature['name']}* {danger_emoji}
{creature['description']}
Опасность: {creature['danger']}

"""
    
    keyboard = []
    for i, creature in enumerate(filtered_creatures[:5]):
        keyboard.append([InlineKeyboardButton(
            f"🔍 {creature['name']}", 
            callback_data=f"creature_{creature['name'].replace(' ', '_')}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к категориям", callback_data="creatures_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        creatures_text[:4000],  # Ограничение Telegram
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

def get_danger_emoji(danger_level: str) -> str:
    """Возвращает эмодзи для уровня опасности"""
    emojis = {
        'очень низкая': '🟢',
        'низкая': '🟡',
        'средняя': '🟠',
        'высокая': '🔴',
        'очень высокая': '💀',
        'смертельная': '☠️'
    }
    return emojis.get(danger_level, '⚪')

async def items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /items - волшебные предметы"""
    items_text = """
🔮 *Волшебные предметы* 🔮

Мир Гарри Поттера полон удивительных артефактов и предметов!
От полезных инструментов до могущественных реликвий.

🏆 *Категории предметов:*
• **Дары Смерти** - Самые могущественные артефакты
• **Карты и навигация** - Помощь в перемещении
• **Одежда и аксессуары** - Магическая экипировка
• **Инструменты волшебника** - Для учебы и работы
• **Защитные артефакты** - Оборона от темных сил

✨ *Исследуй магические предметы:*
        """
    
    keyboard = [
        [
            InlineKeyboardButton("💀 Дары Смерти", callback_data="items_deathly_hallows"),
            InlineKeyboardButton("🗺️ Карты", callback_data="items_maps")
        ],
        [
            InlineKeyboardButton("👕 Одежда", callback_data="items_clothing"),
            InlineKeyboardButton("🛠️ Инструменты", callback_data="items_tools")
        ],
        [
            InlineKeyboardButton("🛡️ Защита", callback_data="items_defense"),
            InlineKeyboardButton("🔍 Все предметы", callback_data="items_all")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        items_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def owl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /owl - совиная почта"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Проверяем непрочитанные сообщения
    unread_count = len([m for m in owl_messages.get(user_id, []) if not m.get('read', False)])
    
    owl_text = f"""
🦉 *Совиная Почта Хогвартса* 🦉

Приветствую, {username}!

📮 *Твоя почта:*
• 📨 Непрочитанных: {unread_count}
• 📤 Отправленных: {len([m for m in owl_messages.values() for msg in m if msg.get('from') == user_id])}
• 🗑️ В корзине: 0

✉️ *Что ты можешь сделать:*
• Отправить письмо другу
• Проверить входящие
• Отправить анонимное послание
• Получить письмо от персонажей

⚡ *Быстрая отправка:*
Напиши `сове @username текст сообщения`
        """
    
    keyboard = [
        [
            InlineKeyboardButton("📨 Входящие", callback_data="owl_inbox"),
            InlineKeyboardButton("📤 Отправленные", callback_data="owl_sent")
        ],
        [
            InlineKeyboardButton("✉️ Написать письмо", callback_data="owl_compose"),
            InlineKeyboardButton("🎭 Персонажи", callback_data="owl_characters")
        ],
        [
            InlineKeyboardButton("🔄 Проверить почту", callback_data="owl_check"),
            InlineKeyboardButton("📜 Правила почты", callback_data="owl_rules")
        ]
    ]
    
    if unread_count > 0:
        owl_text += f"\n🔔 *У тебя {unread_count} непрочитанных сообщений!*"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        owl_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /points - очки факультетов"""
    # В реальном проекте здесь должны быть реальные данные из БД
    # Для демо используем случайные очки
    
    points = {
        Houses.GRYFFINDOR: random.randint(300, 500),
        Houses.SLYTHERIN: random.randint(300, 500),
        Houses.RAVENCLAW: random.randint(250, 400),
        Houses.HUFFLEPUFF: random.randint(200, 350)
    }
    
    # Определяем лидера
    leader = max(points, key=points.get)
    
    points_text = """
🏆 *Кубок Факультетов Хогвартса* 🏆

Текущие очки факультетов:

"""
    
    for house, score in points.items():
        emoji = get_house_emoji(house.value)
        points_text += f"{emoji} *{house.value}:* {score} очков\n"
    
    points_text += f"\n🎯 *Текущий лидер:* {leader.value} {get_house_emoji(leader.value)}"
    
    # Добавляем информацию о том, как получить очки
    points_text += """

✨ *Как получить очки для факультета:*
• 📚 Правильные ответы в викторине (+10-50)
• ⚔️ Победы в дуэлях (+20)
• 🧪 Успешное зельеварение (+15)
• 🦉 Активность в совиной почте (+5)
• 🎯 Особые достижения (+100)

⚠️ *Как потерять очки:*
• 💀 Использование непростительных заклинаний (-50)
• ⏰ Опоздание на уроки (-10)
• 🔊 Нарушение правил (-20)

🏅 *В конце года факультет-победитель получит Кубок!*
        """
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Подробная статистика", callback_data="points_detailed"),
            InlineKeyboardButton("🏅 Мои очки", callback_data="points_mine")
        ],
        [
            InlineKeyboardButton("🎯 Как получить больше очков", callback_data="points_howto"),
            InlineKeyboardButton("📅 История изменений", callback_data="points_history")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        points_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile - магический профиль"""
    user = update.effective_user
    user_id = user.id
    
    # Получаем данные пользователя
    house = user_houses.get(user_id, Houses.UNKNOWN)
    house_emoji = get_house_emoji(house.value)
    quiz_score = quiz_scores.get(user_id, 0)
    
    # Определяем уровень волшебника
    if quiz_score >= 500:
        wizard_level = "Волшебник-Мастер 🧙‍♂️"
    elif quiz_score >= 300:
        wizard_level = "Продвинутый волшебник 📚"
    elif quiz_score >= 150:
        wizard_level = "Ученик 7-го года 🎓"
    elif quiz_score >= 50:
        wizard_level = "Ученик 5-го года 📖"
    else:
        wizard_level = "Первокурсник 🎒"
    
    profile_text = f"""
✨ *Магический Профиль* ✨

👤 *Волшебник:* {user.first_name}
🆔 *ID:* `{user_id}`
🏠 *Факультет:* {house.value} {house_emoji}
📊 *Уровень:* {wizard_level}

🎯 *Достижения:*
• 📚 Очки викторины: {quiz_score}
• ⚔️ Побед в дуэлях: {user_data[user_id].get('duel_wins', 0)}
• 🧪 Сваренных зелий: {user_data[user_id].get('potions_brewed', 0)}
• 🦉 Отправлено писем: {len([m for m in owl_messages.values() for msg in m if msg.get('from') == user_id])}

🔮 *Магические способности:*
• 🪄 Палочка: `{get_wand(user_id)}`
• 🦌 Патронус: `{get_patronus(user_id)}`
• ⚡ Любимое заклинание: {get_favorite_spell(user_id)}
• 🏆 Лучший результат в викторине: {user_data[user_id].get('best_quiz_score', 0)}

📅 *Статистика:*
• 🎮 Всего активностей: {user_data[user_id].get('total_actions', 0)}
• ⏱️ Время в боте: {user_data[user_id].get('bot_time', 0)} минут
• 🏅 Ранг на факультете: #{get_house_rank(user_id, house)}

🎖️ *Награды:* {get_user_badges(user_id)}
        """
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Подробная статистика", callback_data="profile_stats"),
            InlineKeyboardButton("🎖️ Мои награды", callback_data="profile_badges")
        ],
        [
            InlineKeyboardButton("🔄 Обновить профиль", callback_data="profile_refresh"),
            InlineKeyboardButton("📤 Поделиться профилем", callback_data="profile_share")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        profile_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

def get_favorite_spell(user_id: int) -> str:
    """Определяет любимое заклинание пользователя"""
    spells_used = user_data[user_id].get('spells_used', {})
    if spells_used:
        return max(spells_used, key=spells_used.get, default="Экспекто патронум")
    return "Экспекто патронум"

def get_house_rank(user_id: int, house: Houses) -> int:
    """Определяет ранг пользователя на факультете"""
    # В реальном проекте здесь должен быть расчет из БД
    return random.randint(1, 50)

def get_user_badges(user_id: int) -> str:
    """Возвращает награды пользователя"""
    badges = []
    
    if quiz_scores.get(user_id, 0) >= 100:
        badges.append("🏆 Знаток магии")
    
    if user_data[user_id].get('duel_wins', 0) >= 10:
        badges.append("⚔️ Мастер дуэлей")
    
    if user_data[user_id].get('potions_brewed', 0) >= 5:
        badges.append("🧪 Зельевар")
    
    if len(owl_messages.get(user_id, [])) >= 20:
        badges.append("🦉 Голубятник")
    
    return ", ".join(badges) if badges else "Пока нет наград"

async def general_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех callback-запросов"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "main_menu":
        await start(update, context)
    
    elif data == "select_house":
        await house_command(update, context)
    
    elif data == "start_quiz":
        await quiz_command(update, context)
    
    elif data == "start_duel":
        await duel_command(update, context)
    
    elif data == "brew_potion":
        await potions_command(update, context)
    
    elif data == "send_owl":
        await owl_command(update, context)
    
    elif data == "show_spells":
        await spells_command(update, context)
    
    elif data.startswith("spell_"):
        await spell_detail_callback(update, context)
    
    elif data.startswith("potion_"):
        await potion_detail_callback(update, context)
    
    elif data == "creatures_menu":
        await creatures_command(update, context)
    
    elif data.startswith("creatures_"):
        await creatures_list_callback(update, context)
    
    elif data.startswith("duel_"):
        if data == "duel_challenge":
            await duel_challenge_callback(update, context)
        # Обработка других действий дуэли
    
    else:
        await query.edit_message_text("Действие не распознано. Возвращаю в меню...")
        await start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    message_text = update.message.text.lower()
    user_id = update.effective_user.id
    
    # Увеличиваем счетчик действий
    user_data[user_id]['total_actions'] = user_data[user_id].get('total_actions', 0) + 1
    
    # Обработка ключевых слов
    if any(word in message_text for word in ['заклинание', 'spell', 'заклинания']):
        await spells_command(update, context)
    
    elif any(word in message_text for word in ['факультет', 'house', 'распределение']):
        await house_command(update, context)
    
    elif any(word in message_text for word in ['квидич', 'quidditch']):
        await update.message.reply_text(
            "🏆 *Квидич - волшебный спорт!* 🏆\n\n"
            "Правила квидича:\n"
            "• 7 игроков в команде\n"
            "• 3 охотника за голы (+10 очков)\n"
            "• 2 загонщика с бладжерами\n"
            "• 1 вратарь защищает кольца\n"
            "• 1 ловец ловит снитча (+150 очков)\n\n"
            "Игра заканчивается, когда снитч пойман!",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif any(word in message_text for word in ['привет', 'hello', 'здравствуй']):
        await update.message.reply_text(
            f"Приветствую, {update.effective_user.first_name}! ✨\n"
            "Используй /start для начала магического приключения!",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif any(word in message_text for word in ['спасибо', 'thanks', 'благодарю']):
        await update.message.reply_text(
            "Всегда рад помочь! 🪄\n"
            "Удачи в твоих магических начинаниях!",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif 'сове' in message_text:
        # Обработка отправки совиной почты
        parts = message_text.split()
        if len(parts) >= 3:
            recipient = parts[1].replace('@', '')
            message = ' '.join(parts[2:])
            await update.message.reply_text(
                f"🦉 Сова отправлена пользователю {recipient}!\n"
                f"Сообщение: {message[:100]}...",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                "🦉 Формат: `сове @username текст сообщения`",
                parse_mode=ParseMode.MARKDOWN
            )
    
    else:
        # Проверяем, является ли сообщение заклинанием
        for spell_name, spell in SPELLS_DICT.items():
            if spell_name in message_text:
                await update.message.reply_text(
                    f"✨ *{spell.display_name.upper()}!* ✨\n\n"
                    f"Эффект: {spell.description}\n"
                    f"Сила: {spell.damage} единиц\n\n"
                    f"{get_spell_cast_message(spell)}",
                    parse_mode=ParseMode.MARKDOWN
                )
                break
        else:
            # Если не распознано, предлагаем помощь
            await update.message.reply_text(
                "✨ *Магическое приветствие!* ✨\n\n"
                "Я не совсем понял твое заклинание...\n"
                "Попробуй:\n"
                "• /help - для списка команд\n"
                "• 'заклинание' - для изучения заклинаний\n"
                "• 'квидич' - о волшебном спорте\n"
                "• 'факультет' - для распределения",
                parse_mode=ParseMode.MARKDOWN
            )

def get_spell_cast_message(spell: Spells) -> str:
    """Возвращает сообщение о применении заклинания"""
    messages = {
        Spells.EXPECTO_PATRONUM: "Серебристый патронус вылетает из твоей палочки!",
        Spells.STUPEFY: "Красная вспышка оглушает цель!",
        Spells.EXPELLIARMUS: "Палочка вылетает из рук противника!",
        Spells.LUMOS: "Свет загорается на конце твоей палочки!",
        Spells.NOX: "Свет гаснет, вокруг темнота...",
        Spells.AVADA_KEDAVRA: "⚡ ЗЕЛЕНАЯ ВСПЫШКА СМЕРТИ! ⚡\n(Непростительное заклинание!)"
    }
    return messages.get(spell, "Заклинание успешно применено!")

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========

from flask import Flask, jsonify
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": "Hogwarts Legacy Bot",
        "version": "1.0.0",
        "description": "Магический бот по вселенной Гарри Поттера"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/stats')
def stats():
    return jsonify({
        "users_count": len(user_houses),
        "quiz_players": len(quiz_scores),
        "active_duels": len(active_duels),
        "owl_messages": sum(len(messages) for messages in owl_messages.values())
    })

def run_web_server():
    """Запускает Flask сервер в отдельном потоке"""
    app.run(host='0.0.0.0', port=PORT)

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

def main():
    """Основная функция запуска бота"""
    
    # Запускаем веб-сервер в отдельном потоке
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info(f"Веб-сервер запущен на порту {PORT}")
    
    # Создаем приложение бота
    application = Application.builder().token(TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("spells", spells_command))
    application.add_handler(CommandHandler("duel", duel_command))
    application.add_handler(CommandHandler("potions", potions_command))
    application.add_handler(CommandHandler("creatures", creatures_command))
    application.add_handler(CommandHandler("items", items_command))
    application.add_handler(CommandHandler("owl", owl_command))
    application.add_handler(CommandHandler("points", points_command))
    application.add_handler(CommandHandler("profile", profile_command))
    
    # ConversationHandler для распределения по факультетам
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("house", house_command)],
        states={
            SELECTING_HOUSE: [CallbackQueryHandler(sorting_callback, pattern="^sort_")]
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )
    application.add_handler(conv_handler)
    
    # ConversationHandler для викторины
    quiz_handler = ConversationHandler(
        entry_points=[CommandHandler("quiz", quiz_command),
                     CallbackQueryHandler(quiz_command, pattern="^start_quiz$")],
        states={
            QUIZ_QUESTION: [CallbackQueryHandler(quiz_callback, pattern="^quiz_")]
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )
    application.add_handler(quiz_handler)
    
    # Обработчик callback-запросов
    application.add_handler(CallbackQueryHandler(general_callback))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    if WEBHOOK_URL:
        # Webhook режим для продакшена
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
        )
    else:
        # Polling режим для разработки
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
