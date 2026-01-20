from flask import Flask, render_template_string
import os

app = Flask(__name__)

# Настройки (можно подтянуть из переменных окружения)
BOT_NAME = "AnonymousBot"
BOT_LINK = f"https://t.me/{os.getenv('BOT', 'anoncoo1_bot')}"
CONTACT_LINK = "t.me/crollow"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Соглашение | {{ bot_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f4f7f9;
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #2c3e50;
        }
        .container {
            max-width: 800px;
            margin: 50px auto;
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.05);
            padding: 40px;
            background: #fff;
        }
        .header-box {
            text-align: center;
            margin-bottom: 40px;
        }
        h1 {
            font-weight: 700;
            color: #0088cc;
            margin-bottom: 10px;
        }
        .badge-status {
            background-color: #e3f2fd;
            color: #0088cc;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
        }
        h3 {
            font-size: 1.25rem;
            font-weight: 600;
            margin-top: 25px;
            color: #34495e;
            border-left: 4px solid #0088cc;
            padding-left: 15px;
        }
        p, li {
            font-size: 1.05rem;
            line-height: 1.7;
            color: #5d6d7e;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            font-size: 0.9rem;
            color: #bdc3c7;
        }
        .btn-back {
            background-color: #0088cc;
            color: white;
            border-radius: 10px;
            padding: 10px 25px;
            text-decoration: none;
            transition: 0.3s;
        }
        .btn-back:hover {
            background-color: #006699;
            color: white;
            box-shadow: 0 5px 15px rgba(0,136,204,0.3);
        }
    </style>
</head>
<body>

<div class="container">
    <div class="header-box">
        <h1>{{ bot_name }}</h1>
        <span class="badge-status">Пользовательское соглашение</span>
    </div>

    <div class="card">
        <p class="lead">Используя данный сервис, вы подтверждаете свое согласие с нижеизложенными правилами. Пожалуйста, прочтите их внимательно.</p>

        <h3>1. О Сервисе</h3>
        <p>Наш бот предназначен для обмена анонимными сообщениями. Мы обеспечиваем технический мостик между пользователями, сохраняя конфиденциальность отправителя.</p>

        <h3>2. Обязанности пользователя</h3>
        <ul>
            <li>Не использовать бота для оскорблений, травли (буллинга) и угроз.</li>
            <li>Не распространять спам, вредоносное ПО и рекламные материалы.</li>
            <li>Соблюдать законодательство вашей страны при общении.</li>
        </ul>

        <h3>3. Конфиденциальность</h3>
        <p>Мы уважаем вашу частную жизнь. Бот сохраняет ваш Telegram ID исключительно для следующих целей:</p>
        <ul>
            <li>Обеспечение функции «Черного списка» (бана).</li>
            <li>Доставка ответов на ваши анонимные вопросы.</li>
        </ul>
        <p><strong>Важно:</strong> Администрация может передать данные пользователя правоохранительным органам только при наличии официального законного запроса.</p>

        <h3>4. Ограничение ответственности</h3>
        <p>Администрация не является автором сообщений и не несет ответственности за их содержание. Вся ответственность за передаваемую информацию лежит на пользователе.</p>

        <div class="text-center mt-5">
            <a href="{{ bot_link }}" class="btn-back">Вернуться в бота</a>
        </div>
    </div>

    <div class="footer">
        &copy; 2026 {{ bot_name }} &bull; <a href="{{ contact_link }}" style="color: #bdc3c7;">Поддержка</a>
    </div>
</div>

</body>
</html>
"""

@app.route('/')
def terms_page():
    return render_template_string(
        HTML_TEMPLATE, 
        bot_name=BOT_NAME, 
        bot_link=BOT_LINK,
        contact_link=CONTACT_LINK
    )

if __name__ == '__main__':
    # Запуск на порту 10000 для совместимости с Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
