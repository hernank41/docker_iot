from telegram import Update
from telegram.ext import ContextTypes
from services.api_client import api_client
from keyboards.inline import (
    get_operario_menu_keyboard,
    get_maquinas_select_keyboard,
    get_herramientas_select_keyboard
)

async def safe_edit_or_reply(query, text: str, reply_markup=None, parse_mode="Markdown"):
    """Edita el mensaje si es posible. Si es una foto o falla el edit_text, borra el mensaje anterior y envía uno nuevo."""
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

async def operario_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = context.user_data.get("db_id")

    if data == "op_asignar_maquina":
        maquinas = await api_client.get_maquinas()
        await safe_edit_or_reply(
            query,
            "**SELECCIONE LA MÁQUINA A LA QUE DESEA ASIGNARSE:**",
            reply_markup=get_maquinas_select_keyboard(maquinas, "asig_maq")
        )

    elif data.startswith("asig_maq_"):
        maquina_id = int(data.split("_")[-1])
        if not user_id:
            await safe_edit_or_reply(query, "Debe estar autenticado como Operario para auto-asignarse. Ejecute `/login_operario <usuario>`")
            return

        res = await api_client.actualizar_asignacion(maquina_id=maquina_id, operario_id=user_id)
        if res and res.get("status") == "ok":
            await safe_edit_or_reply(
                query,
                f"**Asignación Exitosa:** Quedó asignado como Operario de la máquina seleccionada.",
                reply_markup=get_operario_menu_keyboard()
            )
        else:
            await safe_edit_or_reply(query, "No se pudo registrar la asignación.", reply_markup=get_operario_menu_keyboard())

    elif data == "op_seleccionar_herramienta":
        maquinas = await api_client.get_maquinas()
        await safe_edit_or_reply(
            query,
            "**SELECCIONE LA MÁQUINA PARA CAMBIAR HERRAMIENTA:**",
            reply_markup=get_maquinas_select_keyboard(maquinas, "select_herram_maq")
        )

    elif data.startswith("select_herram_maq_"):
        maquina_id = int(data.split("_")[-1])
        context.user_data["temp_maquina_id"] = maquina_id
        herramientas = await api_client.get_herramientas(maquina_id=maquina_id)
        if not herramientas:
            await safe_edit_or_reply(query, "No hay herramientas registradas para esta máquina.", reply_markup=get_operario_menu_keyboard())
            return

        await safe_edit_or_reply(
            query,
            "**SELECCIONE LA HERRAMIENTA A INSTALAR:**",
            reply_markup=get_herramientas_select_keyboard(herramientas, "instalar_h")
        )

    elif data.startswith("instalar_h_"):
        herramienta_id = int(data.split("_")[-1])
        maquina_id = context.user_data.get("temp_maquina_id", 1)

        res = await api_client.actualizar_asignacion(maquina_id=maquina_id, herramienta_id=herramienta_id)
        if res and res.get("status") == "ok":
            await safe_edit_or_reply(
                query,
                f"**Herramienta instalada exitosamente en la máquina.**",
                reply_markup=get_operario_menu_keyboard()
            )
        else:
            await safe_edit_or_reply(query, "Error al cambiar herramienta.", reply_markup=get_operario_menu_keyboard())

    elif data == "op_finalizar_actividad":
        activas = await api_client.get_actividades_activas()
        if not activas:
            await safe_edit_or_reply(query, "No hay sesiones de actividad activas para finalizar.", reply_markup=get_operario_menu_keyboard())
            return

        context.user_data["esperando_comentario_actividad_id"] = activas[0]["id"]
        await safe_edit_or_reply(
            query,
            f"**Finalización de Actividad (ID #{activas[0]['id']})**\n\n"
            f"Por favor, envíe un **mensaje de texto** con su comentario u observación sobre la tarea realizada (ej: *'Mecanizado finalizado sin novedad'*):"
        )

async def recibir_comentario_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    actividad_id = context.user_data.get("esperando_comentario_actividad_id")
    if not actividad_id:
        return

    comentario = update.message.text
    res = await api_client.finalizar_actividad(actividad_id, comentario)
    context.user_data.pop("esperando_comentario_actividad_id", None)

    if res and res.get("status") == "ok":
        await update.message.reply_text(
            f"**Actividad #{actividad_id} Finalizada Exitosamente.**\nComentario guardado: _{comentario}_",
            parse_mode="Markdown",
            reply_markup=get_operario_menu_keyboard()
        )
    else:
        await update.message.reply_text("No se pudo finalizar la actividad.", reply_markup=get_operario_menu_keyboard())
