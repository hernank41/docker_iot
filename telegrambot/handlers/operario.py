from telegram import Update
from telegram.ext import ContextTypes
from services.api_client import api_client
from keyboards.inline import (
    get_operario_menu_keyboard,
    get_maquinas_select_keyboard,
    get_herramientas_select_keyboard,
    get_cancel_keyboard
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
            "**SELECCIONE LA MÁQUINA A LA QUE DESEA ASIGNARSE:**\n\n*Nota: Al asignarse a una nueva máquina, se desvinculará automáticamente de la máquina anterior.*",
            reply_markup=get_maquinas_select_keyboard(maquinas, "asig_maq")
        )

    elif data.startswith("asig_maq_"):
        maquina_id = int(data.split("_")[-1])
        if not user_id:
            await safe_edit_or_reply(query, "Debe estar autenticado como Operario para auto-asignarse. Ejecute `/start` para iniciar sesión.")
            return

        res = await api_client.actualizar_asignacion(maquina_id=maquina_id, operario_id=user_id)
        if res and res.get("status") == "ok":
            asig_info = await api_client.get_asignacion_operario(user_id)
            asig = asig_info.get("asignacion") if asig_info else None
            act = asig_info.get("actividad_activa") if asig_info else None

            maq_str = asig.get("maquina_nombre", "Sin Asignar") if asig else "Sin Asignar"
            herram_str = asig.get("herramienta_nombre", "Sin Asignar") if asig and asig.get("herramienta_nombre") else "Sin Asignar"
            comentario_str = f"\"{act['comentario']}\"" if act and act.get("comentario") else "Sin Comentario"

            text = (
                f"**Asignación Exitosa:** Quedó asignado como Operario de la máquina seleccionada.\n\n"
                f"• **Máquina Asignada:** `{maq_str}`\n"
                f"• **Herramienta Montada:** `{herram_str}`\n"
                f"• **Comentario Activo:** {comentario_str}"
            )
            await safe_edit_or_reply(query, text, reply_markup=get_operario_menu_keyboard())
        else:
            await safe_edit_or_reply(query, "No se pudo registrar la asignación.", reply_markup=get_operario_menu_keyboard())

    elif data == "op_seleccionar_herramienta":
        if not user_id:
            await safe_edit_or_reply(query, "Debe estar autenticado como Operario para seleccionar herramientas.")
            return

        # Consultar la máquina a la que está asignado el operario actualmente
        asig_info = await api_client.get_asignacion_operario(user_id)
        asig = asig_info.get("asignacion") if asig_info else None

        if not asig or not asig.get("maquina_id"):
            await safe_edit_or_reply(
                query,
                "**Primero debe fichar / asignarse a una máquina** antes de poder seleccionar una herramienta de corte.",
                reply_markup=get_operario_menu_keyboard()
            )
            return

        maquina_id = asig["maquina_id"]
        maquina_nombre = asig.get("maquina_nombre", "Máquina")
        context.user_data["temp_maquina_id"] = maquina_id

        herramientas = await api_client.get_herramientas(maquina_id=maquina_id)
        if not herramientas:
            await safe_edit_or_reply(query, f"No hay herramientas registradas para la máquina {maquina_nombre}.", reply_markup=get_operario_menu_keyboard())
            return

        await safe_edit_or_reply(
            query,
            f"**SELECCIONE LA HERRAMIENTA A INSTALAR EN {maquina_nombre}:**",
            reply_markup=get_herramientas_select_keyboard(herramientas, "instalar_h")
        )

    elif data.startswith("instalar_h_"):
        herramienta_id = int(data.split("_")[-1])
        
        asig_info = await api_client.get_asignacion_operario(user_id)
        asig = asig_info.get("asignacion") if asig_info else None
        maquina_id = asig["maquina_id"] if asig else context.user_data.get("temp_maquina_id", 1)

        res = await api_client.actualizar_asignacion(maquina_id=maquina_id, herramienta_id=herramienta_id, operario_id=user_id)
        if res and res.get("status") == "ok":
            asig_info_updated = await api_client.get_asignacion_operario(user_id)
            asig_up = asig_info_updated.get("asignacion") if asig_info_updated else None
            act_up = asig_info_updated.get("actividad_activa") if asig_info_updated else None

            maq_str = asig_up.get("maquina_nombre", "Sin Asignar") if asig_up else "Sin Asignar"
            herram_str = asig_up.get("herramienta_nombre", "Sin Asignar") if asig_up and asig_up.get("herramienta_nombre") else "Sin Asignar"
            comentario_str = f"\"{act_up['comentario']}\"" if act_up and act_up.get("comentario") else "Sin Comentario"

            text = (
                f"**Herramienta instalada exitosamente en la máquina.**\n\n"
                f"• **Máquina Asignada:** `{maq_str}`\n"
                f"• **Herramienta Montada:** `{herram_str}`\n"
                f"• **Comentario Activo:** {comentario_str}"
            )
            await safe_edit_or_reply(query, text, reply_markup=get_operario_menu_keyboard())
        else:
            await safe_edit_or_reply(query, "Error al cambiar herramienta.", reply_markup=get_operario_menu_keyboard())

    elif data == "op_agregar_comentario":
        asig_info = await api_client.get_asignacion_operario(user_id)
        act = asig_info.get("actividad_activa") if asig_info else None

        if not act:
            await safe_edit_or_reply(
                query,
                "No hay una actividad activa en curso para agregar un comentario. Inicie la máquina para comenzar una sesión.",
                reply_markup=get_operario_menu_keyboard()
            )
            return

        context.user_data["esperando_comentario_actividad_id"] = act["id"]
        comentario_actual = act.get("comentario") or "Ninguno"

        await safe_edit_or_reply(
            query,
            f"**AGREGAR / MODIFICAR COMENTARIO A LA ACTIVIDAD EN CURSO (ID #{act['id']})**\n\n"
            f"Comentario actual: _{comentario_actual}_\n\n"
            f"Por favor, envíe en un **mensaje de texto** su comentario u observación (ejemplo: *'Lote bujes 50mm terminado sin novedad'*):",
            reply_markup=get_cancel_keyboard("menu_principal")
        )

    elif data == "op_finalizar_actividad":
        activas = await api_client.get_actividades_activas()
        
        # Filtrar por operario si es posible
        op_activas = [a for a in activas if a.get("operario_id") == user_id] if user_id else activas
        target_act = op_activas[0] if op_activas else (activas[0] if activas else None)

        if not target_act:
            await safe_edit_or_reply(query, "No hay sesiones de actividad activas para finalizar.", reply_markup=get_operario_menu_keyboard())
            return

        context.user_data["esperando_comentario_actividad_id"] = target_act["id"]
        await safe_edit_or_reply(
            query,
            f"**Finalización de Actividad (ID #{target_act['id']})**\n\n"
            f"Por favor, envíe un **mensaje de texto** con su comentario u observación final sobre la tarea realizada:",
            reply_markup=get_cancel_keyboard("menu_principal")
        )

async def recibir_comentario_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    actividad_id = context.user_data.get("esperando_comentario_actividad_id")
    if not actividad_id:
        return

    comentario = update.message.text.strip()
    user_id = context.user_data.get("db_id")

    # Intentar actualizar comentario vía API
    res = await api_client.actualizar_comentario_actividad(actividad_id, comentario)
    context.user_data.pop("esperando_comentario_actividad_id", None)

    asig_info = await api_client.get_asignacion_operario(user_id) if user_id else None
    asig = asig_info.get("asignacion") if asig_info else None
    maq_str = asig.get("maquina_nombre", "Máquina") if asig else "Máquina"
    herram_str = asig.get("herramienta_nombre", "Sin Asignar") if asig and asig.get("herramienta_nombre") else "Sin Asignar"

    msg = (
        f"**Comentario Guardado Exitosamente para Actividad #{actividad_id}:**\n"
        f"_{comentario}_\n\n"
        f"• **Máquina Asignada:** `{maq_str}`\n"
        f"• **Herramienta Montada:** `{herram_str}`\n"
        f"• **Comentario Activo:** \"{comentario}\""
    )
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=get_operario_menu_keyboard()
    )
