import os
import io
import requests
import telebot
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
# Вставь ключи в Environment Variables на Render!
BOT_TOKEN = os.getenv("8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4")
DEEPSEEK_API_KEY = os.getenv("sk-0f6ccbcf2ab44b5687a58934e3ae626f")
API_URL = "https://api.deepseek.com/v1/chat/completions" # Официальный URL DeepSeek

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# --- ВЕБ-СЕРВЕР (Для стабильности на Render) ---
@app.route('/')
def home():
    return "DeepSeek Фанфик-бот активен!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# --- ЛОГИКА DEEPSEEK ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "📝 Привет! Я использую мощный DeepSeek для написания огромных фанфиков. Просто пришли мне тему!")

@bot.message_handler(func=lambda m: True)
def create_fanfic(message):
    topic = message.text
    chat_id = message.chat.id
    
    status = bot.send_message(chat_id, "🚀 DeepSeek начал генерацию... Это может занять до 2-х минут, так как текст будет очень длинным.")
    
    payload = {
        "model": "deepseek-chat", # Или deepseek-reasoner для более умных сюжетов
        "messages": [
            {
                "role": "system", 
                "content": (
                    "Ты профессиональный писатель. Напиши ОГРОМНЫЙ фанфик. "
                    "Используй сложный литературный язык, глубокие диалоги и подробные описания природы и чувств. "
                    "Текст должен быть максимально длинным и разделенным на главы."
                )
            },
            {"role": "user", "content": f"Напиши масштабный фанфик: {topic}"}
        ],
        "max_tokens": 8000, # DeepSeek позволяет выдавать очень длинные ответы
        "temperature": 0.7
    }
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}", 
        "Content-Type": "application/json"
    }

    try:
        # Увеличиваем таймаут, так как DeepSeek может долго генерировать 8к токенов
        response = requests.post(API_URL, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        
        full_text = response.json()['choices'][0]['message']['content']

        # Отправляем документом, чтобы текст не обрезался лимитами Telegram
        with io.BytesIO(full_text.encode('utf-8')) as doc:
            doc.name = f"DeepSeek_Story_{chat_id}.txt"
            bot.send_document(chat_id, doc, caption="📖 Ваш длинный фанфик от DeepSeek готов!")
            
        bot.delete_message(chat_id, status.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)}", chat_id, status.message_id)

if __name__ == "__main__":
    keep_alive() # Запуск Flask
    print("Бот на DeepSeek запущен...")
    # infinity_polling с авто-рестартом при ошибках сети
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
