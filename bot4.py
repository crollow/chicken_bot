import os
import io
from openai import OpenAI
import telebot
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
# Если запускаешь в Termux — вставь ключи прямо в кавычки.
# Если на Render — оставь как есть и добавь их в Environment Variables.
TOKEN = os.environ.get('BOT_TOKEN', '8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4')
DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY','sk-0f6ccbcf2ab44b5687a58934e3ae626f')

client = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")
bot = telebot.TeleBot(TOKEN)
app = Flask('')

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (Чтобы не выключался) ---
@app.route('/')
def home():
    return "DeepSeek Bot is Running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# --- ЛОГИКА ФАНФИКОВ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "📚 Привет! Я пишу огромные фанфики через DeepSeek. Просто пришли тему!")

@bot.message_handler(func=lambda message: True)
def generate_fanfic(message):
    status = bot.reply_to(message, "⏳ DeepSeek генерирует длинную историю... Подождите немного.")
    
    try:
        # Используем ваш пример вызова API
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты профессиональный автор фанфиков. Пиши очень длинно, подробно, с диалогами и главами."},
                {"role": "user", "content": f"Напиши масштабный фанфик: {message.text}"},
            ],
            stream=False,
            max_tokens=4000 # Лимит на длину текста
        )

        full_text = response.choices[0].message.content

        # Отправляем документом, чтобы текст не обрезался
        with io.BytesIO(full_text.encode('utf-8')) as doc:
            doc.name = "fanfic.txt"
            bot.send_document(message.chat.id, doc, caption="📖 Ваш фанфик готов!")
        
        bot.delete_message(message.chat.id, status.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка API: {e}", message.chat.id, status.message_id)

if __name__ == "__main__":
    keep_alive() # Запуск сервера-"пиналки"
    print("Бот запущен...")
    # infinity_polling защищает от вылетов при сбое интернета
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
