import logging, os, aiomysql, traceback, asyncio, locale
import matplotlib.pyplot as plt
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext
from io import BytesIO

import ssl, certifi, json, traceback
import aiomqtt

token=os.environ["TB_TOKEN"]

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)

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
    kb = [["Ultimos valores"],["Gráfico"],["Setear parametros"]]
    #kb = [["temperatura"],["humedad"],["gráfico temperatura"],["gráfico humedad"]]
    await context.bot.send_message(update.message.chat.id, text="Bienvenido al Bot "+ nombre + " " + apellido,reply_markup=ReplyKeyboardMarkup(kb))
    # await update.message.reply_text("Bienvenido al Bot "+ nombre + " " + apellido) # también funciona


async def ultimos_valores(update: Update, context: CallbackContext):
    kb = [["temperatura"],["humedad"],["Volver"]]
    await context.bot.send_message(update.message.chat.id, text="Here's the updated keyboard.", reply_markup=ReplyKeyboardMarkup(kb))

async def volver(update: Update, context: CallbackContext):
    kb = [["Ultimos valores"],["Gráfico"],["Setear parametros"]]
    await context.bot.send_message(update.message.chat.id, text="Here's the updated keyboard.", reply_markup=ReplyKeyboardMarkup(kb))

    
async def mostrar_graficos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["gráfico temperatura"],["gráfico humedad"]]
    await context.bot.send_message(reply_markup=ReplyKeyboardMarkup(kb))

async def setear_parametros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["setear"],["volver"]]
    await context.bot.send_message(reply_markup=ReplyKeyboardMarkup(kb))

async def acercade(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="Este bot fue creado para el curso de IoT FIO")

async def kill(update: Update, context):
    logging.info(context.args)
    if context.args and context.args[0] == '@e':
        await context.bot.send_animation(update.message.chat.id, "CgACAgQAAxkBAAMRZk-SS3Frzijvi_gVgHxe0plv3AUAAq4EAAJYom1S72dC_CPRrwM1BA")
        await asyncio.sleep(6)
        await context.bot.send_message(update.message.chat.id, text="¡¡¡Ahora estan todos muertos!!!")
    else:
        await context.bot.send_message(update.message.chat.id, text="☠️ ¡¡¡Esto es muy peligroso!!! ☠️")

async def graficos(update: Update, context):
    logging.info(update.message.text)
    sql = f"SELECT timestamp, {update.message.text.split()[1]} FROM mediciones where id mod 2 = 0 AND timestamp >= NOW() - INTERVAL 1 DAY ORDER BY timestamp"
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306,
                                    user=os.environ["MARIADB_USER"],
                                    password=os.environ["MARIADB_USER_PASS"],
                                    db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        filas = await cur.fetchall()

        fig, ax = plt.subplots(figsize=(7, 4))
        fecha,var=zip(*filas)
        ax.plot(fecha,var)
        ax.grid(True, which='both')
        ax.set_title(update.message.text, fontsize=14, verticalalignment='bottom')
        ax.set_xlabel('fecha')
        ax.set_ylabel('unidad')

        buffer = BytesIO()
        fig.tight_layout()
        fig.savefig(buffer, format='png')
        buffer.seek(0)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=buffer)
    conn.close()

async def kill(update: Update, context):
    logging.info(context.args)
    if context.args and context.args[0] == '@e':
        await context.bot.send_animation(update.message.chat.id, "CgACAgEAAxkBAANXZAiWvDIEfGNVzodgTgH1o5z3_WEAAmUCAALrx0lEZ8ytatzE5X0uBA")
        await asyncio.sleep(6)
        await context.bot.send_message(update.message.chat.id, text="¡¡¡Ahora estan todos muertos!!!")
    else:
        await context.bot.send_message(update.message.chat.id, text="☠️ ¡¡¡Esto es muy peligroso!!! ☠️")

async def medicion(update: Update, context):
    logging.info(update.message.text)
    sql = f"SELECT timestamp, {update.message.text} FROM mediciones ORDER BY timestamp DESC LIMIT 1"
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306,
                                    user=os.environ["MARIADB_USER"],
                                    password=os.environ["MARIADB_USER_PASS"],
                                    db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        r = await cur.fetchone()
        if update.message.text == 'temperatura':
            unidad = 'ºC'
        else:
            unidad = '%'
        await context.bot.send_message(update.message.chat.id,
                                    text="La última {} es de {} {},\nregistrada a las {:%H:%M:%S %d/%m/%Y}"
                                    .format(update.message.text, str(r[1]).replace('.',','), unidad, r[0]))
        logging.info("La última {} es de {} {}, medida a las {:%H:%M:%S %d/%m/%Y}".format(update.message.text, r[1], unidad, r[0]))
    conn.close()

async def setear(update: Update, context):
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()
    async with aiomqtt.Client(
        os.environ["SERVIDOR"],
        username=os.environ["MQTT_USR"],
        password=os.environ["MQTT_PASS"],
        port=int(os.environ["PUERTO_MQTTS"]),
        tls_context=tls_context,
    ) as client:
        mensaje = update.message.text
        try:
            words = mensaje.split()
            topico = words[0]
            parametro = words[1]
        
            logging.info(mensaje)
            if(topico == "setpoint"):
                try:
                    parametro = float(parametro)
                    await client.publish(topic="iot/2024/24dcc399d76c/" + topico, payload=parametro , qos=1)
                    await context.bot.send_message(update.message.chat.id, text="El setpoint se seteo en {}".format(parametro))
                except ValueError:
                    logging.info("Parametro incorrecto")
                    await context.bot.send_message(update.message.chat.id, text="Parametro incorrecto")
            else:
                logging.info("Formato incorrecto")
                await context.bot.send_message(update.message.chat.id, text="Formato incorrecto")
        except IndexError:
            logging.info("Formato incorrecto")
            await context.bot.send_message(update.message.chat.id, text="Formato incorrecto")
        except UnboundLocalError:
            logging.info("Formato incorrecto")
            await context.bot.send_message(update.message.chat.id, text="Formato incorrecto")
async def setear2(update: Update, context):
    logging.info(update.message.text)
    await context.bot.send_message(update.message.chat.id,
                text="Setpoint")
    client=mqtt.Client()
    client.tls_set()
    client.username_pw_set(username="kisiel", password="41995095")
    client.subscribe("iot/2024/24dcc399d76c/setpoint ")
    client.publish("iot/2024/24dcc399d76c", "setpoint")

async def graficos(update: Update, context):
    logging.info(update.message.text)
    sql = f"SELECT timestamp, {update.message.text.split()[1]} FROM mediciones where id mod 2 = 0 AND timestamp >= NOW() - INTERVAL 1 DAY ORDER BY timestamp"
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306,
                                    user=os.environ["MARIADB_USER"],
                                    password=os.environ["MARIADB_USER_PASS"],
                                    db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        filas = await cur.fetchall()

        fig, ax = plt.subplots(figsize=(7, 4))
        fecha,var=zip(*filas)
        ax.plot(fecha,var)
        ax.grid(True, which='both')
        ax.set_title(update.message.text, fontsize=14, verticalalignment='bottom')
        ax.set_xlabel('fecha')
        ax.set_ylabel('unidad')

        buffer = BytesIO()
        fig.tight_layout()
        fig.savefig(buffer, format='png')
        buffer.seek(0)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=buffer)
    conn.close()


def main():
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('acercade', acercade))
    application.add_handler(CommandHandler('kill', kill))
    application.add_handler(MessageHandler(filters.Regex("Ultimos valores$"), ultimos_valores))
    application.add_handler(MessageHandler(filters.Regex("Volver$"), volver))
    application.add_handler(MessageHandler(filters.Regex("Gráfico$"), mostrar_graficos))
    application.add_handler(MessageHandler(filters.Regex("Setear parametros$"), setear_parametros))
    application.add_handler(MessageHandler(filters.Regex("*.setear.*$"), setear))
    application.add_handler(MessageHandler(filters.Regex("^(temperatura|humedad)$"), medicion))
    application.add_handler(MessageHandler(filters.Regex("^(gráfico temperatura|gráfico humedad)$"), graficos))
    application.run_polling()
'''
# Define configuration
config['ssl'] = True

# Set up client
MQTTClient.DEBUG = True  # Optional
client = MQTTClient(config)
'''
if __name__ == '__main__':
    main()
