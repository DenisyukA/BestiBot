import telebot
from flask import Flask, request
from telebot import types
import sqlite3
import os

# --- НАЛАШТУВАННЯ ---
TOKEN = '7966376299:AAFXhIYp7msvOSiLI7Ve1BdrOX74JMJlZoM'
AUTH_PASSWORD = 'pentagon2025'
ADMIN_ID = 806035065 
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

def init_db():
    conn = sqlite3.connect('orders.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, quantity TEXT, status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS workers (chat_id INTEGER PRIMARY KEY, approved INTEGER DEFAULT 0)''')
    
    # АВТО-ФІКС: Виправляємо старі статуси, щоб кнопки їх бачили
    cursor.execute("UPDATE orders SET status='Активні' WHERE status='Активне'")
    conn.commit()
    return conn

db = init_db()

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return "OK", 200
    return "Forbidden", 403

@app.route('/tilda-webhook', methods=['POST'])
def tilda_webhook():
    data = request.get_json() if request.is_json else request.form.to_dict()
    name = data.get('Name', data.get('name', 'Невідомо'))
    phone = data.get('Phone', data.get('phone', 'Немає'))
    quantity = data.get('quantity', '1 шт')
    
    cursor = db.cursor()
    cursor.execute("INSERT INTO orders (name, phone, quantity, status) VALUES (?, ?, ?, 'Активні')", (name, phone, quantity))
    db.commit()
    
    msg = f"📦 *Нове замовлення №{cursor.lastrowid}*\n👤 {name}\n📞 {phone}\n🔢 {quantity}"
    cursor.execute("SELECT chat_id FROM workers WHERE approved=1")
    for worker in cursor.fetchall():
        try: bot.send_message(worker[0], msg, parse_mode="Markdown")
        except: pass
    return "OK", 200

# --- ЛОГІКА БОТА ---

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Вітаю! Введіть пароль доступу:")

@bot.message_handler(func=lambda m: m.text == AUTH_PASSWORD)
def request_access(message):
    user = message.from_user
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Дозволити", callback_data=f"appr_{message.chat.id}"))
    kb.add(types.InlineKeyboardButton("❌ Відмовити", callback_data=f"deny_{message.chat.id}"))
    bot.send_message(ADMIN_ID, f"🔔 *Запит на доступ!*\nКористувач: @{user.username}\nID: {message.chat.id}", parse_mode="Markdown", reply_markup=kb)
    bot.send_message(message.chat.id, "⏳ Пароль вірний. Запит надіслано адміну (Артему).")

@bot.callback_query_handler(func=lambda call: True)
def handle_queries(call):
    cursor = db.cursor()
    if call.data.startswith('appr_'):
        uid = call.data.split('_')[1]
        cursor.execute("INSERT OR REPLACE INTO workers (chat_id, approved) VALUES (?, 1)", (uid, 1))
        db.commit()
        bot.send_message(uid, "🎉 Ваш доступ підтверджено!")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Мої замовлення")
        bot.send_message(uid, "Робоче меню:", reply_markup=markup)
    
    elif call.data.startswith('set_'):
        oid = call.data.split('_')[-1]
        new_status = "В роботі" if "work" in call.data else "Завершені"
        cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, oid))
        db.commit()
        bot.edit_message_text(f"✅ Замовлення №{oid} -> {new_status}", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text in ["📦 Мої замовлення", "🔙 Назад"])
def menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Активні", "В роботі", "Завершені")
    bot.send_message(message.chat.id, "Оберіть категорію:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Активні", "В роботі", "Завершені"])
def show_orders(message):
    cursor = db.cursor()
    cursor.execute("SELECT id, name, phone FROM orders WHERE status=?", (message.text,))
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, f"У категорії '{message.text}' порожньо.")
        return
    for row in rows:
        kb = types.InlineKeyboardMarkup()
        if message.text == "Активні": kb.add(types.InlineKeyboardButton("Взяти", callback_data=f"set_work_{row[0]}"))
        elif message.text == "В роботі": kb.add(types.InlineKeyboardButton("Завершити", callback_data=f"set_done_{row[0]}"))
        bot.send_message(message.chat.id, f"🆔 {row[0]} | 👤 {row[1]}\n📞 {row[2]}", reply_markup=kb)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
