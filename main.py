import telebot
from flask import Flask, request
from telebot import types
import sqlite3

# --- НАЛАШТУВАННЯ ---
TOKEN = '7966376299:AAHSS27wP8x_x25jamUzZLxF9ocpvwXV2II'
AUTH_PASSWORD = 'pentagon2025'  # Пароль, який власник дає працівникам
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Ініціалізація бази даних
def init_db():
    conn = sqlite3.connect('orders.db', check_same_thread=False)
    cursor = conn.cursor()
    # Таблиця замовлень
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, quantity TEXT, status TEXT)''')
    # Таблиця працівників (зберігаємо їхні Chat ID)
    cursor.execute('''CREATE TABLE IF NOT EXISTS workers (chat_id INTEGER PRIMARY KEY)''')
    conn.commit()
    return conn

db = init_db()

# Функція для розсилки всім зареєстрованим працівникам
def notify_workers(text):
    cursor = db.cursor()
    cursor.execute("SELECT chat_id FROM workers")
    workers = cursor.fetchall()
    for worker in workers:
        try:
            bot.send_message(worker[0], text, parse_mode="Markdown")
        except:
            pass # Якщо працівник заблокував бота

# Прийом замовлення з Tilda
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.form.to_dict()
    name = data.get('Name', 'Невідомо')
    phone = data.get('Phone', 'Немає')
    quantity = data.get('quantity', '1 шт')

    cursor = db.cursor()
    cursor.execute("INSERT INTO orders (name, phone, quantity, status) VALUES (?, ?, ?, 'Активне')", 
                   (name, phone, quantity))
    db.commit()
    order_id = cursor.lastrowid

    msg = f"📦 *Нове замовлення №{order_id}*\n👤 {name}\n📞 {phone}\n🔢 Кількість: {quantity}"
    notify_workers(msg)
    return "OK", 200

# Реєстрація працівника за паролем
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Вітаю! Введіть пароль доступу, щоб стати модератором замовлень:")

@bot.message_handler(func=lambda m: m.text == AUTH_PASSWORD)
def auth(message):
    cursor = db.cursor()
    cursor.execute("INSERT OR IGNORE INTO workers (chat_id) VALUES (?)", (message.chat.id,))
    db.commit()
    bot.send_message(message.chat.id, "✅ Ви зареєстровані! Тепер ви отримуватимете нові замовлення.")

# Команда для видалення себе зі списку працівників
@bot.message_handler(commands=['logout'])
def logout(message):
    cursor = db.cursor()
    cursor.execute("DELETE FROM workers WHERE chat_id=?", (message.chat.id,))
    db.commit()
    bot.send_message(message.chat.id, "❌ Ви більше не отримуватимете замовлення.")

# Перегляд замовлень
@bot.message_handler(commands=['orders'])
def show_orders(message):
    # Перевірка, чи це працівник
    cursor = db.cursor()
    cursor.execute("SELECT chat_id FROM workers WHERE chat_id=?", (message.chat.id,))
    if not cursor.fetchone():
        bot.send_message(message.chat.id, "У вас немає доступу.")
        return

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
