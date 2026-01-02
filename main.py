import telebot
from flask import Flask, request
from telebot import types
import sqlite3
import os

# --- НАЛАШТУВАННЯ ---
TOKEN = '7966376299:AAFXhIYp7msvOSiLI7Ve1BdrOX74JMJlZoM'
AUTH_PASSWORD = 'pentagon2025'         # Пароль для працівників
ADMIN_ID = 806035065                   
OLGA_ID = 366380521                    # ID Ольги (Замовник/Власник)

app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

def init_db():
    conn = sqlite3.connect('orders.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, quantity TEXT, status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS workers (chat_id INTEGER PRIMARY KEY, username TEXT, approved INTEGER DEFAULT 0)''')
    
    # Твій доступ (Технічний адмін)
    cursor.execute("INSERT OR REPLACE INTO workers (chat_id, username, approved) VALUES (?, 'Technical_Admin', 1)", (ADMIN_ID,))
    # Доступ Ольги (Власник - рівень 2)
    cursor.execute("INSERT OR REPLACE INTO workers (chat_id, username, approved) VALUES (?, 'Owner_Olga', 2)", (OLGA_ID,))
    
    cursor.execute("UPDATE orders SET status='Активні' WHERE status='Активне'")
    conn.commit()
    return conn

db = init_db()

# --- WEBHOOKS (без змін) ---
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
    cursor = db.cursor()
    cursor.execute("INSERT INTO orders (name, phone, quantity, status) VALUES (?, ?, ?, 'Активні')", 
                   (data.get('Name', 'Невідомо'), data.get('Phone', 'Немає'), data.get('quantity', '1 шт')))
    db.commit()
    
    msg = f"📦 *Нове замовлення №{cursor.lastrowid}*\n👤 {data.get('Name')}\n📞 {data.get('Phone')}"
    cursor.execute("SELECT chat_id FROM workers WHERE approved >= 1")
    for worker in cursor.fetchall():
        try: bot.send_message(worker[0], msg, parse_mode="Markdown")
        except: pass
    return "OK", 200

# --- ЛОГІКА БОТА ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    # Перевіряємо, чи це Ольга або Артем
    if uid == OLGA_ID:
        bot.send_message(uid, "👑 Вітаю, Ольго! Система впізнала вас як Власника.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Мої замовлення"))
        return
    
    if uid == ADMIN_ID:
        bot.send_message(uid, "🛠 Вітаю, Артеме! Ти в адмін-панелі.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Мої замовлення"))
        return

    # Для інших — стандартний запит пароля
    bot.send_message(ADMIN_ID, f"🎯 Хтось зайшов у бот!\nІм'я: {message.from_user.first_name}\nID: `{uid}`", parse_mode="Markdown")
    bot.send_message(uid, "Вітаю в системі Пентагон! Введіть пароль доступу:")

@bot.message_handler(commands=['admin'])
def admin_list(message):
    cursor = db.cursor()
    cursor.execute("SELECT approved FROM workers WHERE chat_id=?", (message.chat.id,))
    res = cursor.fetchone()
    # Доступ до керування мають Артем (ADMIN_ID) та Ольга (approved == 2)
    if message.chat.id == ADMIN_ID or (res and res[0] == 2):
        cursor.execute("SELECT chat_id, username FROM workers WHERE approved=1")
        workers = cursor.fetchall()
        if not workers:
            bot.send_message(message.chat.id, "У команді поки немає працівників.")
            return
        bot.send_message(message.chat.id, "👥 *Керування командою:*", parse_mode="Markdown")
        for w in workers:
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚫 Видалити", callback_data=f"fire_{w[0]}"))
            bot.send_message(message.chat.id, f"Працівник: @{w[1]} (ID: {w[0]})", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == AUTH_PASSWORD)
def auth(message):
    user = message.from_user
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Дозволити", callback_data=f"appr_{message.chat.id}_{user.username}"),
        types.InlineKeyboardButton("❌ Відхилити", callback_data=f"deny_{message.chat.id}")
    )
    # Сповіщаємо і Артема, і Ольгу про новий запит
    cursor = db.cursor()
    cursor.execute("SELECT chat_id FROM workers WHERE approved=2 OR chat_id=?", (ADMIN_ID,))
    admins = cursor.fetchall()
    for adm in admins:
        try: bot.send_message(adm[0], f"🔔 *Запит на доступ!*\n@{user.username} (ID: {message.chat.id})", parse_mode="Markdown", reply_markup=kb)
        except: pass
    bot.send_message(message.chat.id, "⏳ Пароль вірний. Очікуйте підтвердження від адміністрації.")

# --- РЕШТА ЛОГІКИ (callbacks та menu_logic) ЗАЛИШАЄТЬСЯ БЕЗ ЗМІН ---
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    cursor = db.cursor()
    if call.data.startswith('appr_'):
        _, uid, uname = call.data.split('_')
        cursor.execute("INSERT OR REPLACE INTO workers (chat_id, username, approved) VALUES (?, ?, 1)", (uid, uname, 1))
        db.commit()
        bot.send_message(uid, "🎉 Доступ надано!", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Мої замовлення"))
        bot.edit_message_text(f"✅ @{uname} доданий", call.message.chat.id, call.message.message_id)
    elif call.data.startswith('deny_'):
        uid = call.data.split('_')[1]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        try: bot.send_message(uid, "🚫 Вам відмовлено у доступі.")
        except: pass
    elif call.data.startswith('fire_'):
        uid = call.data.split('_')[1]
        cursor.execute("DELETE FROM workers WHERE chat_id=?", (uid,))
        db.commit()
        bot.send_message(uid, "🚫 Ваш доступ анульовано.")
        bot.edit_message_text(f"❌ Видалено ID: {uid}", call.message.chat.id, call.message.message_id)
    elif call.data.startswith('set_'):
        oid = call.data.split('_')[-1]
        new_status = "В роботі" if "work" in call.data else "Завершені"
        cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, oid))
        db.commit()
        bot.edit_message_text(f"✅ №{oid} -> {new_status}", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text in ["📦 Мої замовлення", "🔙 Назад", "Активні", "В роботі", "Завершені"])
def menu_logic(message):
    cursor = db.cursor()
    cursor.execute("SELECT approved FROM workers WHERE chat_id=?", (message.chat.id,))
    res = cursor.fetchone()
    if not res or res[0] == 0: return
    if message.text in ["📦 Мої замовлення", "🔙 Назад"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Активні", "В роботі", "Завершені")
        bot.send_message(message.chat.id, "Оберіть категорію:", reply_markup=markup)
    else:
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
