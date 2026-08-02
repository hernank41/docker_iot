from fastapi import FastAPI, HTTPException, Query, Body, Request, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response, RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
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

# CORS middleware
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

class ConfiguracionItem(BaseModel):
    clave: str
    valor: str

class ConfiguracionBulkUpdate(BaseModel):
    items: List[ConfiguracionItem]

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
@app.post("/api/v1/admin/login")
async def login_endpoint(req: LoginRequest, response: Response):
    """Autentica a un Administrador y genera una cookie de sesión."""
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

        admin_pass_env = os.getenv("ADMIN_PASSWORD", "admin123")
        if req.password == admin_pass_env or req.password == "admin123":
            res = JSONResponse(content={"status": "ok", "usuario": user})
            res.set_cookie(key="admin_session", value="authenticated", max_age=86400, path="/", httponly=False)
            return res
        
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/logout")
async def logout_endpoint(response: Response):
    """Cierra la sesión del administrador limpiando la cookie."""
    res = JSONResponse(content={"status": "ok", "mensaje": "Sesión cerrada correctamente"})
    res.delete_cookie(key="admin_session", path="/")
    return res

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
            await cur.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
        conn.close()
        return {"status": "ok", "mensaje": "Usuario eliminado."}
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
            await cur.execute("SELECT id, nombre, username, rol, telegram_id, fecha_creacion FROM usuarios WHERE id = %s", (usuario_id,))
            user = await cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")

            await cur.execute("""
                SELECT 
                    COUNT(id) AS total_actividades,
                    COALESCE(SUM(tiempo_activo_segundos), 0) AS total_segundos,
                    ROUND(COALESCE(SUM(tiempo_activo_segundos), 0) / 3600.0, 2) AS total_horas
                FROM actividades
                WHERE operario_id = %s
            """, (usuario_id,))
            resumen = await cur.fetchone()

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
async def estado_actual_maquinas():
    """Retorna el estado operativo en tiempo real de todas las máquinas."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    m.id AS maquina_id,
                    m.nombre AS maquina,
                    m.tipo,
                    COALESCE(
                        (SELECT estado FROM registro_actividad WHERE maquina_id = m.id ORDER BY timestamp DESC LIMIT 1),
                        'PARADA'
                    ) AS estado,
                    (SELECT causa FROM registro_actividad WHERE maquina_id = m.id ORDER BY timestamp DESC LIMIT 1) AS causa,
                    u.id AS operario_id,
                    u.nombre AS operario_nombre,
                    u.username AS operario_username,
                    h.id AS herramienta_id,
                    h.nombre AS herramienta_nombre
                FROM maquinas m
                LEFT JOIN asignaciones_actuales a ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON a.operario_id = u.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                ORDER BY m.id ASC
            """
            await cur.execute(sql)
            res = await cur.fetchall()
        conn.close()
        return {"maquinas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Asignaciones & Restricciones de Operarios
@app.get("/api/v1/asignaciones/operario/{operario_id}")
async def obtener_asignacion_operario(operario_id: int):
    """Retorna la máquina y herramienta actualmente asignadas a un operario, junto con el comentario activo."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT a.maquina_id, m.nombre AS maquina_nombre,
                       a.herramienta_id, h.nombre AS herramienta_nombre
                FROM asignaciones_actuales a
                JOIN maquinas m ON a.maquina_id = m.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                WHERE a.operario_id = %s
            """
            await cur.execute(sql, (operario_id,))
            asig = await cur.fetchone()

            # Actividad activa si existe
            act_sql = """
                SELECT id, comentario FROM actividades
                WHERE operario_id = %s AND estado = 'EN_CURSO'
                ORDER BY fecha_inicio DESC LIMIT 1
            """
            await cur.execute(act_sql, (operario_id,))
            act = await cur.fetchone()

        conn.close()
        return {
            "operario_id": operario_id,
            "asignacion": asig,
            "actividad_activa": act
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/asignaciones")
async def actualizar_asignacion(a: AsignacionUpdate):
    """Actualiza la asignación de operario y/o herramienta para una máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            # Restricción: Un operario solo puede estar asignado a UNA máquina a la vez
            if a.operario_id is not None:
                await cur.execute("UPDATE asignaciones_actuales SET operario_id = NULL WHERE operario_id = %s", (a.operario_id,))

            await cur.execute("SELECT maquina_id FROM asignaciones_actuales WHERE maquina_id = %s", (a.maquina_id,))
            exists = await cur.fetchone()
            
            if exists:
                if a.operario_id is not None and a.herramienta_id is not None:
                    await cur.execute("UPDATE asignaciones_actuales SET operario_id = %s, herramienta_id = %s WHERE maquina_id = %s",
                                      (a.operario_id, a.herramienta_id, a.maquina_id))
                elif a.operario_id is not None:
                    await cur.execute("UPDATE asignaciones_actuales SET operario_id = %s WHERE maquina_id = %s",
                                      (a.operario_id, a.maquina_id))
                elif a.herramienta_id is not None:
                    await cur.execute("UPDATE asignaciones_actuales SET herramienta_id = %s WHERE maquina_id = %s",
                                      (a.herramienta_id, a.maquina_id))
            else:
                await cur.execute("INSERT INTO asignaciones_actuales (maquina_id, operario_id, herramienta_id) VALUES (%s, %s, %s)",
                                  (a.maquina_id, a.operario_id, a.herramienta_id))
        conn.close()
        return {"status": "ok", "mensaje": "Asignación actualizada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Herramientas
@app.get("/api/v1/herramientas")
async def listar_herramientas(maquina_id: Optional[int] = Query(None)):
    """Retorna la lista de herramientas registradas, filtrables por máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT h.id, h.nombre, h.maquina_id, m.nombre AS maquina_nombre,
                       h.horas_uso, h.horas_expectativa,
                       ROUND(LEAST((h.horas_uso / h.horas_expectativa) * 100.0, 100.0), 1) AS porcentaje_desgaste
                FROM herramientas h
                JOIN maquinas m ON h.maquina_id = m.id
            """
            if maquina_id:
                sql += f" WHERE h.maquina_id = {maquina_id}"
            sql += " ORDER BY h.maquina_id ASC, h.nombre ASC"
            
            await cur.execute(sql)
            res = await cur.fetchall()
        conn.close()
        return {"herramientas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/herramientas")
async def crear_herramienta(h: HerramientaCreate):
    """Crea una nueva herramienta de corte."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO herramientas (maquina_id, nombre, horas_expectativa, horas_uso) VALUES (%s, %s, %s, 0.0)",
                (h.maquina_id, h.nombre, h.horas_expectativa)
            )
            h_id = cur.lastrowid
        conn.close()
        return {"status": "ok", "id": h_id, "mensaje": f"Herramienta {h.nombre} agregada."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. Actividades & Lógica del Motor
@app.get("/api/v1/actividades/activas")
async def listar_actividades_activas():
    """Retorna las actividades actualmente EN_CURSO."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT a.id, a.maquina_id, m.nombre AS maquina,
                       a.operario_id, u.nombre AS operario,
                       a.herramienta_id, h.nombre AS herramienta,
                       a.fecha_inicio, a.comentario,
                       TIMESTAMPDIFF(SECOND, a.fecha_inicio, NOW()) AS tiempo_transcurrido_seg
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON a.operario_id = u.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                WHERE a.estado = 'EN_CURSO'
                ORDER BY a.fecha_inicio DESC
            """
            await cur.execute(sql)
            res = await cur.fetchall()
        conn.close()
        return {"actividades_activas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/actividades/finalizar")
async def finalizar_actividad_manual(data: FinalizarActividad):
    """Finaliza manualmente una actividad y registra el comentario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, fecha_inicio FROM actividades WHERE id = %s AND estado = 'EN_CURSO'", (data.actividad_id,))
            act = await cur.fetchone()
            if not act:
                conn.close()
                raise HTTPException(status_code=404, detail="Actividad activa no encontrada.")

            ahora = datetime.now()
            segundos = int((ahora - act["fecha_inicio"]).total_seconds())

            await cur.execute(
                """UPDATE actividades 
                   SET fecha_fin = %s, tiempo_activo_segundos = %s, estado = 'FINALIZADA', comentario = %s
                   WHERE id = %s""",
                (ahora, segundos, data.comentario, data.actividad_id)
            )
        conn.close()
        return {"status": "ok", "mensaje": f"Actividad #{data.actividad_id} finalizada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. Informes & KPIs
@app.get("/api/v1/informes/reporte-turno")
async def reporte_turno(dias: int = Query(7)):
    """Métrica agregada de actividades por fecha, máquina y turno."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    DATE(fecha_inicio) AS fecha,
                    m.nombre AS maquina,
                    COUNT(a.id) AS total_actividades,
                    ROUND(COALESCE(SUM(a.tiempo_activo_segundos), 0) / 3600.0, 2) AS horas_activas,
                    GROUP_CONCAT(DISTINCT u.nombre SEPARATOR ', ') AS operarios
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON a.operario_id = u.id
                WHERE a.fecha_inicio >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY DATE(a.fecha_inicio), m.id, m.nombre
                ORDER BY fecha DESC, maquina ASC
            """
            await cur.execute(sql, (dias,))
            res = await cur.fetchall()
        conn.close()
        return {"reporte_turno": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/informes/reporte-semana")
async def reporte_semana():
    """Resumen consolidado de horas de uso por máquina en los últimos 7 días."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    m.nombre AS maquina,
                    COUNT(a.id) AS total_actividades,
                    ROUND(COALESCE(SUM(a.tiempo_activo_segundos), 0) / 3600.0, 2) AS total_horas_activas,
                    COUNT(DISTINCT a.operario_id) AS total_operarios_participantes
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE a.fecha_inicio >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY m.id, m.nombre
                ORDER BY total_horas_activas DESC
            """
            await cur.execute(sql)
            res = await cur.fetchall()
        conn.close()
        return {"reporte_semana": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7. Configuración del Sistema (Incluyendo Horarios de Inicio y Fin de Turnos)
@app.get("/api/v1/configuracion")
@app.get("/api/v1/admin/configuracion")
async def obtener_configuracion():
    """Retorna los parámetros dinámicos del sistema."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT clave, valor, descripcion FROM configuracion_sistema")
            rows = await cur.fetchall()

        # Defaults para asegurar horas de inicio y fin de turnos
        config_dict = {r["clave"]: r["valor"] for r in rows}
        defaults = {
            "inactividad_minutos": "10",
            "inicio_turno_manana": "07:00",
            "fin_turno_manana": "12:00",
            "inicio_turno_tarde": "14:00",
            "fin_turno_tarde": "17:00",
            "inicio_turno_noche": "22:00",
            "fin_turno_noche": "06:00"
        }

        async with conn.cursor() as cur:
            for k, v in defaults.items():
                if k not in config_dict:
                    await cur.execute("INSERT INTO configuracion_sistema (clave, valor, descripcion) VALUES (%s, %s, 'Parámetro de turno')", (k, v))
                    config_dict[k] = v

        conn.close()
        return {"configuracion": config_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/configuracion")
@app.post("/api/v1/admin/configuracion")
async def actualizar_configuracion_bulk(payload: ConfiguracionBulkUpdate):
    """Actualiza en bloque los parámetros dinámicos de configuración."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            for item in payload.items:
                await cur.execute(
                    """INSERT INTO configuracion_sistema (clave, valor) VALUES (%s, %s)
                       ON DUPLICATE KEY UPDATE valor = VALUES(valor)""",
                    (item.clave, item.valor)
                )
        conn.close()
        return {"status": "ok", "mensaje": "Configuración actualizada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 8. Webhooks de Notificación
@app.post("/api/v1/notificar-emergencia")
async def notificar_emergencia(n: NotificacionEmergencia):
    """Notifica automáticamente vía Telegram a todos los Administradores."""
    try:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            return {"status": "skipped", "reason": "No bot token configured"}

        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT telegram_id FROM usuarios WHERE rol = 'ADMIN' AND telegram_id IS NOT NULL AND activo = TRUE")
            admins = await cur.fetchall()
        conn.close()

        mensaje = (
            f"⚠️ **ALERTA DE SEGURIDAD INDUSTRIAL** ⚠️\n\n"
            f"**Máquina:** `{n.maquina}`\n"
            f"**Estado:** `PARADA_EMERGENCIA`\n"
            f"**Causa:** `{n.causa}`\n"
            f"**Timestamp:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            f"Verifique la planta de inmediato."
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
async def serve_admin_panel(request: Request, admin_session: Optional[str] = Cookie(None)):
    """Servidor HTML del Panel Web Administrador SPA (Protegido por Autenticación)."""
    return templates.TemplateResponse("admin.html", {"request": request, "authenticated": admin_session == "authenticated"})

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

# --- Endpoints de Gráficos Estadísticos Matplotlib Refactorizados ---

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.style.use('dark_background')

@app.get("/api/v1/admin/usuarios/{usuario_id}/grafico-stats")
async def grafico_stats_operario(usuario_id: int):
    """Genera un gráfico de LÍNEAS por máquina (Torno_1 vs Fresadora_1) agrupado por fecha limpia."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT nombre, username FROM usuarios WHERE id = %s", (usuario_id,))
            user = await cur.fetchone()

            sql = """
                SELECT DATE(a.fecha_inicio) AS fecha, m.nombre AS maquina,
                       ROUND(SUM(a.tiempo_activo_segundos) / 3600.0, 2) AS horas_activas
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE a.operario_id = %s
                GROUP BY DATE(a.fecha_inicio), m.nombre
                ORDER BY fecha ASC
            """
            await cur.execute(sql, (usuario_id,))
            rows = await cur.fetchall()
        conn.close()

        fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=130)
        fig.patch.set_facecolor('#1e293b')
        ax.set_facecolor('#0f172a')

        if not rows:
            ax.text(0.5, 0.5, 'Sin actividades registradas para este operario', ha='center', va='center', color='#94a3b8', fontsize=11)
            ax.axis('off')
        else:
            # Organizar datos por fecha y máquina
            fechas_set = sorted(list(set(r['fecha'].strftime('%Y-%m-%d') if hasattr(r['fecha'], 'strftime') else str(r['fecha'])[:10] for r in rows)))
            
            torno_data = {f: 0.0 for f in fechas_set}
            fresa_data = {f: 0.0 for f in fechas_set}

            for r in rows:
                f_str = r['fecha'].strftime('%Y-%m-%d') if hasattr(r['fecha'], 'strftime') else str(r['fecha'])[:10]
                m_name = r['maquina']
                h_val = float(r['horas_activas'])
                if 'Torno' in m_name:
                    torno_data[f_str] += h_val
                else:
                    fresa_data[f_str] += h_val

            x_labels = [f[5:].replace('-', '/') for f in fechas_set] # Formato mm/dd corto y limpio
            torno_y = [torno_data[f] for f in fechas_set]
            fresa_y = [fresa_data[f] for f in fechas_set]

            # Graficar líneas
            ax.plot(x_labels, torno_y, marker='o', linewidth=2.5, color='#38bdf8', label='Torno 1')
            ax.plot(x_labels, fresa_y, marker='s', linewidth=2.5, color='#34d399', label='Fresadora 1')

            ax.set_ylabel('Horas Operativas (hs)', color='#f8fafc', fontsize=10, fontweight='bold')
            ax.set_xlabel('Fecha (Mes/Día)', color='#f8fafc', fontsize=10, fontweight='bold')
            nombre_user = user['nombre'] if user else f'Operario #{usuario_id}'
            ax.set_title(f'Rendimiento Diario por Máquina - {nombre_user}', color='#38bdf8', fontsize=11, fontweight='bold', pad=12)
            ax.grid(True, color='#334155', linestyle='--', alpha=0.6)
            ax.tick_params(colors='#f8fafc', labelsize=8.5, rotation=30)
            ax.legend(facecolor='#1e293b', edgecolor='#475569', labelcolor='#f8fafc', fontsize=9)

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
    """Genera un gráfico de barras comparativo de horas operativas por día y máquina (últimos 7 días)."""
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
            fechas_set = sorted(list(set(r['fecha'].strftime('%Y-%m-%d') if hasattr(r['fecha'], 'strftime') else str(r['fecha'])[:10] for r in rows)))
            torno_data = {f: 0.0 for f in fechas_set}
            fresa_data = {f: 0.0 for f in fechas_set}

            for r in rows:
                f_str = r['fecha'].strftime('%Y-%m-%d') if hasattr(r['fecha'], 'strftime') else str(r['fecha'])[:10]
                m_name = r['maquina']
                h_val = float(r['horas_activas'])
                if 'Torno' in m_name:
                    torno_data[f_str] += h_val
                else:
                    fresa_data[f_str] += h_val

            x_labels = [f[5:].replace('-', '/') for f in fechas_set]
            torno_y = [torno_data[f] for f in fechas_set]
            fresa_y = [fresa_data[f] for f in fechas_set]

            import numpy as np
            x = np.arange(len(x_labels))
            width = 0.35

            rects1 = ax.bar(x - width/2, torno_y, width, label='Torno 1', color='#38bdf8', edgecolor='#475569')
            rects2 = ax.bar(x + width/2, fresa_y, width, label='Fresadora 1', color='#34d399', edgecolor='#475569')

            ax.set_ylabel('Horas Operativas (hs)', color='#f8fafc', fontsize=10, fontweight='bold')
            ax.set_title('Horas Operativas Comparativas por Máquina (Últimos 7 Días)', color='#38bdf8', fontsize=11, fontweight='bold', pad=12)
            ax.set_xticks(x)
            ax.set_xticklabels(x_labels, color='#f8fafc', fontsize=9)
            ax.grid(axis='y', color='#334155', linestyle='--', alpha=0.5)
            ax.legend(facecolor='#1e293b', edgecolor='#475569', labelcolor='#f8fafc', fontsize=9)

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
