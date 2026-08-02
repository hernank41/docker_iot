from telegram import Update
from telegram.ext import ContextTypes
from services.api_client import api_client
from keyboards.inline import (
    get_admin_menu_keyboard,
    get_operario_menu_keyboard,
    get_role_select_keyboard,
    get_operarios_login_keyboard,
    get_cancel_keyboard
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
    
    if context.user_data.get("role"):
        rol = context.user_data["role"]
        username = context.user_data.get("username", "")
        if rol == "ADMIN":
            msg = f"¡Hola **{username}**! Conectado como **Administrador**.\nUtilice el menú inferior para gestionar el sistema."
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_admin_menu_keyboard())
            return
        else:
            op_id = context.user_data.get("db_id")
            asig_info = await api_client.get_asignacion_operario(op_id) if op_id else None
            asig = asig_info.get("asignacion") if asig_info else None
            act = asig_info.get("actividad_activa") if asig_info else None

            maq_str = asig.get("maquina_nombre", "Sin Asignar") if asig else "Sin Asignar"
            herram_str = asig.get("herramienta_nombre", "Sin Asignar") if asig and asig.get("herramienta_nombre") else "Sin Asignar"
            comentario_str = f"\"{act['comentario']}\"" if act and act.get("comentario") else "Sin Comentario"

            msg = (
                f"¡Bienvenido **{username}**! Conectado como **Operario**.\n\n"
                f"• **Máquina Asignada:** `{maq_str}`\n"
                f"• **Herramienta Montada:** `{herram_str}`\n"
                f"• **Comentario Activo:** {comentario_str}\n\n"
                f"Seleccione una opción:"
            )
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_operario_menu_keyboard())
            return

    msg = (
        f"¡Hola {user.first_name}!\n\n"
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
        msg = "Bienvenido al sistema **Industrial IoT Stack**. Seleccione su rol:"
        await safe_edit_or_reply(query, msg, reply_markup=get_role_select_keyboard())

    elif data == "role_login_admin":
        context.user_data["esperando_login"] = "admin_username"
        msg = (
            "**AUTENTICACIÓN DE ADMINISTRADOR (Paso 1 de 2)**\n\n"
            "Por favor, envíe en un **mensaje de texto** su **Nombre de Usuario** de Administrador (ejemplo: `admin`):"
        )
        await safe_edit_or_reply(query, msg, reply_markup=get_cancel_keyboard("show_role_select"))

    elif data == "role_login_operario":
        usuarios = await api_client.get_usuarios()
        operarios = [u for u in usuarios if u["rol"] == "OPERARIO" and u["activo"]]
        if not operarios:
            await safe_edit_or_reply(query, "No hay operarios registrados en la base de datos.", reply_markup=get_role_select_keyboard())
            return

        msg = "**SELECCIÓN DE OPERARIO**\nSeleccione su nombre con los botones para iniciar sesión:"
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
            
            asig_info = await api_client.get_asignacion_operario(user_db["id"])
            asig = asig_info.get("asignacion") if asig_info else None
            act = asig_info.get("actividad_activa") if asig_info else None

            maq_str = asig.get("maquina_nombre", "Sin Asignar") if asig else "Sin Asignar"
            herram_str = asig.get("herramienta_nombre", "Sin Asignar") if asig and asig.get("herramienta_nombre") else "Sin Asignar"
            comentario_str = f"\"{act['comentario']}\"" if act and act.get("comentario") else "Sin Comentario"

            msg = (
                f"**Sesión de Operario Iniciada:** Bienvenid@ **{user_db['nombre']}**.\n\n"
                f"• **Máquina Asignada:** `{maq_str}`\n"
                f"• **Herramienta Montada:** `{herram_str}`\n"
                f"• **Comentario Activo:** {comentario_str}"
            )
            await safe_edit_or_reply(query, msg, reply_markup=get_operario_menu_keyboard())
        else:
            await safe_edit_or_reply(query, "No se pudo iniciar sesión con ese operario.", reply_markup=get_role_select_keyboard())

async def login_step_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el inicio de sesión interactivo paso a paso para el Administrador."""
    estado_login = context.user_data.get("esperando_login")
    if not estado_login:
        return

    text = update.message.text.strip()

    if estado_login == "admin_username":
        context.user_data["temp_admin_user"] = text
        context.user_data["esperando_login"] = "admin_password"
        await update.message.reply_text(
            f"**AUTENTICACIÓN DE ADMINISTRADOR (Paso 2 de 2)**\n\n"
            f"Usuario: `{text}`\n"
            f"Por favor, ingrese su **Contraseña**:",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard("show_role_select")
        )
    elif estado_login == "admin_password":
        username = context.user_data.get("temp_admin_user", "admin")
        password = text
        context.user_data.pop("esperando_login", None)
        context.user_data.pop("temp_admin_user", None)

        res = await api_client.login_admin(username, password)
        if res and res.get("status") == "ok":
            user_info = res.get("usuario", {})
            telegram_id = update.effective_user.id
            await api_client.vincular_telegram(telegram_id, username)
            
            context.user_data["role"] = "ADMIN"
            context.user_data["username"] = username
            context.user_data["db_id"] = user_info.get("id")
            
            msg = f"**Inicio de sesión exitoso.** Bienvenid@ **{user_info.get('nombre', username)}** (Administrador)."
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_admin_menu_keyboard())
        else:
            await update.message.reply_text(
                "**Error de Autenticación:** Usuario o contraseña de Administrador incorrectos.\n\n"
                "Seleccione su rol para reintentar:",
                parse_mode="Markdown",
                reply_markup=get_role_select_keyboard()
            )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        context.user_data["esperando_login"] = "admin_username"
        await update.message.reply_text(
            "**AUTENTICACIÓN DE ADMINISTRADOR (Paso 1 de 2)**\n\n"
            "Por favor, ingrese su **Nombre de Usuario** de Administrador:",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard("show_role_select")
        )
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
        
        msg = f"**Inicio de sesión exitoso.** Bienvenid@ **{user_info.get('nombre', username)}** (Administrador)."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_admin_menu_keyboard())
    else:
        await update.message.reply_text("Usuario o contraseña de Administrador incorrectos.")

async def login_operario_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Uso correcto: `/login_operario <nombre_usuario>`", parse_mode="Markdown")
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
        
        msg = f"**Sesión de Operario Iniciada:** Bienvenid@ **{user_db['nombre']}**."
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_operario_menu_keyboard())
    else:
        await update.message.reply_text("No se encontró un operario activo con ese nombre de usuario.")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = "**Sesión cerrada correctamente.** Por favor seleccione su rol para iniciar sesión:"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_role_select_keyboard())
