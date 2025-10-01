import os
import logging
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Flask ---
app = Flask(__name__)

# --- Этапы разговора ---
NAME, APARTMENT, QUESTIONS, BREAKAGE, BREAKAGE_PHOTO, BREAKAGE_DESC, END = range(7)

# --- Данные ---
apartments = [
    "9к3-27", "9к3-28", "9к3-29", "9к3-78", "13-51", "11с1-347", "5.-4",
    "42-1", "42-52", "42-105", "42-144", "3-174", "3-334", "3-852",
    "69к5-138", "7к1-348", "73к5-751", "73к5-752"
]

questions = [
    "Протерли пыль на подоконниках?",
    "Пропарили белье?",
    "Поменяли водичку в ершиках?"
]

yes_no_keyboard = ReplyKeyboardMarkup([["Да", "Нет"]], one_time_keyboard=True)
breakage_keyboard = ReplyKeyboardMarkup([["Да", "Нет"]], one_time_keyboard=True)
apartment_keyboard = ReplyKeyboardMarkup(
    [apartments[i:i+3] for i in range(0, len(apartments), 3)],
    one_time_keyboard=True
)

# --- Токен и канал ---
TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = os.environ.get("CHANNEL_ID")

# --- Telegram Application ---
application = Application.builder().token(TOKEN).build()

# --- Функции бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Команда /start от {update.effective_user.id}")
    await update.message.reply_text("Привет! Введите Фамилию и Имя:")
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.strip():
        await update.message.reply_text("Пожалуйста, введите корректное имя:")
        return NAME
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Выберите квартиру:", reply_markup=apartment_keyboard)
    return APARTMENT

async def apartment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_apartment = update.message.text
    if selected_apartment not in apartments:
        await update.message.reply_text("Пожалуйста, выберите квартиру из списка:", reply_markup=apartment_keyboard)
        return APARTMENT
    context.user_data['apartment'] = selected_apartment
    context.user_data['answers'] = {}
    context.user_data['q_index'] = 0
    await update.message.reply_text(questions[0], reply_markup=yes_no_keyboard)
    return QUESTIONS

async def questions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['q_index']
    context.user_data['answers'][questions[idx]] = update.message.text
    context.user_data['q_index'] += 1
    if context.user_data['q_index'] < len(questions):
        await update.message.reply_text(questions[context.user_data['q_index']], reply_markup=yes_no_keyboard)
        return QUESTIONS
    else:
        await update.message.reply_text("Были ли поломки?", reply_markup=breakage_keyboard)
        return BREAKAGE

async def breakage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['breakage'] = update.message.text
    if update.message.text.lower() == "да":
        await update.message.reply_text("Пришлите фото поломки")
        return BREAKAGE_PHOTO
    else:
        return await end(update, context)

async def breakage_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = update.message.photo[-1]
    context.user_data['breakage_photo'] = photo_file.file_id
    await update.message.reply_text("Опишите поломку:")
    return BREAKAGE_DESC

async def breakage_photo_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, пришлите фото поломки.")
    return BREAKAGE_PHOTO

async def breakage_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['breakage_desc'] = update.message.text
    return await end(update, context)

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = f"Новый отчет:\n\nИмя: {context.user_data['name']}\nКвартира: {context.user_data['apartment']}\n\n"
    for q, a in context.user_data['answers'].items():
        message += f"{q} - {a}\n"
    message += f"Поломки: {context.user_data.get('breakage', 'Нет')}\n"

    try:
        if context.user_data.get('breakage') == "Да":
            await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=context.user_data['breakage_photo'],
                caption=message + f"\nОписание: {context.user_data.get('breakage_desc', '')}"
            )
        else:
            await context.bot.send_message(chat_id=CHANNEL, text=message)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при отправке отчета: {str(e)}. Попробуйте позже.")
        return ConversationHandler.END

    await update.message.reply_text("Спасибо! Ваш отчет отправлен.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# --- Conversation Handler ---
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        APARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, apartment)],
        QUESTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, questions_handler)],
        BREAKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, breakage)],
        BREAKAGE_PHOTO: [
            MessageHandler(filters.PHOTO, breakage_photo),
            MessageHandler(filters.ALL & ~filters.PHOTO, breakage_photo_invalid)
        ],
        BREAKAGE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, breakage_desc)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
application.add_handler(conv_handler)

# --- Webhook для Render с логированием ---
@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    logging.info(f"Получено обновление: {data}")  # <-- важное для проверки
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return "ok", 200

@app.route("/")
def index():
    return "🤖 Бот работает через Render!", 200

# --- Запуск Flask ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
