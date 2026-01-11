import os
import io
import requests
import telebot
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
# Рекомендую вставить ключи в панели Render (Environment Variables)
# Но если тестишь локально, можно вписать сюда
BOT_TOKEN = os.getenv("BOT_TOKEN", "8503199106:AAHCO_ElZ-eSGpJ5VwyD9hnf48lFaYIPsak")
API_KEY = os.getenv("AGENT_PLATFORM_KEY", "sk-Oz6JFLQd0f_h3-He1Lx8dw")
API_URL = "https://litellm.tokengate.ru/v1/chat/completions"
MODEL_NAME = "openai/gpt-4o" # Можно сменить на gemini/gemini-1.5-pro для объема

# --- ОБХОД ОШИБКИ ПОРТА RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Бот для фанфиков активен!"

def run_web_server():
    # Render дает порт в переменную окружения PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web_server)
    t.start()

# --- ЛОГИКА БОТА ---
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "📚 Привет! Я мастер длинных фанфиков.\n\nНапиши тему или персонажей, и я создам целую книгу в .txt файле!")

@bot.message_handler(func=lambda message: True)
def handle_fanfic(message):
    topic = message.text
    chat_id = message.chat.id
    
    wait_msg = bot.send_message(chat_id, "⚙️ Нейросеть начала работу над большой историей... Это займет около минуты.")
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Промпт настроен на МАКСИМАЛЬНУЮ длину и детализацию
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system", 
                "content": (
                    "Ты — профессиональный писатель-романист. Твоя задача — писать ОЧЕНЬ ДЛИННЫЕ, "
                    "подробные и захватывающие фанфики. Описывай чувства персонажей, окружающую обстановку, "
                    "запахи и звуки. Разделяй историю на главы. Текст должен быть минимум на 2000 слов."
                )
            },
            {"role": "user", "content": f"Напиши масштабный фанфик на тему: {topic}"}
        ],
        "temperature": 0.8 # Немного креативности
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        text = result['choices'][0]['message']['content']

        # Сохранение в файл
        file_name = f"fanfic_{chat_id}.txt"
        with io.BytesIO(text.encode('utf-8')) as f:
            f.name = "Long_Fanfic.txt"
            bot.send_document(chat_id, f, caption="📖 Твой длинный фанфик готов! Приятного чтения.")
        
        bot.delete_message(chat_id, wait_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка при генерации: {str(e)}", chat_id, wait_msg.message_id)

if __name__ == "__main__":
    # Сначала запускаем веб-сервер для Render
    keep_alive()
    # Затем запускаем бота
    print("Бот запущен...")
    bot.infinity_polling()
