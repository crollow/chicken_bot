import os
import io
import telebot
import requests
from flask import Flask
from threading import Thread

# --- ТВОИ ДАННЫЕ (Удали ключи из кода перед загрузкой куда-либо!) ---
API_KEY = "sk-0f6ccbcf2ab44b5687a58934e3ae626f"
BOT_TOKEN = "8503199106:AAEZAWOq7hgC_2NBtgyckhbNl3K3qkbOKL4"
API_URL = "https://litellm.tokengate.ru/v1/chat/completions"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# --- СИСТЕМНЫЙ ПРОМПТ ДЛЯ ДЛИННЫХ ТЕКСТОВ ---
SYSTEM_PROMPT = (
    "Ты — мастер эпических фанфиков. Твоя цель — писать ОГРОМНЫЕ главы. "
    "Описывай каждое движение, каждый вдох и каждую мысль персонажа. "
    "Используй богатый литературный язык. Если история не влезает в один ответ, "
    "просто остановись, пользователь напишет 'продолжай'. "
    "Никогда не сокращай сюжет! Пиши минимум 1000 слов на главу."
)

@app.route('/')
def home(): return "Бот-писатель онлайн"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- ЛОГИКА ---
@bot.message_handler(func=lambda m: True)
def handle_fanfic(message):
    msg = bot.reply_to(message, "📜 Начинаю работу над твоим шедевром... Это займет время.")
    
    payload = {
        "model": "openai/gpt-4o", # Самая мощная для фанфиков
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Напиши огромную первую главу фанфика: {message.text}"}
        ],
        "temperature": 0.8
    }
    
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=120)
        res_data = response.json()
        text = res_data['choices'][0]['message']['content']

        # Отправляем документом, чтобы не обрезалось
        with io.BytesIO(text.encode('utf-8')) as doc:
            doc.name = "fanfic.txt"
            bot.send_document(message.chat.id, doc, caption="📖 Глава готова! Чтобы продолжить, напиши 'Пиши дальше'.")
        
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, msg.message_id)

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
