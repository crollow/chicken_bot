import telebot
import requests
import io

# --- НАСТРОЙКИ ИЗ ВАШИХ СКРИНШОТОВ ---
# 1. Вставьте ваш ключ, созданный в разделе "Ключи"
AGENT_PLATFORM_KEY = "sk-Oz6JFLQd0f_h3-He1Lx8dw" 

# 2. URL для запросов (взят прямо из вашего скриншота)
API_URL = "https://litellm.tokengate.ru/v1/chat/completions"

# 3. Выберите модель (например: openai/gpt-4o, gemini/gemini-1.5-flash и т.д.)
# Список доступных вам моделей можно посмотреть во вкладке "Поддерживаемые модели" на сайте
MODEL_NAME = "openai/gpt-4o" 

# 4. Токен вашего бота из @BotFather
BOT_TOKEN = "8503199106:AAHCO_ElZ-eSGpJ5VwyD9hnf48lFaYIPsak"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "Пришли мне тему, и я напишу фанфик в формате .txt файла!")

@bot.message_handler(func=lambda message: True)
def handle_fanfic(message):
    topic = message.text
    chat_id = message.chat.id
    
    status_msg = bot.send_message(chat_id, "⏳ Нейросеть генерирует текст... Это может занять до 30 секунд.")
    
    # Заголовки и данные по инструкции с вашего скриншота
    headers = {
        "Authorization": f"Bearer {AGENT_PLATFORM_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system", 
                "content": "Ты талантливый писатель. Напиши увлекательный и длинный фанфик на русском языке."
            },
            {
                "role": "user", 
                "content": f"Тема: {topic}"
            }
        ]
    }

    try:
        # Запрос к API
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        content = data['choices'][0]['message']['content']

        # Создаем файл в оперативной памяти
        file_stream = io.BytesIO(content.encode('utf-8'))
        file_stream.name = "fanfic.txt"

        # Отправляем документ
        bot.send_document(chat_id, file_stream, caption="✅ Готово! Приятного чтения.")
        bot.delete_message(chat_id, status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ Произошла ошибка: {e}", chat_id, status_msg.message_id)

if __name__ == "__main__":
    print("Бот запущен и готов к работе...")
    bot.infinity_polling()
