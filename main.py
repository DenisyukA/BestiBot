import telebot
from flask import Flask, request
from telebot import types
import sqlite3
import os

# --- НАЛАШТУВАННЯ ---
# ВАЖЛИВО: Отримай новий токен через /revoke у @BotFather!
TOKEN = 'ТВІЙ_НОВИЙ_ТОКЕН_ТУТ' 
AUTH_PASSWORD = 'pentagon2025'
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# 1. Ендпоінт для Telegram (щоб бот ожив)
@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    return "Forbidden", 403

# 2. Ендпоінт для Tilda (замовлення з сайту)
@app.route('/tilda-webhook', methods=['POST'])
def tilda_webhook():
    # Тільда може слати дані як form або json
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
        
    name = data.get('Name', data.get('name', 'Невідомо'))
    phone = data.get('Phone', data.get('phone', 'Немає'))
    quantity = data.get('quantity', '1 шт')

    cursor = db.cursor()
    cursor.execute("INSERT INTO orders (name, phone, quantity, status) VALUES (?, ?, ?, 'Активне')", 
                   (name, phone, quantity))
    db.commit()
    order_id = cursor.lastrowid

    msg = f"📦 *Нове замовлення №{order_id}*\n👤 {name}\n📞 {phone}\n🔢 Кількість: {quantity}"
    notify_workers(msg)
    return "OK", 200

# --- РЕШТА ТВОЄЇ ЛОГІКИ (БАЗА, ОБРОБНИКИ КОМАНД) ---
def init_db():
    conn = sqlite3.connect('orders.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, quantity TEXT, status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS workers (chat_id INTEGER PRIMARY KEY)''')
    conn.commit()
    return conn

db = init_db()

def notify_workers(text):
    cursor = db.cursor()
    cursor.execute("SELECT chat_id FROM workers")
    workers = cursor.fetchall()
    for worker in workers:
        try:
            bot.send_message(worker[0], text, parse_mode="Markdown")
        except: pass

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Вітаю! Введіть пароль:")

@bot.message_handler(func=lambda m: m.text == AUTH_PASSWORD)
def auth(message):
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO workers (chat_id) VALUES (?)", (message.chat.id,))
    db.commit()
    bot.send_message(message.chat.id, "✅ Ви зареєстровані!")

# --- ЗАПУСК (БЕЗ THREADING І POLLING!) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
