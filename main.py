import telebot
from flask import Flask, request
from telebot import types
import sqlite3

# --- НАЛАШТУВАННЯ ---
TOKEN = 'ТВІЙ_ТГ_ТОКЕН'
ADMIN_ID = 'ТВІЙ_CHAT_ID' # Бот писатиме сюди
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Ініціалізація бази даних
def init_db():
    conn = sqlite3.connect('orders.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, quantity TEXT, status TEXT)''')
    conn.commit()
    return conn

db = init_db()

# Прийом замовлення з Tilda
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.form.to_dict() # Tilda шле дані як форму
    name = data.get('Name', 'Невідомо')
    phone = data.get('Phone', 'Немає')
    quantity = data.get('quantity', '1 шт') # Поле зі скріншоту

    cursor = db.cursor()
    cursor.execute("INSERT INTO orders (name, phone, quantity, status) VALUES (?, ?, ?, 'Активне')", 
                   (name, phone, quantity))
    db.commit()
    order_id = cursor.lastrowid

    msg = f"📦 *Нове замовлення №{order_id}*\n👤 {name}\n📞 {phone}\n🔢 Кількість: {quantity}\n📍 Статус: Активне"
    bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
    return "OK", 200

# Перегляд замовлень через ТГ
@bot.message_handler(commands=['start', 'orders'])
def show_orders(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Активні", "В роботі", "Завершені")
    bot.send_message(message.chat.id, "Виберіть фільтр замовлень:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Активні", "В роботі", "Завершені"])
def filter_orders(message):
    cursor = db.cursor()
    cursor.execute("SELECT id, name, phone FROM orders WHERE status=?", (message.text,))
    rows = cursor.fetchall()
    
    if not rows:
        bot.send_message(message.chat.id, f"Замовлень у статусі '{message.text}' немає.")
        return

    for row in rows:
        kb = types.InlineKeyboardMarkup()
        if message.text == "Активні":
            kb.add(types.InlineKeyboardButton("Взяти в роботу", callback_data=f"set_work_{row[0]}"))
        elif message.text == "В роботі":
            kb.add(types.InlineKeyboardButton("Завершити", callback_data=f"set_done_{row[0]}"))
        
        bot.send_message(message.chat.id, f"🆔 {row[0]} | {row[1]} | {row[2]}", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: True)
def update_status(call):
    order_id = call.data.split('_')[-1]
    new_status = "В роботі" if "work" in call.data else "Завершені"
    
    cursor = db.cursor()
    cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    db.commit()
    
    bot.answer_callback_query(call.id, f"Статус змінено на {new_status}")
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=f"✅ Замовлення №{order_id} переведено в: {new_status}")

if __name__ == "__main__":
    import threading
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host="0.0.0.0", port=5000)