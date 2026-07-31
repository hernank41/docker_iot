import logging
import os
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from handlers.common import (
    start_command,
    role_callback_handler,
    login_command,
    login_operario_command,
    logout_command
)
from handlers.admin import (
    admin_callback_handler,
    admin_text_input_handler
)
from handlers.operario import (
    operario_callback_handler,
    recibir_comentario_handler
)

logging.basicConfig(
    format='%(asctime)s - [Telegram Bot] - %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8684338338:AAGSiGXsVvbAmkYqnL7X8wwlVnouglWU2mo")

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router para capturar texto del usuario según el estado activo."""
    if context.user_data.get("esperando_accion"):
        await admin_text_input_handler(update, context)
    elif context.user_data.get("esperando_comentario_actividad_id"):
        await recibir_comentario_handler(update, context)

def main():
    logging.info(f"Iniciando Bot de Telegram: Kisiel_iot_bot...")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Registros de Comandos Comunes
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("login", login_command))
    app.add_handler(CommandHandler("login_operario", login_operario_command))
    app.add_handler(CommandHandler("logout", logout_command))

    # Handlers de Selección de Rol e Inicio de Sesión
    app.add_handler(CallbackQueryHandler(role_callback_handler, pattern="^(role_|login_op_|show_)"))

    # Handlers de Menú de Administración
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^(admin_|menu_|reporte_|edit_cfg_|logout_session)"))

    # Handlers de Menú de Operario
    app.add_handler(CallbackQueryHandler(operario_callback_handler, pattern="^(op_|asig_|select_|instalar_)"))

    # Router de Entrada de Texto Interactivo
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logging.info("Bot de Telegram inicializado y escuchando eventos en tiempo real.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
