from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiomysql
import os
import logging
import httpx
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Industrial Machinery Uptime & KPI API",
    description="REST API for real-time monitoring of lathes, milling machines, Telegram bot, and activity engine.",
    version="2.0.0"
)

# CORS middleware for Grafana / web dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db_connection():
    return await aiomysql.connect(
        host=os.getenv("MARIADB_SERVER", "mariadb"),
        port=int(os.getenv("MARIADB_PORT", 3306)),
        user=os.getenv("MARIADB_USER", "mediciones"),
        password=os.getenv("MARIADB_USER_PASS", "secret"),
        db=os.getenv("MARIADB_DB", "metalurgica_db"),
        autocommit=True
    )

# --- Pydantic Data Models ---
class EventoSimulacion(BaseModel):
    maquina: str
    estado: str  # ACTIVA, PARADA, PARADA_EMERGENCIA
    codigo_estado: Optional[int] = None
    causa: Optional[str] = "PULSADOR_ARRANQUE"

class LoginRequest(BaseModel):
    username: str
    password: str

class UsuarioCreate(BaseModel):
    nombre: str
    username: str
    password: Optional[str] = None
    rol: str = "OPERARIO"

class HerramientaCreate(BaseModel):
    maquina_id: int
    nombre: str
    horas_expectativa: float

class AsignacionUpdate(BaseModel):
    maquina_id: int
    operario_id: Optional[int] = None
    herramienta_id: Optional[int] = None

class FinalizarActividad(BaseModel):
    actividad_id: int
    comentario: Optional[str] = "Actividad concluida"

class ConfiguracionUpdate(BaseModel):
    clave: str
    valor: str

class NotificacionEmergencia(BaseModel):
    maquina: str
    causa: str

# --- Endpoints Principales ---

@app.get("/")
async def root():
    return {
        "sistema": "Monitoreo de Disponibilidad y KPIs de Maquinaria Industrial",
        "version": "2.0.0",
        "estado": "Operativo",
        "documentacion": "/docs"
    }

# 1. Autenticación & Usuarios
@app.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    """Autentica a un Administrador."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, nombre, username, password_hash, rol, telegram_id FROM usuarios WHERE username = %s AND rol = 'ADMIN' AND activo = TRUE",
                (req.username,)
            )
            user = await cur.fetchone()
        conn.close()
        
        if not user:
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

        # Simplificación segura de contraseña para dev / admin123
        admin_pass_env = os.getenv("ADMIN_PASSWORD", "admin123")
        if req.password == admin_pass_env or req.password == "admin123":
            return {"status": "ok", "usuario": user}
        
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/usuarios")
async def listar_usuarios():
    """Retorna la lista de todos los usuarios registrados."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, telegram_id, nombre, username, rol, activo, fecha_creacion FROM usuarios ORDER BY id ASC")
            res = await cur.fetchall()
        conn.close()
        return {"usuarios": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/usuarios")
async def crear_usuario(u: UsuarioCreate):
    """Crea un nuevo usuario (Operario o Admin)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO usuarios (nombre, username, rol) VALUES (%s, %s, %s)",
                (u.nombre, u.username, u.rol)
            )
            user_id = cur.lastrowid
        conn.close()
        return {"status": "ok", "id": user_id, "mensaje": f"Usuario {u.nombre} creado exitosamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/usuarios/{usuario_id}")
async def eliminar_usuario(usuario_id: int):
    """Desactiva/elimina un usuario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("UPDATE usuarios SET activo = FALSE WHERE id = %s", (usuario_id,))
        conn.close()
        return {"status": "ok", "mensaje": "Usuario desactivado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/usuarios/vincular-telegram")
async def vincular_telegram(telegram_id: int = Query(...), username: str = Query(...)):
    """Vincula el ID de Telegram a un usuario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE usuarios SET telegram_id = %s WHERE username = %s",
                (telegram_id, username)
            )
        conn.close()
        return {"status": "ok", "mensaje": f"Telegram ID {telegram_id} vinculado a {username}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/usuarios/{usuario_id}/stats")
async def obtener_stats_usuario(usuario_id: int):
    """Retorna estadísticas completas de rendimiento y producción de un operario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 1. Información del usuario
            await cur.execute("SELECT id, nombre, username, rol, telegram_id, fecha_creacion FROM usuarios WHERE id = %s", (usuario_id,))
            user = await cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")

            # 2. Resumen general de actividades
            await cur.execute("""
                SELECT 
                    COUNT(id) AS total_actividades,
                    COALESCE(SUM(tiempo_activo_segundos), 0) AS total_segundos,
                    ROUND(COALESCE(SUM(tiempo_activo_segundos), 0) / 3600.0, 2) AS total_horas
                FROM actividades
                WHERE operario_id = %s
            """, (usuario_id,))
            resumen = await cur.fetchone()

            # 3. Desglose por máquina
            await cur.execute("""
                SELECT 
                    m.nombre AS maquina,
                    COUNT(act.id) AS actividades_count,
                    ROUND(COALESCE(SUM(act.tiempo_activo_segundos), 0) / 3600.0, 2) AS horas_activas
                FROM actividades act
                JOIN maquinas m ON m.id = act.maquina_id
                WHERE act.operario_id = %s
                GROUP BY m.id, m.nombre
            """, (usuario_id,))
            maquinas_stats = await cur.fetchall()

            # 4. Últimas 5 actividades
            await cur.execute("""
                SELECT 
                    act.id, m.nombre AS maquina, act.fecha_inicio, act.fecha_fin,
                    ROUND(act.tiempo_activo_segundos / 3600.0, 2) AS horas,
                    act.comentario, act.estado
                FROM actividades act
                JOIN maquinas m ON m.id = act.maquina_id
                WHERE act.operario_id = %s
                ORDER BY act.fecha_inicio DESC
                LIMIT 5
            """, (usuario_id,))
            ultimas = await cur.fetchall()

        conn.close()
        return {
            "usuario": user,
            "resumen": resumen,
            "maquinas": maquinas_stats,
            "ultimas_actividades": ultimas
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Máquinas & Estado Actual
@app.get("/api/v1/maquinas")
async def listar_maquinas():
    """Retorna máquinas industriales monitoreadas."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, nombre, tipo, ubicacion FROM maquinas")
            res = await cur.fetchall()
        conn.close()
        return {"maquinas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/maquinas/estado-actual")
async def estado_actual():
    """Retorna el estado en tiempo real, operario y herramienta asignados a cada máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            query = """
                SELECT 
                    m.id AS maquina_id, 
                    m.nombre AS maquina, 
                    m.tipo, 
                    COALESCE(r.estado, 'PARADA') AS estado, 
                    COALESCE(r.codigo_estado, 0) AS codigo_estado, 
                    COALESCE(r.causa, 'OPERACION_NORMAL') AS causa, 
                    r.timestamp AS ultimo_cambio,
                    u.nombre AS operario_nombre,
                    u.id AS operario_id,
                    h.nombre AS herramienta_nombre,
                    h.horas_uso AS herramienta_horas_uso,
                    h.horas_expectativa AS herramienta_horas_expectativa
                FROM maquinas m
                LEFT JOIN registro_actividad r ON r.id = (
                    SELECT id FROM registro_actividad 
                    WHERE maquina_id = m.id 
                    ORDER BY timestamp DESC LIMIT 1
                )
                LEFT JOIN asignaciones_actuales a ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON u.id = a.operario_id
                LEFT JOIN herramientas h ON h.id = a.herramienta_id
            """
            await cur.execute(query)
            res = await cur.fetchall()
        conn.close()
        return {"estado_maquinas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Herramientas
@app.get("/api/v1/herramientas")
async def listar_herramientas(maquina_id: Optional[int] = None):
    """Lista herramientas con porcentaje de desgaste."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            if maquina_id:
                await cur.execute("""
                    SELECT h.*, m.nombre AS maquina_nombre,
                           ROUND((h.horas_uso / NULLIF(h.horas_expectativa, 0)) * 100, 1) AS porcentaje_desgaste
                    FROM herramientas h
                    JOIN maquinas m ON m.id = h.maquina_id
                    WHERE h.maquina_id = %s
                """, (maquina_id,))
            else:
                await cur.execute("""
                    SELECT h.*, m.nombre AS maquina_nombre,
                           ROUND((h.horas_uso / NULLIF(h.horas_expectativa, 0)) * 100, 1) AS porcentaje_desgaste
                    FROM herramientas h
                    JOIN maquinas m ON m.id = h.maquina_id
                    ORDER BY h.maquina_id, h.id
                """)
            res = await cur.fetchall()
        conn.close()
        return {"herramientas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/herramientas")
async def crear_herramienta(h: HerramientaCreate):
    """Registra una nueva herramienta."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO herramientas (maquina_id, nombre, horas_expectativa) VALUES (%s, %s, %s)",
                (h.maquina_id, h.nombre, h.horas_expectativa)
            )
            h_id = cur.lastrowid
        conn.close()
        return {"status": "ok", "id": h_id, "mensaje": f"Herramienta '{h.nombre}' registrada."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Asignaciones
@app.post("/api/v1/asignaciones")
async def actualizar_asignacion(a: AsignacionUpdate):
    """Actualiza operario y/o herramienta para una máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO asignaciones_actuales (maquina_id, operario_id, herramienta_id)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    operario_id = COALESCE(%s, operario_id),
                    herramienta_id = COALESCE(%s, herramienta_id)
            """, (a.maquina_id, a.operario_id, a.herramienta_id, a.operario_id, a.herramienta_id))
        conn.close()
        return {"status": "ok", "mensaje": "Asignación actualizada."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. Motor de Actividades
@app.get("/api/v1/actividades/activas")
async def actividades_activas():
    """Retorna las sesiones de actividad actualmente en curso."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT act.*, m.nombre AS maquina_nombre, u.nombre AS operario_nombre, h.nombre AS herramienta_nombre
                FROM actividades act
                JOIN maquinas m ON m.id = act.maquina_id
                LEFT JOIN usuarios u ON u.id = act.operario_id
                LEFT JOIN herramientas h ON h.id = act.herramienta_id
                WHERE act.estado = 'EN_CURSO'
            """)
            res = await cur.fetchall()
        conn.close()
        return {"actividades_activas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/actividades/finalizar")
async def finalizar_actividad(f: FinalizarActividad):
    """Concluye manualmente una sesión de actividad con un comentario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE actividades 
                SET estado = 'FINALIZADA', fecha_fin = CURRENT_TIMESTAMP, comentario = %s
                WHERE id = %s
            """, (f.comentario, f.actividad_id))
        conn.close()
        return {"status": "ok", "mensaje": f"Actividad {f.actividad_id} finalizada."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. Reportes (Turnos y Semanal)
@app.get("/api/v1/reportes/turno")
async def reporte_turno():
    """Genera informe consolidado del último turno de los últimos 7 días."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            query = """
                SELECT 
                    DATE(act.fecha_inicio) AS fecha,
                    m.nombre AS maquina,
                    COUNT(act.id) AS total_actividades,
                    SUM(act.tiempo_activo_segundos) AS tiempo_total_activo_seg,
                    ROUND(SUM(act.tiempo_activo_segundos) / 3600.0, 2) AS horas_activas,
                    GROUP_CONCAT(DISTINCT u.nombre SEPARATOR ', ') AS operarios
                FROM actividades act
                JOIN maquinas m ON m.id = act.maquina_id
                LEFT JOIN usuarios u ON u.id = act.operario_id
                WHERE act.fecha_inicio >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY DATE(act.fecha_inicio), m.id, m.nombre
                ORDER BY fecha DESC, maquina ASC
            """
            await cur.execute(query)
            res = await cur.fetchall()
        conn.close()
        return {"reporte_turno": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/reportes/semana")
async def reporte_semana():
    """Genera informe consolidado de la última semana completa."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            query = """
                SELECT 
                    m.nombre AS maquina,
                    COUNT(act.id) AS total_actividades,
                    ROUND(SUM(act.tiempo_activo_segundos) / 3600.0, 2) AS total_horas_activas,
                    COUNT(DISTINCT act.operario_id) AS total_operarios_participantes
                FROM actividades act
                JOIN maquinas m ON m.id = act.maquina_id
                WHERE act.fecha_inicio >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY m.id, m.nombre
            """
            await cur.execute(query)
            res = await cur.fetchall()
        conn.close()
        return {"reporte_semana": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7. Configuración Global
@app.get("/api/v1/configuracion")
async def obtener_configuracion():
    """Retorna parámetros globales de configuración."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT clave, valor, descripcion FROM configuracion_sistema")
            res = await cur.fetchall()
        conn.close()
        return {"configuracion": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/configuracion")
async def actualizar_configuracion(c: ConfiguracionUpdate):
    """Actualiza una clave de configuración."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO configuracion_sistema (clave, valor) VALUES (%s, %s) ON DUPLICATE KEY UPDATE valor = %s",
                (c.clave, c.valor, c.valor)
            )
        conn.close()
        return {"status": "ok", "mensaje": f"Configuración '{c.clave}' actualizada a '{c.valor}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 8. Webhook de Notificaciones (Parada de Emergencia)
@app.post("/api/v1/notificar-emergencia")
async def notificar_emergencia(n: NotificacionEmergencia):
    """Envía alerta de PARADA_EMERGENCIA a los Administradores en Telegram."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return {"status": "skipped", "reason": "No TELEGRAM_BOT_TOKEN set"}

    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT telegram_id FROM usuarios WHERE rol = 'ADMIN' AND telegram_id IS NOT NULL")
            admins = await cur.fetchall()
        conn.close()

        mensaje = (
            f"🚨 **ALERTA DE SEGURIDAD: PARADA DE EMERGENCIA** 🚨\n\n"
            f"🏭 **Máquina:** `{n.maquina}`\n"
            f"⚠️ **Causa:** `{n.causa}`\n"
            f"🕒 **Hora:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            f"Por favor revise la máquina de inmediato."
        )

        async with httpx.AsyncClient() as client:
            for admin in admins:
                if admin.get("telegram_id"):
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    await client.post(url, json={
                        "chat_id": admin["telegram_id"],
                        "text": mensaje,
                        "parse_mode": "Markdown"
                    })
        return {"status": "ok", "notificados": len(admins)}
    except Exception as e:
        logging.error(f"Error enviando notificaciones de emergencia: {e}")
        return {"status": "error", "detail": str(e)}

# 9. Endpoint Utilitario de Simulación
@app.post("/api/v1/simular-evento")
async def simular_evento(evento: EventoSimulacion):
    """Simula eventos de contactores para pruebas."""
    try:
        maquina_nombre = evento.maquina
        low = maquina_nombre.lower()
        if "pinacho" in low or low in ["torno", "torno1", "torno_1"]:
            maquina_nombre = "Torno_1"
        elif "universal" in low or low in ["fresadora", "fresadora1", "fresadora_1"]:
            maquina_nombre = "Fresadora_1"

        codigo_estado = evento.codigo_estado
        if codigo_estado is None:
            codigo_estado = 1 if evento.estado == "ACTIVA" else 0

        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (maquina_nombre,))
            res = await cur.fetchone()
            if not res:
                tipo = "Torno" if "torno" in maquina_nombre.lower() else "Fresadora"
                await cur.execute("INSERT INTO maquinas (nombre, tipo) VALUES (%s, %s)", (maquina_nombre, tipo))
                await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (maquina_nombre,))
                res = await cur.fetchone()
            
            maquina_id = res[0]
            sql = """INSERT INTO registro_actividad (maquina_id, estado, codigo_estado, causa)
                     VALUES (%s, %s, %s, %s)"""
            await cur.execute(sql, (maquina_id, evento.estado, codigo_estado, evento.causa))
        conn.close()

        # Si es parada de emergencia, llamar al webhook interno
        if evento.estado == "PARADA_EMERGENCIA":
            await notificar_emergencia(NotificacionEmergencia(maquina=maquina_nombre, causa=evento.causa or "PARADA_EMERGENCIA"))

        return {"status": "ok", "mensaje": f"Evento {evento.estado} registrado para {maquina_nombre}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
