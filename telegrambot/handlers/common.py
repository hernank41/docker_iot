from telegram import Update
from telegram.ext import ContextTypes
from services.api_client import api_client
from keyboards.inline import (
    get_admin_menu_keyboard,
    get_operario_menu_keyboard,
    get_role_select_keyboard,
    get_operarios_login_keyboard
)
import os

async def safe_edit_or_reply(query, text: str, reply_markup=None, parse_mode="Markdown"):
    """Edita el mensaje si es posible, o envía uno nuevo."""
    try:
        if query.message and (query.message.photo or not query.message.text):
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        try:
            await query.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception:
            pass

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id
    
    # Verificar si el usuario ya está autenticado en la sesión activa
    if context.user_data.get("role"):
        rol = context.user_data["role"]
        username = context.user_data.get("username", "")
        if rol == "ADMIN":
            msg = f"👋 ¡Hola **{username}**! Conectado como **Administrador**.\nUtilice el menú inferior para gestionar el sistema."
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_admin_menu_keyboard())
            return
        else:
            msg = f"👋 ¡Bienvenido **{username}**! Conectado como **Operario**.\nSeleccione una opción para operar en planta:"
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_operario_menu_keyboard())
            return

    # Si no hay sesión activa, mostrar selección interactiva de rol
    msg = (
        f"👋 ¡Hola {user.first_name}!\n\n"
        f"Bienvenido al sistema **Industrial IoT Stack** (`Kisiel_iot_bot`).\n"
        f"Por favor, seleccione su **Rol de Usuario** para iniciar sesión:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_role_select_keyboard())

async def role_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ["show_role_select", "show_start"]:
        context.user_data.clear()
        msg = "👋 Bienvenido al sistema **Industrial IoT Stack**. Seleccione su rol:"
        await safe_edit_or_reply(query, msg, reply_markup=get_role_select_keyboard())

    elif data == "role_login_admin":
        msg = (
            "👑 **AUTENTICACIÓN DE ADMINISTRADOR**\n\n"
            "Por favor, envíe sus credenciales ejecutando el comando:\n"
            "`/login <usuario> <contraseña>`\n\n"
            "Ejemplo: `/login admin admin123`"
        )
        await safe_edit_or_reply(query, msg, reply_markup=get_role_select_keyboard())

    elif data == "role_login_operario":
        usuarios = await api_client.get_usuarios()
        operarios = [u for u in usuarios if u["rol"] == "OPERARIO" and u["activo"]]
        if not operarios:
            await safe_edit_or_reply(query, "ℹ️ No hay operarios registrados en la base de datos.", reply_markup=get_role_select_keyboard())
            return

        msg = "👷 **SELECCIÓN DE OPERARIO**\nSeleccione su nombre con los botones para iniciar sesión:"
        await safe_edit_or_reply(query, msg, reply_markup=get_operarios_login_keyboard(operarios))

    elif data.startswith("login_op_user_"):
        username = data.replace("login_op_user_", "")
        usuarios = await api_client.get_usuarios()
        user_db = next((u for u in usuarios if u.get("username") == username and u.get("rol") == "OPERARIO"), None)
        
        if user_db:
            telegram_id = update.effective_user.id
            await api_client.vincular_telegram(telegram_id, username)
            
            context.user_data["role"] = "OPERARIO"
            context.user_data["username"] = username
            context.user_data["db_id"] = user_db["id"]
            
            msg = f"👷 **Sesión de Operario Iniciada:** Bienvenid@ **{user_db['nombre']}**."
            await safe_edit_or_reply(query, msg, reply_markup=get_operario_menu_keyboard())
        else:
            await safe_edit_or_reply(query, "❌ No se pudo iniciar sesión con ese operario.", reply_markup=get_role_select_keyboard())

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ Uso correcto: `/login <usuario> <contraseña>`", parse_mode="Markdown")
        return

    username = args[0]
    password = args[1]
    
    res = await api_client.login_admin(username, password)
    if res and res.get("status") == "ok":
        user_info = res.get("usuario", {})
        telegram_id = update.effective_user.id
        
        await api_client.vincular_telegram(telegram_id, username)
        
        context.user_data["role"] = "ADMIN"
        context.user_data["username"] = username
        context.user_data["db_id"] = user_info.get("id")
        
        msg = f"✅ **Inicio de sesión exitoso.** Bienvenid@ **{user_info.get('nombre', username)}** (Administrador)."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_admin_menu_keyboard())
    else:
        await update.message.reply_text("❌ Usuario o contraseña de Administrador incorrectos.")

async def login_operario_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("⚠️ Uso correcto: `/login_operario <nombre_usuario>`", parse_mode="Markdown")
        return

    username = args[0]
    usuarios = await api_client.get_usuarios()
    user_db = next((u for u in usuarios if u.get("username") == username and u.get("rol") == "OPERARIO"), None)
    
    if user_db:
        telegram_id = update.effective_user.id
        await api_client.vincular_telegram(telegram_id, username)
        
        context.user_data["role"] = "OPERARIO"
        context.user_data["username"] = username
        context.user_data["db_id"] = user_db["id"]
        
        msg = f"👷 **Sesión de Operario Iniciada:** Bienvenid@ **{user_db['nombre']}**."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_operario_menu_keyboard())
    else:
        await update.message.reply_text("❌ No se encontró un operario activo con ese nombre de usuario.")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = "🔒 **Sesión cerrada correctamente.** Por favor seleccione su rol para iniciar sesión:"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_role_select_keyboard())
