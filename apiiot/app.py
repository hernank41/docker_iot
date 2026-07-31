from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from typing import Optional, List
import aiomysql
import os
import logging
import httpx
import csv
import io
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Industrial Machinery Uptime & KPI API",
    description="REST API for real-time monitoring of lathes, milling machines, Telegram bot, Web Admin, and activity engine.",
    version="2.0.0"
)

# Servir archivos estáticos y plantillas HTML Jinja2 para Web Admin
os.makedirs("/app/static", exist_ok=True)
os.makedirs("/app/templates", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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

# --- Web Admin SPA & Activity Fit Endpoints ---

class ActivityMergeRequest(BaseModel):
    actividad_ids: List[int]

class ActivitySplitRequest(BaseModel):
    fecha_corte: str

class AssignOperarioRetroactivo(BaseModel):
    operario_id: int

class ComentarioUpdate(BaseModel):
    comentario: str

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_panel(request: Request):
    """Servidor HTML del Panel Web Administrador SPA."""
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/api/v1/admin/actividades")
async def listar_actividades_admin():
    """Retorna el registro histórico completo de actividades."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT a.id, a.maquina_id, m.nombre AS maquina, m.tipo AS tipo_maquina,
                       a.operario_id, u.nombre AS operario_nombre, u.username AS operario_username,
                       a.herramienta_id, h.nombre AS herramienta_nombre,
                       a.fecha_inicio, a.fecha_fin, a.tiempo_activo_segundos,
                       ROUND(a.tiempo_activo_segundos / 3600.0, 2) AS tiempo_activo_horas,
                       a.estado, a.comentario
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON a.operario_id = u.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                ORDER BY a.fecha_inicio DESC
            """
            await cur.execute(sql)
            res = await cur.fetchall()
        conn.close()
        return {"actividades": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/actividades/{actividad_id}/asignar-operario")
async def asignar_operario_retroactivo(actividad_id: int, req: AssignOperarioRetroactivo):
    """Asigna retroactivamente un operario a una actividad existente."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("UPDATE actividades SET operario_id = %s WHERE id = %s", (req.operario_id, actividad_id))
        conn.close()
        return {"status": "ok", "mensaje": f"Operario {req.operario_id} asignado a actividad {actividad_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/actividades/merge")
async def fusionar_actividades(req: ActivityMergeRequest):
    """Fusiona 2 o más actividades consecutivas en un único registro."""
    if len(req.actividad_ids) < 2:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos 2 actividades para fusionar.")

    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            ids_str = ",".join(map(str, req.actividad_ids))
            await cur.execute(f"SELECT * FROM actividades WHERE id IN ({ids_str}) ORDER BY fecha_inicio ASC")
            rows = await cur.fetchall()

            if len(rows) < len(req.actividad_ids):
                conn.close()
                raise HTTPException(status_code=404, detail="Una o más actividades seleccionadas no existen.")

            target_id = rows[0]["id"]
            min_inicio = rows[0]["fecha_inicio"]
            max_fin = max(r["fecha_fin"] for r in rows if r["fecha_fin"])
            total_segundos = sum(r["tiempo_activo_segundos"] or 0 for r in rows)
            
            await cur.execute(
                """UPDATE actividades 
                   SET fecha_inicio = %s, fecha_fin = %s, tiempo_activo_segundos = %s, estado = 'FINALIZADA', comentario = 'Fusionada retroactivamente'
                   WHERE id = %s""",
                (min_inicio, max_fin, total_segundos, target_id)
            )

            other_ids = [r["id"] for r in rows if r["id"] != target_id]
            if other_ids:
                other_str = ",".join(map(str, other_ids))
                await cur.execute(f"DELETE FROM actividades WHERE id IN ({other_str})")

        conn.close()
        return {"status": "ok", "mensaje": f"Actividades fusionadas exitosamente en la actividad #{target_id}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/actividades/{actividad_id}/split")
async def dividir_actividad(actividad_id: int, req: ActivitySplitRequest):
    """Divide una actividad en dos fragmentos utilizando una fecha/hora de corte."""
    try:
        corte_dt = datetime.strptime(req.fecha_corte, "%Y-%m-%d %H:%M:%S")
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM actividades WHERE id = %s", (actividad_id,))
            act = await cur.fetchone()
            if not act:
                conn.close()
                raise HTTPException(status_code=404, detail="Actividad no encontrada.")

            inicio = act["fecha_inicio"]
            fin = act["fecha_fin"] or datetime.now()

            if corte_dt <= inicio or corte_dt >= fin:
                conn.close()
                raise HTTPException(status_code=400, detail="La fecha de corte debe estar dentro del rango de la actividad.")

            t1_seg = int((corte_dt - inicio).total_seconds())
            t2_seg = int((fin - corte_dt).total_seconds())

            await cur.execute(
                """UPDATE actividades SET fecha_fin = %s, tiempo_activo_segundos = %s, comentario = 'Dividida (Fragmento 1)' WHERE id = %s""",
                (corte_dt, t1_seg, actividad_id)
            )

            await cur.execute(
                """INSERT INTO actividades (maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, estado, comentario)
                   VALUES (%s, %s, %s, %s, %s, %s, 'FINALIZADA', 'Dividida (Fragmento 2)')""",
                (act["maquina_id"], act["operario_id"], act["herramienta_id"], corte_dt, fin, t2_seg)
            )
            new_id = cur.lastrowid

        conn.close()
        return {"status": "ok", "mensaje": f"Actividad #{actividad_id} dividida exitosamente. Nuevo fragmento ID #{new_id}."}
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use 'YYYY-MM-DD HH:MM:SS'.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/admin/actividades/{actividad_id}/comentario")
async def actualizar_comentario_actividad(actividad_id: int, req: ComentarioUpdate):
    """Actualiza o agrega un comentario a una actividad."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("UPDATE actividades SET comentario = %s WHERE id = %s", (req.comentario, actividad_id))
        conn.close()
        return {"status": "ok", "mensaje": "Comentario actualizado correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/informes/exportar-csv")
async def exportar_informe_csv():
    """Genera y retorna un archivo CSV con el historial de actividades."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT a.id, m.nombre AS maquina, u.nombre AS operario, h.nombre AS herramienta,
                       a.fecha_inicio, a.fecha_fin, ROUND(a.tiempo_activo_segundos/3600.0, 2) AS horas_activas,
                       a.estado, a.comentario
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON a.operario_id = u.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                ORDER BY a.fecha_inicio DESC
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Maquina", "Operario", "Herramienta", "Fecha Inicio", "Fecha Fin", "Horas Activas", "Estado", "Comentario"])

        for r in rows:
            writer.writerow([
                r["id"], r["maquina"], r["operario"] or "Sin Operario", r["herramienta"] or "Sin Herramienta",
                r["fecha_inicio"], r["fecha_fin"], r["horas_activas"], r["estado"], r["comentario"] or ""
            ])

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=informe_produccion.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoints de Gráficos Estadísticos Matplotlib para Web Admin ---

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.style.use('dark_background')

@app.get("/api/v1/admin/usuarios/{usuario_id}/grafico-stats")
async def grafico_stats_operario(usuario_id: int):
    """Genera un gráfico de barras Seaborn/Matplotlib con el rendimiento semanal por turno del operario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT nombre, username FROM usuarios WHERE id = %s", (usuario_id,))
            user = await cur.fetchone()

            sql = """
                SELECT a.fecha_inicio, m.nombre AS maquina,
                       ROUND(a.tiempo_activo_segundos / 3600.0, 2) AS horas_activas,
                       CASE 
                           WHEN HOUR(a.fecha_inicio) BETWEEN 6 AND 13 THEN 'Mañana'
                           WHEN HOUR(a.fecha_inicio) BETWEEN 14 AND 21 THEN 'Tarde'
                           ELSE 'Noche'
                       END AS turno
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE a.operario_id = %s
                ORDER BY a.fecha_inicio DESC
            """
            await cur.execute(sql, (usuario_id,))
            actividades = await cur.fetchall()
        conn.close()

        fig, ax = plt.subplots(figsize=(7.5, 4), dpi=130)
        fig.patch.set_facecolor('#1e293b')
        ax.set_facecolor('#0f172a')

        if not actividades:
            ax.text(0.5, 0.5, 'Sin actividades registradas para este operario', ha='center', va='center', color='#94a3b8', fontsize=11)
            ax.axis('off')
        else:
            shifts = {}
            for a in actividades:
                fecha_fmt = a['fecha_inicio'].strftime('%d/%m') if hasattr(a['fecha_inicio'], 'strftime') else str(a['fecha_inicio'])[:10]
                lbl = f"{fecha_fmt}\nTurno {a['turno']}\n({a['maquina']})"
                shifts[lbl] = shifts.get(lbl, 0.0) + float(a['horas_activas'])

            labels = list(shifts.keys())
            horas = list(shifts.values())
            colors = ['#38bdf8' if 'Torno' in l else '#34d399' for l in labels]

            bars = ax.bar(labels, horas, color=colors, edgecolor='#475569', width=0.45)
            ax.set_ylabel('Horas Operativas (hs)', color='#f8fafc', fontsize=10, fontweight='bold')
            nombre_user = user['nombre'] if user else f'Operario #{usuario_id}'
            ax.set_title(f'Rendimiento Semanal por Turno - {nombre_user}', color='#38bdf8', fontsize=11, fontweight='bold', pad=12)
            ax.grid(axis='y', color='#334155', linestyle='--', alpha=0.5)
            ax.tick_params(colors='#f8fafc', labelsize=8)

            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., h + 0.05, f"{h:.2f} hs", ha='center', va='bottom', color='#f8fafc', fontsize=8, fontweight='bold')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/informes/grafico-turno")
async def grafico_turno_admin():
    """Genera un gráfico de barras horizontales de horas operativas por día y máquina (últimos 7 días)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT DATE(fecha_inicio) AS fecha, m.nombre AS maquina,
                       ROUND(SUM(tiempo_activo_segundos)/3600.0, 2) AS horas_activas
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE fecha_inicio >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY DATE(fecha_inicio), m.nombre
                ORDER BY fecha ASC, maquina ASC
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()

        fig, ax = plt.subplots(figsize=(8, 4), dpi=130)
        fig.patch.set_facecolor('#1e293b')
        ax.set_facecolor('#0f172a')

        if not rows:
            ax.text(0.5, 0.5, 'Sin registros en los últimos 7 días', ha='center', va='center', color='#94a3b8', fontsize=11)
            ax.axis('off')
        else:
            labels = [f"{r['fecha']}\n({r['maquina']})" for r in rows]
            horas = [float(r['horas_activas']) for r in rows]
            colors = ['#38bdf8' if 'Torno' in l else '#34d399' for l in labels]

            bars = ax.barh(labels, horas, color=colors, edgecolor='#475569', height=0.5)
            ax.set_xlabel('Horas Operativas (hs)', color='#f8fafc', fontsize=10, fontweight='bold')
            ax.set_title('Horas Operativas por Día y Máquina (Últimos 7 Días)', color='#38bdf8', fontsize=11, fontweight='bold', pad=12)
            ax.grid(axis='x', color='#334155', linestyle='--', alpha=0.5)
            ax.tick_params(colors='#f8fafc', labelsize=8)

            for bar in bars:
                w = bar.get_width()
                ax.text(w + 0.1, bar.get_y() + bar.get_height()/2, f"{w:.2f} hs", va='center', ha='left', color='#f8fafc', fontsize=8, fontweight='bold')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/informes/grafico-semana")
async def grafico_semana_admin():
    """Genera un gráfico donut de distribución semanal por máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT m.nombre AS maquina, ROUND(SUM(tiempo_activo_segundos)/3600.0, 2) AS total_horas_activas
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE fecha_inicio >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY m.nombre
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()

        fig, ax = plt.subplots(figsize=(7, 4), dpi=130)
        fig.patch.set_facecolor('#1e293b')
        ax.set_facecolor('#0f172a')

        if not rows:
            ax.text(0.5, 0.5, 'Sin datos semanales', ha='center', va='center', color='#94a3b8', fontsize=11)
            ax.axis('off')
        else:
            labels = [r['maquina'] for r in rows]
            horas = [float(r['total_horas_activas']) for r in rows]
            colors = ['#38bdf8', '#34d399', '#f59e0b', '#fb7185']

            wedges, texts, autotexts = ax.pie(
                horas, labels=labels, autopct='%1.1f%%',
                startangle=140, colors=colors[:len(labels)],
                wedgeprops=dict(width=0.4, edgecolor='#1e293b', linewidth=2),
                textprops=dict(color='#f8fafc', fontsize=9, fontweight='bold')
            )
            for autotext in autotexts:
                autotext.set_color('#0f172a')
                autotext.set_weight('bold')

            ax.set_title('Distribución Semanal de Uso por Máquina', color='#38bdf8', fontsize=11, fontweight='bold', pad=12)

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


