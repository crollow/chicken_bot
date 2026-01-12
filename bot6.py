import os
import io
import requests
import telebot
from flask import Flask
from threading import Thread

# --- ТВОИ ДАННЫЕ ---
API_KEY = "sk-0f6ccbcf2ab44b5687a58934e3ae626f"
BOT_TOKEN = "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4"
API_URL = "https://litellm.tokengate.ru/v1/chat/completions"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# --- ТОТ САМЫЙ МОЩНЫЙ ПРОМПТ ---
# Он заставляет ИИ не спешить и описывать каждую деталь
PROMPT_ENGINE = (
    "Ты — элитный автор фанфиков. Твой стиль — гиперреализм и глубокий психологизм. "
    "ПРАВИЛА: \n"
    "1. Никогда не пиши кратко. Вместо 'он вошел', опиши тяжесть двери, холод ручки и звук шагов.\n"
    "2. На каждую сцену трать минимум 500 слов. Фокусируйся на чувствах, запахах и окружении.\n"
    "3. Если сюжет требует действия, растягивай его. Описывай мысли персонажа в момент удара или слова.\n"
    "4. Используй сложные метафоры. Пиши так, чтобы читатель полностью погрузился в атмосферу.\n"
    "5. Если текст обрывается — это нормально, пользователь попросит продолжить."
)

@app.route('/')
def home():
    return "Фанфик-бот в режиме 'Максимальный объем' запущен!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "📚 Привет! Я настроен писать ОГРОМНЫЕ истории. Пришли мне тему!")

@bot.message_handler(func=lambda m: True)
def write_fanfic(message):
    # Уведомление о начале работы
    status_msg = bot.send_message(message.chat.id, "⚙️ Нейросеть начала генерацию большой главы... Пожалуйста, подожди (это может занять до минуты).")
    
    payload = {
        "model": "openai/gpt-4o", # Лучшая модель для таких задач
        "messages": [
            {"role": "system", "content": PROMPT_ENGINE},
            {"role": "user", "content": f"Напиши масштабную, очень детальную первую главу фанфика на тему: {message.text}"}
        ],
        "temperature": 0.85 # Немного больше творчества
    }
    
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        
        full_text = response.json()['choices'][0]['message']['content']

        # Если текст получился длинным (а он должен!), отправляем файлом
        with io.BytesIO(full_text.encode('utf-8')) as doc:
            doc.name = "fanfic_chapter.txt"
            bot.send_document(
                message.chat.id, 
                doc, 
                caption="📖 Твой длинный фанфик готов! \n\nЧтобы я написал продолжение, просто напиши 'Продолжай дальше' или 'Глава 2'."
            )
            
        bot.delete_message(message.chat.id, status_msg.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Произошла ошибка: {str(e)}", message.chat.id, status_msg.message_id)

if __name__ == "__main__":
    keep_alive() # Запускаем веб-сервер для защиты от выключения
    print("Бот запущен...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
