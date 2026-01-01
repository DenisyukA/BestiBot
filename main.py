import telebot
from flask import Flask, request
from telebot import types
import sqlite3
import os

# --- НАЛАШТУВАННЯ ---
TOKEN = '7966376299:AAFXhIYp7msvOSiLI7Ve1BdrOX74JMJlZoM' 
AUTH_PASSWORD = 'pentagon2025'
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Ініціалізація бази даних
def init_db():
    conn = sqlite3.connect('orders.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, quantity TEXT, status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS workers (chat_id INTEGER PRIMARY KEY)''')
    conn.commit()
    return conn

db = init_db()

# Функція розсилки замовлень
def notify_workers(text):
    cursor = db.cursor()
    cursor.execute("SELECT chat_id FROM workers")
    workers = cursor.fetchall()
    for worker in workers:
        try:
            bot.send_message(worker[0], text, parse_mode="Markdown")
        except: pass

# 1. Ендпоінт для Telegram Updates
@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    return "Forbidden", 403

# 2. Ендпоінт для Tilda (Замовлення)
@app.route('/tilda-webhook', methods=['POST'])
def tilda_webhook():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
        
    name = data.get('Name', data.get('name', 'Невідомо'))
    phone = data.get('Phone', data.get('phone', 'Немає'))
    quantity = data.get('quantity', '1 шт')

    cursor = db.cursor()
    cursor.execute("INSERT INTO orders (name, phone, quantity, status) VALUES (?, ?, ?, 'Активні')", 
                   (name, phone, quantity))
    db.commit()
    order_id = cursor.lastrowid

    msg = f"📦 *Нове замовлення №{order_id}*\n👤 {name}\n📞 {phone}\n🔢 Кількість: {quantity}"
    notify_workers(msg)
    return "OK", 200

# --- ЛОГІКА БОТА (КНОПКИ ТА КОМАНДИ) ---

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Вітаю! Введіть пароль доступу:")

@bot.message_handler(func=lambda m: m.text == AUTH_PASSWORD)
def auth(message):
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO workers (chat_id) VALUES (?)", (message.chat.id,))
    db.commit()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📦 Мої замовлення"))
    bot.send_message(message.chat.id, "✅ Ви зареєстровані! Використовуйте кнопку меню:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📦 Мої замовлення" or m.text == "🔙 Назад")
def main_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Активні", "В роботі", "Завершені")
    bot.send_message(message.chat.id, "Виберіть категорію замовлень:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Активні", "В роботі", "Завершені"])
def show_category(message):
    cursor = db.cursor()
    cursor.execute("SELECT id, name, phone FROM orders WHERE status=?", (message.text,))
    rows = cursor.fetchall()
    
    if not rows:
        bot.send_message(message.chat.id, f"Немає замовлень у статусі '{message.text}'", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Назад"))
        return

    for row in rows:
        kb = types.InlineKeyboardMarkup()
        if message.text == "Активні":
            kb.add(types.InlineKeyboardButton("Взяти в роботу", callback_data=f"set_work_{row[0]}"))
        elif message.text == "В роботі":
            kb.add(types.InlineKeyboardButton("Завершити", callback_data=f"set_done_{row[0]}"))
        
        bot.send_message(message.chat.id, f"🆔 {row[0]} | 👤 {row[1]}\n📞 {row[2]}", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: True)
def update_status(call):
    order_id = call.data.split('_')[-1]
    new_status = "В роботі" if "work" in call.data else "Завершені"
    
    cursor = db.cursor()
    cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    db.commit()
    
    bot.answer_callback_query(call.id, f"Статус: {new_status}")
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=f"✅ Замовлення №{order_id} змінено на: {new_status}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
