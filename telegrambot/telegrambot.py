from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os, aiomysql

token=os.environ["TB_TOKEN"]

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def sin_autorizacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("intento de conexión de: " + str(update.message.from_user.id))
    logging.info(context.application.handlers[0][0].filters.or_filter.inv_filter.user_ids)
    sql = "SELECT telegram_id FROM autorizados"
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306,
                                    user=os.environ["MARIADB_USER"],
                                    password=os.environ["MARIADB_USER_PASS"],
                                    db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        r = await cur.fetchall()
        context.application.handlers[0][0].filters.or_filter.inv_filter.user_ids = set([int(row[0]) for row in r])
        if update.effective_chat.id in context.application.handlers[0][0].filters.or_filter.inv_filter.user_ids:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="ahora está autorizado")
            await start(update, context)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="no autorizado")
    await cur.close()
    conn.close()
    logging.info(context.application.handlers[0][0].filters.or_filter.inv_filter.user_ids)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("se conectó: " + str(update.message.from_user.id))
    if update.message.from_user.first_name:
        nombre=update.message.from_user.first_name
    else:
        nombre=""
    if update.message.from_user.last_name:
        apellido=update.message.from_user.last_name
    else:
        apellido=""
    await context.bot.send_message(update.message.chat.id, text="Bienvenido al Bot "+ nombre + " " + apellido)
    # await update.message.reply_text("Bienvenido al Bot "+ nombre + " " + apellido) # también funciona

async def acercade(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="Este bot fue creado para el curso de IoT FIO")

def main():
    application = Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.ALL | ~filters.User(), sin_autorizacion))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('acercade', acercade))
    application.run_polling()

if __name__ == '__main__':
    main()
