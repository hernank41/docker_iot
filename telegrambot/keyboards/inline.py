from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_role_select_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("[Iniciar Sesión como Administrador]", callback_data="role_login_admin")
        ],
        [
            InlineKeyboardButton("[Iniciar Sesión como Operario]", callback_data="role_login_operario")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_operarios_login_keyboard(operarios):
    keyboard = []
    for op in operarios:
        keyboard.append([InlineKeyboardButton(f"[Operario: {op['nombre']} (@{op['username']})]", callback_data=f"login_op_user_{op['username']}")])
    keyboard.append([InlineKeyboardButton("[< Volver al Inicio]", callback_data="show_role_select")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("[Gestión Operarios]", callback_data="admin_operarios_menu"),
            InlineKeyboardButton("[Estado Máquinas]", callback_data="admin_maquinas")
        ],
        [
            InlineKeyboardButton("[Informes & KPIs]", callback_data="admin_informes"),
            InlineKeyboardButton("[Herramientas]", callback_data="admin_herramientas")
        ],
        [
            InlineKeyboardButton("[Configuración Sistema]", callback_data="admin_config_menu")
        ],
        [
            InlineKeyboardButton("[Cerrar Sesión (Logout)]", callback_data="logout_session")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_operarios_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("[Crear Operario]", callback_data="op_crear_inicio"),
            InlineKeyboardButton("[Eliminar Operario]", callback_data="admin_op_eliminar_menu")
        ],
        [
            InlineKeyboardButton("[Ver Stats de Operario]", callback_data="admin_op_stats_menu")
        ],
        [
            InlineKeyboardButton("[< Volver al Menú Admin]", callback_data="menu_admin")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_operarios_list_keyboard(operarios, action_prefix: str):
    keyboard = []
    for op in operarios:
        btn_text = f"[Eliminar: {op['nombre']} (@{op['username']})]" if "del" in action_prefix else f"[Operario: {op['nombre']} (@{op['username']})]"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"{action_prefix}_{op['id']}")])
    keyboard.append([InlineKeyboardButton("[< Volver]", callback_data="admin_operarios_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_config_menu_keyboard(configs):
    keyboard = []
    for c in configs:
        clave = c['clave']
        label = f"[{clave}: {c['valor']}]"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"edit_cfg_{clave}")])
    keyboard.append([InlineKeyboardButton("[< Volver al Menú Admin]", callback_data="menu_admin")])
    return InlineKeyboardMarkup(keyboard)

def get_operario_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("[Asignarme a Máquina]", callback_data="op_asignar_maquina"),
            InlineKeyboardButton("[Seleccionar Herramienta]", callback_data="op_seleccionar_herramienta")
        ],
        [
            InlineKeyboardButton("[Finalizar Actividad]", callback_data="op_finalizar_actividad")
        ],
        [
            InlineKeyboardButton("[Cerrar Sesión (Logout)]", callback_data="logout_session")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_informes_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("[Último Turno (7 Días)]", callback_data="reporte_turno"),
            InlineKeyboardButton("[Semana Completa]", callback_data="reporte_semana")
        ],
        [
            InlineKeyboardButton("[< Volver al Menú Admin]", callback_data="menu_admin")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_maquinas_select_keyboard(maquinas, callback_prefix: str):
    keyboard = []
    for m in maquinas:
        keyboard.append([InlineKeyboardButton(f"[{m['nombre']} - {m['tipo']}]", callback_data=f"{callback_prefix}_{m['id']}")])
    keyboard.append([InlineKeyboardButton("[< Volver]", callback_data="menu_principal")])
    return InlineKeyboardMarkup(keyboard)

def get_herramientas_select_keyboard(herramientas, callback_prefix: str):
    keyboard = []
    for h in herramientas:
        keyboard.append([InlineKeyboardButton(f"[{h['nombre']}]", callback_data=f"{callback_prefix}_{h['id']}")])
    keyboard.append([InlineKeyboardButton("[< Volver]", callback_data="menu_principal")])
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard(return_callback="menu_admin"):
    keyboard = [[InlineKeyboardButton("[Cancelar]", callback_data=return_callback)]]
    return InlineKeyboardMarkup(keyboard)
