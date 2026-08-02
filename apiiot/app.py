import os
import json
import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request, Depends, Query, Cookie, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import aiomysql

logging.basicConfig(
    format='%(asctime)s - [FastAPI Backend] - %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = FastAPI(
    title="Industrial IoT Stack API",
    version="2.0.0",
    description="API REST para monitoreo industrial, control de herramientas y gestión de operarios."
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

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
    comentario: Optional[str] = None

class ComentarioUpdate(BaseModel):
    comentario: str
    operario_id: Optional[int] = None
    maquina_id: Optional[int] = None

class FinalizarActividad(BaseModel):
    actividad_id: int
    comentario: Optional[str] = "Finalizado por usuario"

class MergeActividades(BaseModel):
    actividad_ids: List[int]

class SplitActividad(BaseModel):
    fecha_corte: str

class AsignarOperarioActividad(BaseModel):
    operario_id: int

class ConfiguracionItem(BaseModel):
    clave: str
    valor: str

class ConfiguracionBulkUpdate(BaseModel):
    items: List[ConfiguracionItem]

# --- Vistas HTML ---
@app.get("/", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_panel(request: Request, admin_session: Optional[str] = Cookie(None)):
    """Renderiza el Panel Web de Administración SPA con autenticación por cookie."""
    is_auth = (admin_session == "authenticated")
    return templates.TemplateResponse("admin.html", {"request": request, "authenticated": is_auth})

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
    """Lista todos los usuarios (Administradores y Operarios)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, nombre, username, rol, telegram_id, activo, fecha_creacion FROM usuarios ORDER BY id ASC")
            res = await cur.fetchall()
        conn.close()
        return {"usuarios": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/usuarios")
async def crear_usuario(u: UsuarioCreate):
    """Registra un nuevo usuario en la base de datos."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO usuarios (nombre, username, rol, activo) VALUES (%s, %s, %s, TRUE)",
                (u.nombre, u.username, u.rol)
            )
            u_id = cur.lastrowid
        conn.close()
        return {"status": "ok", "id": u_id, "mensaje": f"Usuario {u.username} creado exitosamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/usuarios/{usuario_id}")
async def eliminar_usuario(usuario_id: int):
    """Desactiva o elimina un usuario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
        conn.close()
        return {"status": "ok", "mensaje": f"Usuario {usuario_id} eliminado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/usuarios/vincular-telegram")
async def vincular_telegram(telegram_id: int = Query(...), username: str = Query(...)):
    """Vincia el ID numérico de Telegram con un usuario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("UPDATE usuarios SET telegram_id = NULL WHERE telegram_id = %s", (telegram_id,))
            await cur.execute("UPDATE usuarios SET telegram_id = %s WHERE username = %s", (telegram_id, username))
        conn.close()
        return {"status": "ok", "mensaje": f"Telegram ID {telegram_id} vinculado a {username}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/usuarios/{usuario_id}/stats")
async def stats_usuario(usuario_id: int):
    """Retorna las métricas detalladas de desempeño de un operario."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, nombre, username, rol FROM usuarios WHERE id = %s", (usuario_id,))
            user = await cur.fetchone()
            if not user:
                conn.close()
                raise HTTPException(status_code=404, detail="Usuario no encontrado")

            sql_resumen = """
                SELECT 
                    COUNT(id) AS total_actividades,
                    ROUND(COALESCE(SUM(tiempo_activo_segundos), 0) / 3600.0, 2) AS total_horas
                FROM actividades
                WHERE operario_id = %s
            """
            await cur.execute(sql_resumen, (usuario_id,))
            resumen = await cur.fetchone()

            sql_maquinas = """
                SELECT 
                    m.nombre AS maquina,
                    COUNT(a.id) AS actividades_count,
                    ROUND(COALESCE(SUM(a.tiempo_activo_segundos), 0) / 3600.0, 2) AS horas_activas
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE a.operario_id = %s
                GROUP BY m.id, m.nombre
            """
            await cur.execute(sql_maquinas, (usuario_id,))
            maquinas_stats = await cur.fetchall()

            sql_ultimas = """
                SELECT a.id, m.nombre AS maquina, a.fecha_inicio, a.fecha_fin, 
                       ROUND(COALESCE(a.tiempo_activo_segundos, 0) / 3600.0, 2) AS horas, a.comentario
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE a.operario_id = %s
                ORDER BY a.fecha_inicio DESC LIMIT 5
            """
            await cur.execute(sql_ultimas, (usuario_id,))
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
            try:
                await cur.execute("ALTER TABLE asignaciones_actuales ADD COLUMN comentario VARCHAR(255) NULL")
            except Exception:
                pass

            await cur.execute("UPDATE asignaciones_actuales SET herramienta_id = NULL, comentario = NULL WHERE operario_id IS NULL")

            sql = """
                SELECT 
                    m.id AS maquina_id,
                    m.nombre AS maquina,
                    m.tipo,
                    COALESCE(
                        (SELECT estado FROM registro_actividad WHERE maquina_id = m.id ORDER BY timestamp DESC LIMIT 1),
                        'PARADA'
                    ) AS estado,
                    (SELECT timestamp FROM registro_actividad WHERE maquina_id = m.id ORDER BY timestamp DESC LIMIT 1) AS ultimo_estado_timestamp,
                    act.id AS actividad_id,
                    act.fecha_inicio AS actividad_fecha_inicio,
                    CASE WHEN act.id IS NOT NULL THEN TRUE ELSE FALSE END AS en_actividad,
                    COALESCE(
                        act.comentario,
                        (SELECT comentario FROM actividades WHERE maquina_id = m.id ORDER BY id DESC LIMIT 1),
                        a.comentario,
                        (SELECT causa FROM registro_actividad WHERE maquina_id = m.id ORDER BY timestamp DESC LIMIT 1),
                        'Sin Comentario'
                    ) AS causa,
                    u.id AS operario_id,
                    u.nombre AS operario_nombre,
                    u.username AS operario_username,
                    CASE WHEN a.operario_id IS NULL THEN NULL ELSE h.id END AS herramienta_id,
                    CASE WHEN a.operario_id IS NULL THEN NULL ELSE h.nombre END AS herramienta_nombre
                FROM maquinas m
                LEFT JOIN asignaciones_actuales a ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON a.operario_id = u.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                LEFT JOIN actividades act ON act.maquina_id = m.id AND act.estado = 'EN_CURSO'
                ORDER BY m.id ASC
            """
            await cur.execute(sql)
            res = await cur.fetchall()

            for r in res:
                if r.get("ultimo_estado_timestamp") and isinstance(r["ultimo_estado_timestamp"], datetime):
                    r["ultimo_estado_timestamp"] = r["ultimo_estado_timestamp"].isoformat()
                if r.get("actividad_fecha_inicio") and isinstance(r["actividad_fecha_inicio"], datetime):
                    r["actividad_fecha_inicio"] = r["actividad_fecha_inicio"].isoformat()

        conn.close()
        return {"maquinas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Asignaciones & Restricciones de Operarios
@app.get("/api/v1/asignaciones/operario/{operario_id}")
async def obtener_asignacion_operario(operario_id: int):
    """Retorna la máquina y herramienta actualmente asignadas a un operario, junto con el comentario activo o pre-asignado."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            try:
                await cur.execute("ALTER TABLE asignaciones_actuales ADD COLUMN comentario VARCHAR(255) NULL")
            except Exception:
                pass

            sql = """
                SELECT a.maquina_id, m.nombre AS maquina_nombre,
                       a.herramienta_id, h.nombre AS herramienta_nombre,
                       a.comentario AS comentario_pre
                FROM asignaciones_actuales a
                JOIN maquinas m ON a.maquina_id = m.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                WHERE a.operario_id = %s
            """
            await cur.execute(sql, (operario_id,))
            asig = await cur.fetchone()

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
    """Actualiza la asignación de operario, herramienta y/o comentario pre-asignado para una máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            try:
                await cur.execute("ALTER TABLE asignaciones_actuales ADD COLUMN comentario VARCHAR(255) NULL")
            except Exception:
                pass

            if a.operario_id is not None:
                await cur.execute("UPDATE asignaciones_actuales SET operario_id = NULL WHERE operario_id = %s", (a.operario_id,))

            await cur.execute("SELECT maquina_id FROM asignaciones_actuales WHERE maquina_id = %s", (a.maquina_id,))
            exists = await cur.fetchone()
            
            if exists:
                updates = []
                params = []
                if a.operario_id is not None:
                    updates.append("operario_id = %s")
                    params.append(a.operario_id)
                if a.herramienta_id is not None:
                    updates.append("herramienta_id = %s")
                    params.append(a.herramienta_id)
                if a.comentario is not None:
                    updates.append("comentario = %s")
                    params.append(a.comentario)

                if updates:
                    params.append(a.maquina_id)
                    sql = f"UPDATE asignaciones_actuales SET {', '.join(updates)} WHERE maquina_id = %s"
                    await cur.execute(sql, tuple(params))
            else:
                await cur.execute(
                    "INSERT INTO asignaciones_actuales (maquina_id, operario_id, herramienta_id, comentario) VALUES (%s, %s, %s, %s)",
                    (a.maquina_id, a.operario_id, a.herramienta_id, a.comentario)
                )

            if a.comentario is not None:
                if a.operario_id is not None:
                    await cur.execute("UPDATE actividades SET comentario = %s WHERE operario_id = %s AND estado = 'EN_CURSO'", (a.comentario, a.operario_id))
                elif a.maquina_id is not None:
                    await cur.execute("UPDATE actividades SET comentario = %s WHERE maquina_id = %s AND estado = 'EN_CURSO'", (a.comentario, a.maquina_id))

        conn.close()
        return {"status": "ok", "mensaje": "Asignación actualizada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/admin/actividades/{actividad_id}/comentario")
@app.post("/api/v1/actividades/{actividad_id}/comentario")
async def actualizar_comentario_endpoint(actividad_id: int, req: ComentarioUpdate):
    """Actualiza el comentario de una actividad activa o pre-asignada."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, maquina_id, operario_id FROM actividades WHERE id = %s", (actividad_id,))
            act = await cur.fetchone()
            if act:
                await cur.execute("UPDATE actividades SET comentario = %s WHERE id = %s", (req.comentario, actividad_id))
                if act.get("maquina_id"):
                    await cur.execute("UPDATE asignaciones_actuales SET comentario = %s WHERE maquina_id = %s", (req.comentario, act["maquina_id"]))
            elif req.maquina_id:
                await cur.execute("UPDATE asignaciones_actuales SET comentario = %s WHERE maquina_id = %s", (req.comentario, req.maquina_id))
            elif req.operario_id:
                await cur.execute("UPDATE asignaciones_actuales SET comentario = %s WHERE operario_id = %s", (req.comentario, req.operario_id))

        conn.close()
        return {"status": "ok", "mensaje": "Comentario actualizado correctamente."}
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
@app.get("/api/v1/admin/actividades")
async def listar_todas_actividades_admin():
    """Retorna la lista completa de actividades para el módulo de Control de Actividades (Fit)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT a.id, a.maquina_id, m.nombre AS maquina,
                       a.operario_id, u.nombre AS operario_nombre,
                       a.herramienta_id, h.nombre AS herramienta_nombre,
                       a.fecha_inicio, a.fecha_fin, a.estado, a.comentario,
                       ROUND(COALESCE(a.tiempo_activo_segundos, TIMESTAMPDIFF(SECOND, a.fecha_inicio, NOW())) / 3600.0, 2) AS tiempo_activo_horas
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                LEFT JOIN usuarios u ON a.operario_id = u.id
                LEFT JOIN herramientas h ON a.herramienta_id = h.id
                ORDER BY a.fecha_inicio DESC LIMIT 100
            """
            await cur.execute(sql)
            res = await cur.fetchall()
        conn.close()
        return {"actividades": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    """Finaliza manualmente una actividad, registra el comentario final y desvincula la asignación actual de la máquina y herramienta."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, maquina_id, operario_id, fecha_inicio FROM actividades WHERE id = %s AND estado = 'EN_CURSO'", (data.actividad_id,))
            act = await cur.fetchone()

            if not act:
                await cur.execute("SELECT id, maquina_id, operario_id, fecha_inicio FROM actividades WHERE (maquina_id = %s OR operario_id = %s) AND estado = 'EN_CURSO' ORDER BY id DESC LIMIT 1", (data.actividad_id, data.actividad_id))
                act = await cur.fetchone()

            if act:
                ahora = datetime.now()
                segundos = int((ahora - act["fecha_inicio"]).total_seconds())

                await cur.execute(
                    """UPDATE actividades 
                       SET fecha_fin = %s, tiempo_activo_segundos = %s, estado = 'FINALIZADA', comentario = %s
                       WHERE id = %s""",
                    (ahora, segundos, data.comentario, act["id"])
                )

                await cur.execute(
                    "UPDATE asignaciones_actuales SET operario_id = NULL, herramienta_id = NULL, comentario = NULL WHERE maquina_id = %s",
                    (act["maquina_id"],)
                )
                if act.get("operario_id"):
                    await cur.execute(
                        "UPDATE asignaciones_actuales SET operario_id = NULL, herramienta_id = NULL, comentario = NULL WHERE operario_id = %s",
                        (act["operario_id"],)
                    )
            else:
                await cur.execute(
                    "UPDATE asignaciones_actuales SET operario_id = NULL, herramienta_id = NULL, comentario = NULL WHERE maquina_id = %s OR operario_id = %s",
                    (data.actividad_id, data.actividad_id)
                )

        conn.close()
        return {"status": "ok", "mensaje": "Actividad / Asignación finalizada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/actividades/merge")
async def merge_actividades_endpoint(data: MergeActividades):
    """Fusiona múltiples actividades seleccionadas en un único registro."""
    try:
        if len(data.actividad_ids) < 2:
            raise HTTPException(status_code=400, detail="Seleccione al menos 2 actividades.")
        
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            ids_str = ",".join(str(i) for i in data.actividad_ids)
            await cur.execute(f"""
                SELECT id, maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, comentario 
                FROM actividades WHERE id IN ({ids_str}) ORDER BY fecha_inicio ASC
            """)
            acts = await cur.fetchall()

            if len(acts) < 2:
                conn.close()
                raise HTTPException(status_code=404, detail="Actividades no encontradas.")

            base = acts[0]
            fin = acts[-1]["fecha_fin"] or datetime.now()
            segundos_totales = sum(a["tiempo_activo_segundos"] or 0 for a in acts)
            comentarios = " | ".join(filter(None, [a["comentario"] for a in acts])) or "Actividades fusionadas"

            await cur.execute("""
                UPDATE actividades 
                SET fecha_fin = %s, tiempo_activo_segundos = %s, comentario = %s
                WHERE id = %s
            """, (fin, segundos_totales, comentarios, base["id"]))

            delete_ids = [a["id"] for a in acts[1:]]
            del_str = ",".join(str(i) for i in delete_ids)
            await cur.execute(f"DELETE FROM actividades WHERE id IN ({del_str})")

        conn.close()
        return {"status": "ok", "mensaje": "Actividades fusionadas correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/actividades/{actividad_id}/split")
async def split_actividad_endpoint(actividad_id: int, data: SplitActividad):
    """Dividir una actividad en dos partes en una fecha/hora de corte dada."""
    try:
        corte_dt = datetime.strptime(data.fecha_corte, "%Y-%m-%d %H:%M:%S")
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM actividades WHERE id = %s", (actividad_id,))
            act = await cur.fetchone()

            if not act:
                conn.close()
                raise HTTPException(status_code=404, detail="Actividad no encontrada.")

            inicio = act["fecha_inicio"]
            fin_original = act["fecha_fin"] or datetime.now()

            if not (inicio < corte_dt < fin_original):
                conn.close()
                raise HTTPException(status_code=400, detail="La fecha de corte debe estar entre el inicio y el fin de la actividad.")

            seg1 = int((corte_dt - inicio).total_seconds())
            seg2 = int((fin_original - corte_dt).total_seconds())

            await cur.execute("""
                UPDATE actividades SET fecha_fin = %s, tiempo_activo_segundos = %s WHERE id = %s
            """, (corte_dt, seg1, actividad_id))

            await cur.execute("""
                INSERT INTO actividades (maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, estado, comentario)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (act["maquina_id"], act["operario_id"], act["herramienta_id"], corte_dt, fin_original, seg2, act["estado"], act["comentario"]))

        conn.close()
        return {"status": "ok", "mensaje": "Actividad dividida (split) exitosamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/actividades/{actividad_id}/asignar-operario")
async def me_asignar_operario_actividad_endpoint(actividad_id: int, data: AsignarOperarioActividad):
    """Asigna o corrige retroactivamente el operario responsable de una actividad."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("UPDATE actividades SET operario_id = %s WHERE id = %s", (data.operario_id, actividad_id))
        conn.close()
        return {"status": "ok", "mensaje": "Operario asignado retroactivamente a la actividad."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. Informes & KPIs JSON
@app.get("/api/v1/informes/reporte-turnos-detalle")
async def reporte_turnos_detalle():
    """Retorna la distribución de horas y actividades agrupadas por turno de trabajo."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    CASE 
                        WHEN HOUR(a.fecha_inicio) BETWEEN 6 AND 13 THEN 'Turno Mañana (07:00-12:00)'
                        WHEN HOUR(a.fecha_inicio) BETWEEN 14 AND 21 THEN 'Turno Tarde (14:00-17:00)'
                        ELSE 'Turno Noche (22:00-06:00)'
                    END AS turno,
                    COUNT(a.id) AS actividades_count,
                    ROUND(COALESCE(SUM(a.tiempo_activo_segundos), 0) / 3600.0, 2) AS horas_activas
                FROM actividades a
                WHERE a.fecha_inicio >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY turno
                ORDER BY horas_activas DESC
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()
        return {"turnos_detalle": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/informes/reporte-turno")
async def reporte_turno(dias: int = Query(30)):
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

# 7. Configuración del Sistema
@app.get("/api/v1/configuracion")
@app.get("/api/v1/admin/configuracion")
async def obtener_configuracion():
    """Retorna los parámetros dinámicos del sistema."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT clave, valor, descripcion FROM configuracion_sistema")
            rows = await cur.fetchall()

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
                    """INSERT INTO configuracion_sistema (clave, valor) 
                       VALUES (%s, %s) 
                       ON DUPLICATE KEY UPDATE valor = VALUES(valor)""",
                    (item.clave, item.valor)
                )
        conn.close()
        return {"status": "ok", "mensaje": "Configuración actualizada correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 8. Gráficos Dinámicos: Mes (30 Días Separado por Máquina), Turnos, Día y Semana
@app.get("/api/v1/admin/informes/grafico-mes")
async def grafico_mes_endpoint():
    """Genera gráfico PNG con 1 subgráfico separado por máquina (uno debajo del otro) de producción diaria durante el último mes (30 días)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    DATE(fecha_inicio) AS fecha,
                    m.nombre AS maquina,
                    ROUND(COALESCE(SUM(tiempo_activo_segundos), 0) / 3600.0, 2) AS horas
                FROM actividades
                JOIN maquinas m ON actividades.maquina_id = m.id
                WHERE fecha_inicio >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY DATE(fecha_inicio), m.id, m.nombre
                ORDER BY fecha ASC
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io
        import numpy as np

        if not rows:
            fig, ax = plt.subplots(figsize=(8, 3))
            fig.patch.set_facecolor('#1e1e2e')
            ax.set_facecolor('#181825')
            ax.text(0.5, 0.5, 'Sin datos en los últimos 30 días', color='white', ha='center', va='center', fontsize=12)
        else:
            by_maquina = {}
            for r in rows:
                m = r['maquina']
                if m not in by_maquina:
                    by_maquina[m] = {'fechas': [], 'horas': []}
                f_str = str(r['fecha'])[:10]
                if len(f_str) == 10:
                    parts = f_str.split('-')
                    f_fmt = f"{parts[2]}/{parts[1]}"
                else:
                    f_fmt = f_str
                by_maquina[m]['fechas'].append(f_fmt)
                by_maquina[m]['horas'].append(float(r['horas'] or 0.0))

            num_maquinas = len(by_maquina)
            fig, axes = plt.subplots(num_maquinas, 1, figsize=(9.5, 3.8 * num_maquinas), dpi=140)
            fig.patch.set_facecolor('#1e1e2e')

            if num_maquinas == 1:
                axes_list = [axes]
            elif isinstance(axes, np.ndarray):
                axes_list = list(axes.flatten())
            else:
                axes_list = list(axes)

            colors = ['#89b4fa', '#a6e3a1', '#f9e2af', '#f38ba8']

            for idx, (m_name, data) in enumerate(by_maquina.items()):
                ax = axes_list[idx]
                ax.set_facecolor('#181825')
                c = colors[idx % len(colors)]

                fechas = data['fechas']
                horas = data['horas']
                max_h = max(horas) if horas else 1.0

                x_indices = np.arange(len(fechas))

                bars = ax.bar(x_indices, horas, color=c, alpha=0.35, edgecolor=c, linewidth=1.2, width=0.5)
                ax.plot(x_indices, horas, marker='o', markersize=4, linewidth=2, color=c)
                ax.fill_between(x_indices, horas, color=c, alpha=0.08)

                ax.set_title(f"Evolución Mensual (30 Días) — Máquina: {m_name}", color='#f5e0dc', fontsize=11, fontweight='bold', pad=10)
                ax.set_ylabel("Horas Activas (hs)", color='#cdd6f4', fontsize=9, fontweight='bold')
                ax.set_ylim(0, max_h * 1.30 + 0.3)
                
                ax.set_xticks(x_indices)
                ax.set_xticklabels(fechas, rotation=45, ha='right', color='#cdd6f4', fontsize=8)
                ax.tick_params(colors='#cdd6f4', labelsize=8)
                ax.grid(True, linestyle='--', alpha=0.2, color='#6c7086')

                step = 1 if len(fechas) <= 10 else 2
                for i in range(0, len(fechas), step):
                    h_val = horas[i]
                    if h_val > 0:
                        ax.text(x_indices[i], h_val + (max_h * 0.04 + 0.05), f"{h_val:.1f}h", 
                                ha='center', va='bottom', color='#cdd6f4', fontsize=8, fontweight='bold')

            fig.suptitle("Evolución de Producción Diario por Máquina (Último Mes / 30 Días)", color='#cdd6f4', fontsize=13, fontweight='bold', y=0.99)

        plt.tight_layout(pad=3.0)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=140, facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        logging.exception("Error en grafico_mes_endpoint:")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/informes/grafico-turnos-detalle")
async def grafico_turnos_detalle_endpoint():
    """Genera un gráfico PNG de barras mostrando la distribución de producción por turno (Mañana, Tarde, Noche)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    CASE 
                        WHEN HOUR(a.fecha_inicio) BETWEEN 6 AND 13 THEN 'Turno Mañana\n(07:00-12:00)'
                        WHEN HOUR(a.fecha_inicio) BETWEEN 14 AND 21 THEN 'Turno Tarde\n(14:00-17:00)'
                        ELSE 'Turno Noche\n(22:00-06:00)'
                    END AS turno,
                    COUNT(a.id) AS sesiones,
                    ROUND(COALESCE(SUM(a.tiempo_activo_segundos), 0) / 3600.0, 2) AS horas
                FROM actividades a
                WHERE a.fecha_inicio >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY turno
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io

        fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)
        fig.patch.set_facecolor('#1e1e2e')
        ax.set_facecolor('#181825')

        if not rows:
            ax.text(0.5, 0.5, 'Sin datos de turnos registradas', color='white', ha='center', va='center')
        else:
            turnos_order = ['Turno Mañana\n(07:00-12:00)', 'Turno Tarde\n(14:00-17:00)', 'Turno Noche\n(22:00-06:00)']
            horas_map = {r['turno']: float(r['horas']) for r in rows}
            sesiones_map = {r['turno']: int(r['sesiones']) for r in rows}

            horas_list = [horas_map.get(t, 0.0) for t in turnos_order]
            sesiones_list = [sesiones_map.get(t, 0) for t in turnos_order]

            colors = ['#89b4fa', '#f9e2af', '#cba6f7']
            bars = ax.bar(turnos_order, horas_list, color=colors, edgecolor='#cdd6f4', width=0.45)

            max_h = max(horas_list) if max(horas_list) > 0 else 1.0
            ax.set_ylim(0, max_h * 1.30 + 0.3)
            ax.set_ylabel('Horas Activas (hs)', color='#cdd6f4', fontsize=10, fontweight='bold')
            ax.set_title('Distribución de Horas Operativas por Turno de Trabajo', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
            ax.grid(axis='y', color='#45475a', linestyle='--', alpha=0.5)
            ax.tick_params(colors='#cdd6f4', labelsize=9)

            for bar, ses in zip(bars, sesiones_list):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 0.05, f"{height:.2f} hs\n({ses} ses.)",
                        ha='center', va='bottom', color='#cdd6f4', fontsize=9, fontweight='bold')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/informes/grafico-turno")
async def grafico_turno_endpoint():
    """Genera gráfico PNG de barras comparativas por turno y día (últimos 7 días)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    DATE(fecha_inicio) AS fecha,
                    m.nombre AS maquina,
                    ROUND(COALESCE(SUM(tiempo_activo_segundos), 0) / 3600.0, 2) AS horas
                FROM actividades
                JOIN maquinas m ON actividades.maquina_id = m.id
                WHERE fecha_inicio >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY DATE(fecha_inicio), m.id, m.nombre
                ORDER BY fecha ASC
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io

        fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)
        fig.patch.set_facecolor('#1e1e2e')
        ax.set_facecolor('#181825')

        if not rows:
            ax.text(0.5, 0.5, 'Sin datos en los últimos 7 días', color='white', ha='center', va='center')
        else:
            fechas = sorted(list(set(str(r['fecha']) for r in rows)))
            maquinas = sorted(list(set(r['maquina'] for r in rows)))
            
            import numpy as np
            x = np.arange(len(fechas))
            width = 0.35
            colors = ['#89b4fa', '#a6e3a1']

            for i, m_name in enumerate(maquinas):
                horas_list = []
                for f in fechas:
                    h = next((r['horas'] for r in rows if str(r['fecha']) == f and r['maquina'] == m_name), 0.0)
                    horas_list.append(h)
                offset = (i - len(maquinas)/2 + 0.5) * width
                ax.bar(x + offset, horas_list, width, label=m_name, color=colors[i % len(colors)])

            ax.set_xticks(x)
            ax.set_xticklabels(fechas, rotation=30, ha='right')
            ax.set_title("Horas Activas por Máquina (Últimos 7 Días)", color='#cdd6f4', fontsize=12, fontweight='bold')
            ax.set_ylabel("Horas", color='#cdd6f4')
            ax.tick_params(colors='#cdd6f4')
            ax.grid(True, linestyle='--', alpha=0.2, color='#6c7086')
            ax.legend(facecolor='#1e1e2e', edgecolor='#45475a', labelcolor='#cdd6f4')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/informes/grafico-semana")
async def grafico_semana_endpoint():
    """Genera un gráfico de barras horizontales (evitando gráfico de donut) con la distribución semanal por máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            sql = """
                SELECT 
                    m.nombre AS maquina,
                    COUNT(a.id) AS total_actividades,
                    ROUND(COALESCE(SUM(a.tiempo_activo_segundos), 0) / 3600.0, 2) AS total_horas
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE a.fecha_inicio >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY m.id, m.nombre
                ORDER BY total_horas DESC
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
        conn.close()

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io
        import numpy as np

        fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)
        fig.patch.set_facecolor('#1e1e2e')
        ax.set_facecolor('#181825')

        if not rows:
            ax.text(0.5, 0.5, 'Sin horas operativas registradas', color='white', ha='center', va='center')
        else:
            labels = [r['maquina'] for r in rows]
            values = [r['total_horas'] for r in rows]
            sesiones = [r['total_actividades'] for r in rows]
            colors = ['#89b4fa', '#a6e3a1', '#f9e2af', '#fab387']

            y_pos = np.arange(len(labels))
            bars = ax.barh(y_pos, values, align='center', color=colors[:len(labels)], edgecolor='#cdd6f4', height=0.45)
            
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, color='#cdd6f4', fontsize=11, fontweight='bold')
            ax.invert_yaxis()
            ax.set_xlabel('Total Horas Operativas (hs)', color='#cdd6f4', fontsize=10, fontweight='bold')
            ax.set_title('Consolidado Semanal de Horas de Uso por Máquina', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
            ax.grid(axis='x', color='#45475a', linestyle='--', alpha=0.5)
            ax.tick_params(colors='#cdd6f4', labelsize=10)

            for bar, ses in zip(bars, sesiones):
                width = bar.get_width()
                ax.text(width + 0.1, bar.get_y() + bar.get_height()/2., f"{width:.2f} hs ({ses} sesiones)",
                        ha='left', va='center', color='#cdd6f4', fontsize=9, fontweight='bold')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/admin/usuarios/{usuario_id}/grafico-stats")
async def grafico_stats_operario_endpoint(usuario_id: int):
    """Genera una imagen PNG con gráficos limpios, legibles y espaciosos por máquina (uno debajo del otro)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT nombre FROM usuarios WHERE id = %s", (usuario_id,))
            u = await cur.fetchone()
            nombre_op = u["nombre"] if u else "Operario"

            sql = """
                SELECT 
                    DATE(a.fecha_inicio) as fecha,
                    m.nombre as maquina,
                    ROUND(SUM(a.tiempo_activo_segundos) / 3600.0, 2) as horas
                FROM actividades a
                JOIN maquinas m ON a.maquina_id = m.id
                WHERE a.operario_id = %s AND a.fecha_inicio >= DATE_SUB(NOW(), INTERVAL 14 DAY)
                GROUP BY DATE(a.fecha_inicio), m.id, m.nombre
                ORDER BY fecha ASC
            """
            await cur.execute(sql, (usuario_id,))
            rows = await cur.fetchall()
        conn.close()

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io
        import numpy as np

        if not rows:
            fig, ax = plt.subplots(figsize=(8, 3))
            fig.patch.set_facecolor('#1e1e2e')
            ax.set_facecolor('#181825')
            ax.text(0.5, 0.5, 'Sin actividades registradas en los últimos 14 días', color='white', ha='center', va='center', fontsize=12)
        else:
            by_maquina = {}
            for r in rows:
                m = r['maquina']
                if m not in by_maquina:
                    by_maquina[m] = {'fechas': [], 'horas': []}
                f_str = str(r['fecha'])[:10]
                if len(f_str) == 10:
                    parts = f_str.split('-')
                    f_fmt = f"{parts[2]}/{parts[1]}"
                else:
                    f_fmt = f_str
                by_maquina[m]['fechas'].append(f_fmt)
                by_maquina[m]['horas'].append(float(r['horas'] or 0.0))

            num_maquinas = len(by_maquina)
            fig, axes = plt.subplots(num_maquinas, 1, figsize=(9.5, 4.2 * num_maquinas), dpi=140)
            fig.patch.set_facecolor('#1e1e2e')

            if num_maquinas == 1:
                axes_list = [axes]
            elif isinstance(axes, np.ndarray):
                axes_list = list(axes.flatten())
            else:
                axes_list = list(axes)

            colors = ['#89b4fa', '#a6e3a1', '#f9e2af', '#f38ba8']

            for idx, (m_name, data) in enumerate(by_maquina.items()):
                ax = axes_list[idx]
                ax.set_facecolor('#181825')
                c = colors[idx % len(colors)]

                fechas = data['fechas']
                horas = data['horas']
                max_h = max(horas) if horas else 1.0

                x_indices = np.arange(len(fechas))

                bars = ax.bar(x_indices, horas, color=c, alpha=0.35, edgecolor=c, linewidth=1.5, width=0.45)
                ax.plot(x_indices, horas, marker='o', markersize=5, linewidth=2, color=c)
                ax.fill_between(x_indices, horas, color=c, alpha=0.08)

                ax.set_title(f"Máquina: {m_name} — Operario: {nombre_op}", color='#f5e0dc', fontsize=11, fontweight='bold', pad=12)
                ax.set_ylabel("Horas Activas (hs)", color='#cdd6f4', fontsize=9, fontweight='bold')
                ax.set_ylim(0, max_h * 1.30 + 0.3)
                
                ax.set_xticks(x_indices)
                ax.set_xticklabels(fechas, rotation=45, ha='right', color='#cdd6f4', fontsize=8)
                ax.tick_params(colors='#cdd6f4', labelsize=8)
                ax.grid(True, linestyle='--', alpha=0.2, color='#6c7086')

                step = 1 if len(fechas) <= 10 else 2
                for i in range(0, len(fechas), step):
                    h_val = horas[i]
                    if h_val > 0:
                        ax.text(x_indices[i], h_val + (max_h * 0.04 + 0.05), f"{h_val:.2f}h", 
                                ha='center', va='bottom', color='#cdd6f4', fontsize=8, fontweight='bold')

            fig.suptitle(f"Rendimiento Operativo por Máquina: {nombre_op} (Últimos 14 Días)", color='#cdd6f4', fontsize=13, fontweight='bold', y=0.99)

        plt.tight_layout(pad=3.0)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=140, facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)

        return StreamingResponse(buf, media_type="image/png")
    except Exception as e:
        logging.exception("Error en grafico_stats_operario_endpoint:")
        raise HTTPException(status_code=500, detail=str(e))

# 9. Simulación Manual de Eventos de Telemetría
@app.post("/api/v1/simular-evento")
async def simular_evento_endpoint(evento: EventoSimulacion):
    """Simula un evento de telemetría sin depender del broker MQTT."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (evento.maquina,))
            m = await cur.fetchone()
            if not m:
                tipo = "Torno" if "torno" in evento.maquina.lower() else "Fresadora"
                await cur.execute("INSERT INTO maquinas (nombre, tipo) VALUES (%s, %s)", (evento.maquina, tipo))
                await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (evento.maquina,))
                m = await cur.fetchone()
            maquina_id = m["id"]

            codigo = evento.codigo_estado if evento.codigo_estado is not None else (1 if evento.estado == "ACTIVA" else 0)
            causa = evento.causa or "SIMULACION"

            await cur.execute(
                "INSERT INTO registro_actividad (maquina_id, estado, codigo_estado, causa) VALUES (%s, %s, %s, %s)",
                (maquina_id, evento.estado, codigo, causa)
            )

            await cur.execute("SELECT operario_id, herramienta_id, comentario FROM asignaciones_actuales WHERE maquina_id = %s", (maquina_id,))
            asig = await cur.fetchone()
            op_id = asig["operario_id"] if asig else None
            h_id = asig["herramienta_id"] if asig else None
            comentario_pre = asig.get("comentario") if asig else None

            await cur.execute("SELECT id FROM actividades WHERE maquina_id = %s AND estado = 'EN_CURSO'", (maquina_id,))
            act = await cur.fetchone()

            if evento.estado == "ACTIVA":
                if not act:
                    comment_to_use = comentario_pre or causa or "Operación normal"
                    await cur.execute(
                        "INSERT INTO actividades (maquina_id, operario_id, herramienta_id, estado, comentario) VALUES (%s, %s, %s, 'EN_CURSO', %s)",
                        (maquina_id, op_id, h_id, comment_to_use)
                    )
            elif evento.estado in ["PARADA", "PARADA_EMERGENCIA"]:
                if act:
                    st = "FINALIZADA" if evento.estado == "PARADA" else "PARADA_EMERGENCIA"
                    await cur.execute(
                        "UPDATE actividades SET estado = %s, fecha_fin = NOW() WHERE id = %s",
                        (st, act["id"])
                    )
                    await cur.execute(
                        "UPDATE asignaciones_actuales SET operario_id = NULL, herramienta_id = NULL, comentario = NULL WHERE maquina_id = %s",
                        (maquina_id,)
                    )

        conn.close()
        return {"status": "ok", "mensaje": f"Evento {evento.estado} simulado para {evento.maquina}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
