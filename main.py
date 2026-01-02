import telebot
from flask import Flask, request
from telebot import types
import psycopg2
from psycopg2.extras import DictCursor
import os

# --- НАЛАШТУВАННЯ ---
TOKEN = '7966376299:AAFXhIYp7msvOSiLI7Ve1BdrOX74JMJlZoM'
AUTH_PASSWORD = 'pentagon2025'
ADMIN_ID = 806035065                   
OLGA_ID = 366380521                    

# URL твоєї бази із секретних змінних Render
DATABASE_URL = os.environ.get('DATABASE_URL') 

app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Функція для підключення до PostgreSQL
def get_db():
    # sslmode='require' обов'язковий для підключення до Supabase
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# Створення таблиць при запуску
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблиця замовлень (SERIAL для автоінкременту)
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (id SERIAL PRIMARY KEY, name TEXT, phone TEXT, quantity TEXT, status TEXT)''')
    
    # Таблиця працівників (BIGINT для ID телеграма)
    cursor.execute('''CREATE TABLE IF NOT EXISTS workers 
                      (chat_id BIGINT PRIMARY KEY, username TEXT, approved INTEGER DEFAULT 0)''')
    
    # Автоматична реєстрація тебе та Ольги
    cursor.execute("""INSERT INTO workers (chat_id, username, approved) 
                      VALUES (%s, %s, 1) ON CONFLICT (chat_id) DO UPDATE SET approved=1""", (ADMIN_ID, 'Technical_Admin'))
    cursor.execute("""INSERT INTO workers (chat_id, username, approved) 
                      VALUES (%s, %s, 2) ON CONFLICT (chat_id) DO UPDATE SET approved=2""", (OLGA_ID, 'Owner_Olga'))
    
    conn.commit()
    cursor.close()
    conn.close()

# Запускаємо ініціалізацію
init_db()

# --- WEBHOOKS ---
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
    conn = get_db()
    cursor = conn.cursor()
    
    # Вставляємо замовлення і отримуємо його новий ID
    cursor.execute("INSERT INTO orders (name, phone, quantity, status) VALUES (%s, %s, %s, 'Активні') RETURNING id", 
                   (data.get('Name', 'Невідомо'), data.get('Phone', 'Немає'), data.get('quantity', '1 шт')))
    order_id = cursor.fetchone()[0]
    conn.commit()
    
    msg = f"📦 *Нове замовлення №{order_id}*\n👤 {data.get('Name', 'Невідомо')}\n📞 {data.get('Phone', 'Немає')}"
    
    # Розсилаємо всім схваленим працівникам
    cursor.execute("SELECT chat_id FROM workers WHERE approved >= 1")
    workers = cursor.fetchall()
    for worker in workers:
        try: bot.send_message(worker[0], msg, parse_mode="Markdown")
        except: pass
    
    cursor.close()
    conn.close()
    return "OK", 200

# --- КОМАНДИ ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    if uid == OLGA_ID:
        bot.send_message(uid, "👑 Вітаю, Ольго! Ви в системі як Власник.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Мої замовлення"))
        return
    
    if uid == ADMIN_ID:
        bot.send_message(uid, "🛠 Вітаю, Артеме! Ти в адмін-панелі.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Мої замовлення"))
        return

    bot.send_message(ADMIN_ID, f"🎯 Хтось зайшов у бот!\nІм'я: {message.from_user.first_name}\nID: `{uid}`", parse_mode="Markdown")
    bot.send_message(uid, "Вітаю в системі Пентагон! Введіть пароль доступу:")

@bot.message_handler(commands=['admin'])
def admin_list(message):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT approved FROM workers WHERE chat_id=%s", (message.chat.id,))
    res = cursor.fetchone()
    
    if message.chat.id == ADMIN_ID or (res and res[0] == 2):
        cursor.execute("SELECT chat_id, username FROM workers WHERE approved=1")
        workers = cursor.fetchall()
        if not workers:
            bot.send_message(message.chat.id, "У команді поки немає працівників.")
        else:
            bot.send_message(message.chat.id, "👥 *Керування командою:*", parse_mode="Markdown")
            for w in workers:
                kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚫 Видалити", callback_data=f"fire_{w[0]}"))
                bot.send_message(message.chat.id, f"Працівник: @{w[1]} (ID: {w[0]})", reply_markup=kb)
    
    cursor.close()
    conn.close()

@bot.message_handler(func=lambda m: m.text == AUTH_PASSWORD)
def auth(message):
    user = message.from_user
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Дозволити", callback_data=f"appr_{message.chat.id}_{user.username}"),
        types.InlineKeyboardButton("❌ Відхилити", callback_data=f"deny_{message.chat.id}")
    )
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM workers WHERE approved=2 OR chat_id=%s", (ADMIN_ID,))
    admins = cursor.fetchall()
    for adm in admins:
        try: bot.send_message(adm[0], f"🔔 *Запит на доступ!*\n@{user.username} (ID: {message.chat.id})", parse_mode="Markdown", reply_markup=kb)
        except: pass
    
    bot.send_message(message.chat.id, "⏳ Пароль вірний. Очікуйте підтвердження.")
    cursor.close()
    conn.close()

# --- ОБРОБКА КНОПОК (CALLBACKS) ---
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    conn = get_db()
    cursor = conn.cursor()
    
    if call.data.startswith('appr_'):
        _, uid, uname = call.data.split('_')
        cursor.execute("INSERT INTO workers (chat_id, username, approved) VALUES (%s, %s, 1) ON CONFLICT (chat_id) DO UPDATE SET approved=1", (uid, uname))
        conn.commit()
        bot.send_message(uid, "🎉 Доступ надано!", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📦 Мої замовлення"))
        bot.edit_message_text(f"✅ @{uname} доданий", call.message.chat.id, call.message.message_id)

    elif call.data.startswith('fire_'):
        uid = call.data.split('_')[1]
        cursor.execute("DELETE FROM workers WHERE chat_id=%s", (int(uid),))
        conn.commit()
        bot.send_message(uid, "🚫 Ваш доступ анульовано.")
        bot.edit_message_text(f"❌ Видалено ID: {uid}", call.message.chat.id, call.message.message_id)

    elif call.data.startswith('set_'):
        oid = call.data.split('_')[-1]
        new_status = "В роботі" if "work" in call.data else "Завершені"
        cursor.execute("UPDATE orders SET status=%s WHERE id=%s", (new_status, int(oid)))
        conn.commit()
        bot.edit_message_text(f"✅ №{oid} -> {new_status}", call.message.chat.id, call.message.message_id)

    elif call.data.startswith('deny_'):
        uid = call.data.split('_')[1]
        bot.delete_message(call.message.chat.id, call.message.message_id)
        try: bot.send_message(uid, "🚫 Вам відмовлено у доступі.")
        except: pass

    cursor.close()
    conn.close()

# --- МЕНЮ ТА ЗАМОВЛЕННЯ ---
@bot.message_handler(func=lambda m: m.text in ["📦 Мої замовлення", "🔙 Назад", "Активні", "В роботі", "Завершені"])
def menu_logic(message):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT approved FROM workers WHERE chat_id=%s", (message.chat.id,))
    res = cursor.fetchone()
    
    if not res or res[0] == 0: 
        cursor.close()
        conn.close()
        return

    if message.text in ["📦 Мої замовлення", "🔙 Назад"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Активні", "В роботі", "Завершені")
        bot.send_message(message.chat.id, "Оберіть категорію:", reply_markup=markup)
    else:
        cursor.execute("SELECT id, name, phone FROM orders WHERE status=%s ORDER BY id DESC", (message.text,))
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(message.chat.id, f"У категорії '{message.text}' порожньо.")
        else:
            for row in rows:
                kb = types.InlineKeyboardMarkup()
                if message.text == "Активні": kb.add(types.InlineKeyboardButton("Взяти", callback_data=f"set_work_{row[0]}"))
                elif message.text == "В роботі": kb.add(types.InlineKeyboardButton("Завершити", callback_data=f"set_done_{row[0]}"))
                bot.send_message(message.chat.id, f"🆔 {row[0]} | 👤 {row[1]}\n📞 {row[2]}", reply_markup=kb)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
