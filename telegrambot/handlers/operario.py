from telegram import Update
from telegram.ext import ContextTypes
from services.api_client import api_client
from keyboards.inline import (
    get_operario_menu_keyboard,
    get_maquinas_select_keyboard,
    get_herramientas_select_keyboard,
    get_cancel_keyboard
)

async def safe_edit_or_reply(query, text: str, reply_markup=None, parse_mode=None):
    """Edita el mensaje si es posible. Realiza un fallback a texto plano limpio."""
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

    if data in ["menu_operario", "show_menu_operario"]:
        context.user_data.pop("esperando_comentario", None)
        context.user_data.pop("esperando_comentario_actividad_id", None)
        context.user_data.pop("esperando_comentario_maquina_id", None)
        context.user_data.pop("esperando_comentario_user_id", None)
        context.user_data.pop("esperando_finalizar_actividad_id", None)
        
        user_name = context.user_data.get("username", "Operario")
        asig_info = await api_client.get_asignacion_operario(user_id) if user_id else None
        asig = asig_info.get("asignacion") if asig_info else None
        act = asig_info.get("actividad_activa") if asig_info else None

        maq_str = asig.get("maquina_nombre", "Sin asignar") if (asig and asig.get("maquina_nombre")) else "Sin asignar"
        herram_str = asig.get("herramienta_nombre", "Sin asignar") if (asig and asig.get("herramienta_nombre")) else "Sin asignar"

        comentario_val = None
        if act and act.get("comentario"):
            comentario_val = act["comentario"]
        elif asig and asig.get("comentario_pre"):
            comentario_val = asig["comentario_pre"]

        comentario_str = f"\"{comentario_val}\"" if comentario_val else "Sin Comentario"

        msg = (
            f"Sesión de Operario Iniciada: Bienvenid@ {user_name}.\n\n"
            f"• Máquina Asignada: {maq_str}\n"
            f"• Herramienta Montada: {herram_str}\n"
            f"• Comentario Activo: {comentario_str}"
        )
        await safe_edit_or_reply(query, msg, reply_markup=get_operario_menu_keyboard())
        return

    if data == "op_asignar_maquina":
        maquinas = await api_client.get_maquinas()
        await safe_edit_or_reply(
            query,
            "SELECCIONE LA MÁQUINA A LA QUE DESEA ASIGNARSE:\n\nNota: Al asignarse a una nueva máquina, se desvinculará automáticamente de la máquina anterior.",
            reply_markup=get_maquinas_select_keyboard(maquinas, "asig_maq")
        )

    elif data.startswith("asig_maq_"):
        maquina_id = int(data.split("_")[-1])
        if not user_id:
            await safe_edit_or_reply(query, "Debe estar autenticado como Operario para auto-asignarse. Ejecute /start para iniciar sesión.")
            return

        temp_comment = context.user_data.pop("temp_pre_comentario", None)
        res = await api_client.actualizar_asignacion(maquina_id=maquina_id, operario_id=user_id, comentario=temp_comment)
        if res and res.get("status") == "ok":
            user_name = context.user_data.get("username", "Operario")
            asig_info = await api_client.get_asignacion_operario(user_id)
            asig = asig_info.get("asignacion") if asig_info else None
            act = asig_info.get("actividad_activa") if asig_info else None

            maq_str = asig.get("maquina_nombre", "Sin asignar") if (asig and asig.get("maquina_nombre")) else "Sin asignar"
            herram_str = asig.get("herramienta_nombre", "Sin asignar") if (asig and asig.get("herramienta_nombre")) else "Sin asignar"

            comentario_val = None
            if act and act.get("comentario"):
                comentario_val = act["comentario"]
            elif asig and asig.get("comentario_pre"):
                comentario_val = asig["comentario_pre"]

            comentario_str = f"\"{comentario_val}\"" if comentario_val else "Sin Comentario"

            text = (
                f"Asignación Exitosa: Quedó asignado como Operario de la máquina seleccionada.\n\n"
                f"• Máquina Asignada: {maq_str}\n"
                f"• Herramienta Montada: {herram_str}\n"
                f"• Comentario Activo: {comentario_str}"
            )
            await safe_edit_or_reply(query, text, reply_markup=get_operario_menu_keyboard())
        else:
            await safe_edit_or_reply(query, "No se pudo registrar la asignación.", reply_markup=get_operario_menu_keyboard())

    elif data == "op_seleccionar_herramienta":
        if not user_id:
            await safe_edit_or_reply(query, "Debe estar autenticado como Operario para seleccionar herramientas.")
            return

        asig_info = await api_client.get_asignacion_operario(user_id)
        asig = asig_info.get("asignacion") if asig_info else None

        if not asig or not asig.get("maquina_id"):
            await safe_edit_or_reply(
                query,
                "Primero debe fichar / asignarse a una máquina antes de poder seleccionar una herramienta de corte.",
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
            f"SELECCIONE LA HERRAMIENTA A INSTALAR EN {maquina_nombre}:",
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

            maq_str = asig_up.get("maquina_nombre", "Sin asignar") if (asig_up and asig_up.get("maquina_nombre")) else "Sin asignar"
            herram_str = asig_up.get("herramienta_nombre", "Sin asignar") if (asig_up and asig_up.get("herramienta_nombre")) else "Sin asignar"

            comentario_val = None
            if act_up and act_up.get("comentario"):
                comentario_val = act_up["comentario"]
            elif asig_up and asig_up.get("comentario_pre"):
                comentario_val = asig_up["comentario_pre"]

            comentario_str = f"\"{comentario_val}\"" if comentario_val else "Sin Comentario"

            text = (
                f"Herramienta instalada exitosamente en la máquina.\n\n"
                f"• Máquina Asignada: {maq_str}\n"
                f"• Herramienta Montada: {herram_str}\n"
                f"• Comentario Activo: {comentario_str}"
            )
            await safe_edit_or_reply(query, text, reply_markup=get_operario_menu_keyboard())
        else:
            await safe_edit_or_reply(query, "Error al cambiar herramienta.", reply_markup=get_operario_menu_keyboard())

    elif data == "op_agregar_comentario":
        asig_info = await api_client.get_asignacion_operario(user_id)
        asig = asig_info.get("asignacion") if asig_info else None
        act = asig_info.get("actividad_activa") if asig_info else None

        comentario_actual = (act.get("comentario") if act else None) or (asig.get("comentario_pre") if asig else None) or "Ninguno"

        context.user_data["esperando_comentario"] = True
        context.user_data["esperando_comentario_user_id"] = user_id
        if act:
            context.user_data["esperando_comentario_actividad_id"] = act["id"]
        if asig:
            context.user_data["esperando_comentario_maquina_id"] = asig.get("maquina_id")

        await safe_edit_or_reply(
            query,
            f"AGREGAR / MODIFICAR COMENTARIO\n\n"
            f"Comentario actual: {comentario_actual}\n\n"
            f"Por favor, envíe en un mensaje de texto su comentario u observación para la sesión (ejemplo: Lote bujes 50mm terminado sin novedad):",
            reply_markup=get_cancel_keyboard("menu_operario")
        )

    elif data == "op_finalizar_actividad":
        if not user_id:
            await safe_edit_or_reply(query, "Debe estar autenticado como Operario para finalizar actividades.")
            return

        asig_info = await api_client.get_asignacion_operario(user_id)
        asig = asig_info.get("asignacion") if asig_info else None
        act = asig_info.get("actividad_activa") if asig_info else None

        target_act_id = act["id"] if act else (asig.get("maquina_id") if asig else None)

        if not target_act_id:
            await safe_edit_or_reply(
                query,
                "No tiene ninguna máquina asignada ni actividad en curso para finalizar.",
                reply_markup=get_operario_menu_keyboard()
            )
            return

        context.user_data["esperando_finalizar_actividad_id"] = target_act_id
        await safe_edit_or_reply(
            query,
            f"Finalización de Actividad y Desvinculación\n\n"
            f"Por favor, envíe un mensaje de texto con su comentario u observación final sobre la tarea realizada:",
            reply_markup=get_cancel_keyboard("menu_operario")
        )

async def recibir_comentario_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = context.user_data.get("db_id")
    comentario = update.message.text.strip()

    context.user_data.pop("esperando_comentario", None)
    finalizar_act_id = context.user_data.pop("esperando_finalizar_actividad_id", None)
    actividad_id = context.user_data.pop("esperando_comentario_actividad_id", None)
    maquina_id = context.user_data.pop("esperando_comentario_maquina_id", None)
    context.user_data.pop("esperando_comentario_user_id", None)

    if finalizar_act_id:
        # Finalizar la actividad del operario específico y desvincular asignaciones
        await api_client.finalizar_actividad(finalizar_act_id, comentario)
        prefix_msg = "Actividad Finalizada Exitosamente."
    elif maquina_id:
        await api_client.actualizar_asignacion(maquina_id=maquina_id, operario_id=user_id, comentario=comentario)
        prefix_msg = "Comentario Registrado Exitosamente."
    elif actividad_id:
        await api_client.actualizar_comentario_actividad(actividad_id, comentario)
        prefix_msg = "Comentario Registrado Exitosamente."
    else:
        context.user_data["temp_pre_comentario"] = comentario
        prefix_msg = "Comentario Registrado Exitosamente."

    user_name = context.user_data.get("username", "Operario")
    asig_info = await api_client.get_asignacion_operario(user_id) if user_id else None
    asig = asig_info.get("asignacion") if asig_info else None
    act = asig_info.get("actividad_activa") if asig_info else None

    maq_str = asig.get("maquina_nombre", "Sin asignar") if (asig and asig.get("maquina_nombre")) else "Sin asignar"
    herram_str = asig.get("herramienta_nombre", "Sin asignar") if (asig and asig.get("herramienta_nombre")) else "Sin asignar"

    comentario_val = None
    if act and act.get("comentario"):
        comentario_val = act["comentario"]
    elif asig and asig.get("comentario_pre"):
        comentario_val = asig["comentario_pre"]

    comentario_str = f"\"{comentario_val}\"" if comentario_val else "Sin Comentario"

    msg = (
        f"{prefix_msg}\n"
        f"Comentario: \"{comentario}\"\n\n"
        f"Sesión de Operario Iniciada: Bienvenid@ {user_name}.\n\n"
        f"• Máquina Asignada: {maq_str}\n"
        f"• Herramienta Montada: {herram_str}\n"
        f"• Comentario Activo: {comentario_str}"
    )
    await update.message.reply_text(
        msg,
        reply_markup=get_operario_menu_keyboard()
    )
