from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiomysql
import os
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Industrial Machinery Uptime & KPI API",
    description="REST API for real-time monitoring of lathes, milling machines, and availability KPIs.",
    version="1.0.0"
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

class EventoSimulacion(BaseModel):
    maquina: str
    estado: str  # ACTIVA, PARADA, PARADA_EMERGENCIA
    codigo_estado: int  # 1 o 0
    causa: Optional[str] = "PULSADOR_ARRANQUE"

@app.get("/")
async def root():
    return {
        "sistema": "Monitoreo de Disponibilidad y KPIs de Maquinaria Industrial",
        "estado": "Operativo",
        "version": "1.0.0",
        "documentacion": "/docs"
    }

@app.get("/api/v1/maquinas")
async def listar_maquinas():
    """Retorna todas las máquinas industriales registradas."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, nombre, tipo, ubicacion FROM maquinas")
            res = await cur.fetchall()
        conn.close()
        return {"maquinas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando MariaDB: {str(e)}")

@app.get("/api/v1/maquinas/estado-actual")
async def estado_actual():
    """Retorna el último estado registrado de cada máquina (Torno, Fresadora)."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            query = """
                SELECT 
                    m.id AS maquina_id, 
                    m.nombre AS maquina, 
                    m.tipo, 
                    COALESCE(r.estado, 'DESCONOCIDO') AS estado, 
                    COALESCE(r.codigo_estado, 0) AS codigo_estado, 
                    COALESCE(r.causa, 'N/A') AS causa, 
                    r.timestamp AS ultimo_cambio
                FROM maquinas m
                LEFT JOIN registro_actividad r ON r.id = (
                    SELECT id FROM registro_actividad 
                    WHERE maquina_id = m.id 
                    ORDER BY timestamp DESC LIMIT 1
                )
            """
            await cur.execute(query)
            res = await cur.fetchall()
        conn.close()
        return {"estado_maquinas": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener estado actual: {str(e)}")

@app.get("/api/v1/maquinas/{maquina_id}/historial")
async def historial_actividad(maquina_id: int, limit: int = Query(50, ge=1, le=500)):
    """Retorna el historial de cambios de estado para una máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            query = """
                SELECT id, estado, codigo_estado, causa, timestamp
                FROM registro_actividad
                WHERE maquina_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            await cur.execute(query, (maquina_id, limit))
            res = await cur.fetchall()
        conn.close()
        return {"maquina_id": maquina_id, "historial": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando historial: {str(e)}")

@app.get("/api/v1/kpi/disponibilidad")
async def calcular_disponibilidad():
    """Calcula el porcentaje de disponibilidad y resumen de paradas por máquina."""
    try:
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            query = """
                SELECT 
                    m.id AS maquina_id,
                    m.nombre AS maquina,
                    COUNT(r.id) AS total_eventos,
                    SUM(CASE WHEN r.estado = 'ACTIVA' THEN 1 ELSE 0 END) AS conteo_activas,
                    SUM(CASE WHEN r.estado IN ('PARADA', 'PARADA_EMERGENCIA') THEN 1 ELSE 0 END) AS conteo_paradas,
                    ROUND(
                        (SUM(CASE WHEN r.estado = 'ACTIVA' THEN 1 ELSE 0 END) * 100.0) / 
                        NULLIF(COUNT(r.id), 0), 2
                    ) AS disponibilidad_porcentaje
                FROM maquinas m
                LEFT JOIN registro_actividad r ON r.maquina_id = m.id
                GROUP BY m.id, m.nombre
            """
            await cur.execute(query)
            res = await cur.fetchall()
        conn.close()
        return {"resumen_kpis": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al calcular KPIs: {str(e)}")

@app.post("/api/v1/simular-evento")
async def simular_evento(evento: EventoSimulacion):
    """Endpoint utilitario para simular eventos de contactores de 24V."""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (evento.maquina,))
            res = await cur.fetchone()
            if not res:
                await cur.execute("INSERT INTO maquinas (nombre, tipo) VALUES (%s, %s)", (evento.maquina, "Industrial"))
                await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (evento.maquina,))
                res = await cur.fetchone()
            
            maquina_id = res[0]
            sql = """INSERT INTO registro_actividad (maquina_id, estado, codigo_estado, causa)
                     VALUES (%s, %s, %s, %s)"""
            await cur.execute(sql, (maquina_id, evento.estado, evento.codigo_estado, evento.causa))
        conn.close()
        return {"status": "ok", "mensaje": f"Evento {evento.estado} registrado para {evento.maquina}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error simulando evento: {str(e)}")
