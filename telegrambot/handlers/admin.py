from telegram import Update, InputFile
from telegram.ext import ContextTypes
from services.api_client import api_client
from services.chart_generator import (
    generar_grafico_turno,
    generar_grafico_semana,
    generar_grafico_operario
)
from keyboards.inline import (
    get_admin_menu_keyboard,
    get_operarios_menu_keyboard,
    get_operarios_list_keyboard,
    get_config_menu_keyboard,
    get_informes_keyboard,
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

def generar_barra_progreso(porcentaje: float) -> str:
    bloques = int(round(porcentaje / 10))
    bloques = min(max(bloques, 0), 10)
    barra = "█" * bloques + "░" * (10 - bloques)
    return f"[{barra}] {porcentaje:.1f}%"

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "logout_session":
        context.user_data.clear()
        await safe_edit_or_reply(
            query,
            "**Sesión cerrada correctamente.**\n\nPara volver a iniciar sesión ejecute `/start`, `/login` o `/login_operario`."
        )
        return

    if data in ["menu_admin", "menu_principal"]:
        context.user_data.pop("esperando_accion", None)
        await safe_edit_or_reply(
            query,
            "**Menú de Administración Principal:**",
            reply_markup=get_admin_menu_keyboard()
        )

    # 1. Estado de Máquinas
    elif data == "admin_maquinas":
        estados = await api_client.get_estado_actual()
        if not estados:
            await safe_edit_or_reply(query, "No hay información de máquinas registrada.", reply_markup=get_admin_menu_keyboard())
            return

        text = "**ESTADO EN TIEMPO REAL DE MÁQUINAS**\n\n"
        for m in estados:
            estado_str = m.get("estado", "PARADA")
            operario = m.get("operario_nombre") or "Sin Asignar"
            herramienta = m.get("herramienta_nombre") or "Sin Asignar"
            causa = m.get("causa") or "OPERACION_NORMAL"
            
            text += f"• **{m['maquina']}** ({m['tipo']})\n"
            text += f"   • **Estado:** `{estado_str}` [{causa}]\n"
            text += f"   • **Operario:** {operario}\n"
            text += f"   • **Herramienta:** {herramienta}\n\n"

        await safe_edit_or_reply(query, text, reply_markup=get_admin_menu_keyboard())

    # 2. Herramientas y Desgaste
    elif data == "admin_herramientas":
        herramientas = await api_client.get_herramientas()
        if not herramientas:
            await safe_edit_or_reply(query, "No hay herramientas registradas.", reply_markup=get_admin_menu_keyboard())
            return

        text = "**ESTADO DE HERRAMIENTAS Y VIDA ÚTIL**\n\n"
        for h in herramientas:
            porcentaje = float(h.get("porcentaje_desgaste") or 0.0)
            barra = generar_barra_progreso(porcentaje)
            alerta = " [DESGASTE ALTO]" if porcentaje >= 90 else ""
            
            text += f"• **{h['nombre']}** ({h['maquina_nombre']})\n"
            text += f"  Desgaste: `{barra}`{alerta}\n"
            text += f"  Uso: `{h['horas_uso']} hs` / Expectativa: `{h['horas_expectativa']} hs`\n\n"

        await safe_edit_or_reply(query, text, reply_markup=get_admin_menu_keyboard())

    # 3. Menú Gestión Operarios
    elif data == "admin_operarios_menu":
        usuarios = await api_client.get_usuarios()
        operarios = [u for u in usuarios if u["rol"] == "OPERARIO" and u["activo"]]
        
        text = "**GESTIÓN DE OPERARIOS REGISTRADOS**\n\n"
        if operarios:
            for op in operarios:
                vinc = "Vinculado" if op.get("telegram_id") else "Pendiente"
                text += f"• **{op['nombre']}** (`@{op['username']}`) - ID: `{op['id']}` [{vinc}]\n"
        else:
            text += "No hay operarios registrados actualmente.\n"

        text += "\n*Seleccione una acción con los botones inferiores:*"
        await safe_edit_or_reply(query, text, reply_markup=get_operarios_menu_keyboard())

    # 3.1 Submenú Eliminar Operario
    elif data == "admin_op_eliminar_menu":
        usuarios = await api_client.get_usuarios()
        operarios = [u for u in usuarios if u["rol"] == "OPERARIO" and u["activo"]]
        if not operarios:
            await safe_edit_or_reply(query, "No hay operarios para eliminar.", reply_markup=get_operarios_menu_keyboard())
            return

        await safe_edit_or_reply(
            query,
            "**SELECCIONE EL OPERARIO A ELIMINAR/DESACTIVAR:**",
            reply_markup=get_operarios_list_keyboard(operarios, "admin_op_del")
        )

    # 3.2 Acción 1-Click Eliminar Operario
    elif data.startswith("admin_op_del_"):
        op_id = int(data.split("_")[-1])
        res = await api_client.eliminar_usuario(op_id)
        if res and res.get("status") == "ok":
            await safe_edit_or_reply(query, f"Operario ID `{op_id}` eliminado/desactivado exitosamente.", reply_markup=get_operarios_menu_keyboard())
        else:
            await safe_edit_or_reply(query, "No se pudo eliminar el operario.", reply_markup=get_operarios_menu_keyboard())

    # 3.3 Submenú Stats Operario
    elif data == "admin_op_stats_menu":
        usuarios = await api_client.get_usuarios()
        operarios = [u for u in usuarios if u["rol"] == "OPERARIO" and u["activo"]]
        if not operarios:
            await safe_edit_or_reply(query, "No hay operarios registrados.", reply_markup=get_operarios_menu_keyboard())
            return

        await safe_edit_or_reply(
            query,
            "**SELECCIONE UN OPERARIO PARA VER SUS ESTADÍSTICAS:**",
            reply_markup=get_operarios_list_keyboard(operarios, "admin_opstats")
        )

    # 3.4 Acción Ver Stats Operario con Matplotlib Chart
    elif data.startswith("admin_opstats_"):
        op_id = int(data.split("_")[-1])
        stats = await api_client.get_usuario_stats(op_id)
        if not stats:
            await safe_edit_or_reply(query, "No se pudieron cargar las estadísticas del operario.", reply_markup=get_operarios_menu_keyboard())
            return

        user_info = stats.get("usuario", {})
        resumen = stats.get("resumen", {})
        maquinas_stats = stats.get("maquinas", [])

        text = f"**ESTADÍSTICAS DE RENDIMIENTO: {user_info.get('nombre')}**\n"
        text += f"• **Usuario:** `@{user_info.get('username')}`\n"
        text += f"• **Total Actividades Completadas:** `{resumen.get('total_actividades', 0)}`\n"
        text += f"• **Horas Operativas Totales:** `{resumen.get('total_horas', 0.0)} hs`\n\n"

        text += "**Desglose por Máquina:**\n"
        for m in maquinas_stats:
            text += f"   • `{m['maquina']}`: {m['horas_activas']} hs ({m['actividades_count']} sesiones)\n"

        chart_buf = generar_grafico_operario(user_info.get('nombre', 'Operario'), maquinas_stats)
        if chart_buf:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_photo(
                photo=InputFile(chart_buf, filename="operario_stats.png"),
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_operarios_menu_keyboard()
            )
        else:
            await safe_edit_or_reply(query, text, reply_markup=get_operarios_menu_keyboard())

    # 3.5 Creación Interactiva de Operario
    elif data == "op_crear_inicio":
        context.user_data["esperando_accion"] = "crear_op_nombre"
        await safe_edit_or_reply(
            query,
            "**NUEVO OPERARIO (Paso 1 de 2)**\n\n"
            "Por favor, envíe en un **mensaje de texto** el **Nombre Completo** del operario (ejemplo: *María López*):",
            reply_markup=get_cancel_keyboard("admin_operarios_menu")
        )

    # 4. Informes & KPIs con Gráficos Matplotlib
    elif data == "admin_informes":
        await safe_edit_or_reply(
            query,
            "**INFORMES Y ANALÍTICA DE PRODUCCIÓN**\nSeleccione el informe que desea consultar:",
            reply_markup=get_informes_keyboard()
        )

    elif data == "reporte_turno":
        rep = await api_client.get_reporte_turno()
        if not rep:
            await safe_edit_or_reply(query, "No hay registros de actividades en los últimos 7 días.", reply_markup=get_informes_keyboard())
            return

        text = "**INFORME DE ACTIVIDADES POR DÍA Y TURNO (Últimos 7 Días)**\n\n"
        for r in rep:
            text += f"**Fecha:** `{r['fecha']}` | **Máquina:** `{r['maquina']}`\n"
            text += f"   • **Horas Activas:** `{r['horas_activas']} hs`\n"
            text += f"   • **Sesiones:** `{r['total_actividades']}` | **Operario:** {r['operarios'] or 'N/A'}\n\n"

        chart_buf = generar_grafico_turno(rep)
        if chart_buf:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_photo(
                photo=InputFile(chart_buf, filename="reporte_turno.png"),
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_informes_keyboard()
            )
        else:
            await safe_edit_or_reply(query, text, reply_markup=get_informes_keyboard())

    elif data == "reporte_semana":
        rep = await api_client.get_reporte_semana()
        if not rep:
            await safe_edit_or_reply(query, "No hay registros de producción en la semana.", reply_markup=get_informes_keyboard())
            return

        text = "**INFORME CONSOLIDADO SEMANAL**\n\n"
        for r in rep:
            text += f"**Máquina:** `{r['maquina']}`\n"
            text += f"   • **Total Horas Operativas:** `{r['total_horas_activas']} hs`\n"
            text += f"   • **Sesiones de Actividad:** `{r['total_actividades']}`\n"
            text += f"   • **Operarios Involucrados:** `{r['total_operarios_participantes']}`\n\n"

        chart_buf = generar_grafico_semana(rep)
        if chart_buf:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_photo(
                photo=InputFile(chart_buf, filename="reporte_semana.png"),
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_informes_keyboard()
            )
        else:
            await safe_edit_or_reply(query, text, reply_markup=get_informes_keyboard())

    # 5. Menú Configuración Global
    elif data == "admin_config_menu":
        configs = await api_client.get_configuracion()
        await safe_edit_or_reply(
            query,
            "**CONFIGURACIÓN GLOBAL DEL SISTEMA**\n\n"
            "Seleccione con los botones el parámetro que desea modificar:",
            reply_markup=get_config_menu_keyboard(configs)
        )

    elif data.startswith("edit_cfg_"):
        clave = data.replace("edit_cfg_", "")
        context.user_data["esperando_accion"] = "editar_cfg_valor"
        context.user_data["cfg_clave_temp"] = clave

        await safe_edit_or_reply(
            query,
            f"**MODIFICAR CONFIGURACIÓN: `{clave}`**\n\n"
            f"Por favor, envíe un **mensaje de texto** con el nuevo valor para esta variable:",
            reply_markup=get_cancel_keyboard("admin_config_menu")
        )

async def admin_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accion = context.user_data.get("esperando_accion")
    if not accion:
        return

    text = update.message.text.strip()

    if accion == "crear_op_nombre":
        context.user_data["op_nombre_temp"] = text
        context.user_data["esperando_accion"] = "crear_op_username"
        await update.message.reply_text(
            f"**NUEVO OPERARIO (Paso 2 de 2)**\n\n"
            f"Nombre ingresado: **{text}**\n\n"
            f"Ahora envíe el **nombre de usuario** para el inicio de sesión del operario (ejemplo: `mlopez`):",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard("admin_operarios_menu")
        )

    elif accion == "crear_op_username":
        nombre = context.user_data.get("op_nombre_temp", "Operario")
        username = text.lower().replace("@", "")
        context.user_data.pop("esperando_accion", None)

        res = await api_client.crear_usuario(nombre, username, rol="OPERARIO")
        if res and res.get("status") == "ok":
            await update.message.reply_text(
                f"**Operario Creado Exitosamente.**\n\n"
                f"• **Nombre:** {nombre}\n"
                f"• **Usuario:** `@{username}`\n\n"
                f"El operario ya puede iniciar sesión enviando:\n`/login_operario {username}`",
                parse_mode="Markdown",
                reply_markup=get_operarios_menu_keyboard()
            )
        else:
            await update.message.reply_text("No se pudo crear el operario. Verifique que el usuario no exista.", reply_markup=get_operarios_menu_keyboard())

    elif accion == "editar_cfg_valor":
        clave = context.user_data.get("cfg_clave_temp")
        valor = text
        context.user_data.pop("esperando_accion", None)

        res = await api_client.actualizar_configuracion(clave, valor)
        if res and res.get("status") == "ok":
            await update.message.reply_text(
                f"**Configuración Actualizada Exitosamente.**\n\n"
                f"• **Clave:** `{clave}`\n"
                f"• **Nuevo Valor:** `{valor}`",
                parse_mode="Markdown",
                reply_markup=get_admin_menu_keyboard()
            )
        else:
            await update.message.reply_text("Error al actualizar configuración.", reply_markup=get_admin_menu_keyboard())
