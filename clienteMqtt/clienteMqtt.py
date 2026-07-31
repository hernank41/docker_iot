import asyncio
import ssl
import logging
import os
import json
import traceback
import aiomqtt
import aiomysql
import httpx
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - [MQTT Ingestion & Activity Engine] - %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
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

async def notificar_emergencia_http(maquina_nombre: str, causa: str):
    try:
        api_url = os.getenv("API_URL", "http://apiiot:8000")
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{api_url}/api/v1/notificar-emergencia",
                json={"maquina": maquina_nombre, "causa": causa},
                timeout=5.0
            )
    except Exception as e:
        logging.warning(f"No se pudo enviar notificación de emergencia por HTTP: {e}")

async def guardar_evento(topic: str, payload_raw: bytes):
    try:
        data = json.loads(payload_raw.decode('utf-8'))
        logging.info(f"Payload recibido en '{topic}': {data}")

        maquina_nombre = data.get("maquina")
        if maquina_nombre:
            low = maquina_nombre.lower()
            if "pinacho" in low or low in ["torno", "torno1", "torno_1"]:
                maquina_nombre = "Torno_1"
            elif "universal" in low or low in ["fresadora", "fresadora1", "fresadora_1"]:
                maquina_nombre = "Fresadora_1"

        if not maquina_nombre:
            parts = topic.split('/')
            if len(parts) >= 2:
                sub = parts[-2].lower() if len(parts) >= 3 else parts[-1].lower()
                if "torno" in sub:
                    maquina_nombre = "Torno_1"
                elif "fresadora" in sub:
                    maquina_nombre = "Fresadora_1"

        if not maquina_nombre:
            maquina_nombre = "Torno_1"

        estado = data.get("estado", "PARADA")
        codigo_raw = data.get("codigo_estado")
        if codigo_raw is None:
            codigo_estado = 1 if estado == "ACTIVA" else 0
        else:
            codigo_estado = int(codigo_raw)

        causa = data.get("causa", "OPERACION_NORMAL")

        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # 1. Obtener ID de la Máquina
            await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (maquina_nombre,))
            res = await cur.fetchone()
            
            if not res:
                tipo = "Torno" if "torno" in maquina_nombre.lower() else "Fresadora"
                await cur.execute("INSERT INTO maquinas (nombre, tipo) VALUES (%s, %s)", (maquina_nombre, tipo))
                await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (maquina_nombre,))
                res = await cur.fetchone()
            
            maquina_id = res['id']

            # 2. Insertar en registro de actividad
            sql = """
                INSERT INTO registro_actividad (maquina_id, estado, codigo_estado, causa)
                VALUES (%s, %s, %s, %s)
            """
            await cur.execute(sql, (maquina_id, estado, codigo_estado, causa))
            logging.info(f"✅ Evento telemetría: '{maquina_nombre}' (ID {maquina_id}) -> {estado} [{causa}]")

            # 3. Lógica del Motor de Actividades (Sesión de Actividad)
            await cur.execute("SELECT valor FROM configuracion_sistema WHERE clave = 'timeout_inactividad_minutos'")
            conf_res = await cur.fetchone()
            timeout_minutos = int(conf_res['valor']) if conf_res else 10

            # Obtener asignación actual de la máquina (operario y herramienta)
            await cur.execute("SELECT operario_id, herramienta_id FROM asignaciones_actuales WHERE maquina_id = %s", (maquina_id,))
            asig = await cur.fetchone()
            operario_id = asig['operario_id'] if asig else None
            herramienta_id = asig['herramienta_id'] if asig else None

            # Buscar actividad activa actual
            await cur.execute(
                "SELECT id, fecha_inicio, timestampdiff(MINUTE, fecha_inicio, CURRENT_TIMESTAMP) as transcurrido_min FROM actividades WHERE maquina_id = %s AND estado = 'EN_CURSO' ORDER BY id DESC LIMIT 1",
                (maquina_id,)
            )
            act_activa = await cur.fetchone()

            if estado == "ACTIVA":
                if not act_activa:
                    # Iniciar nueva actividad
                    await cur.execute("""
                        INSERT INTO actividades (maquina_id, operario_id, herramienta_id, estado)
                        VALUES (%s, %s, %s, 'EN_CURSO')
                    """, (maquina_id, operario_id, herramienta_id))
                    logging.info(f"🚀 Nueva sesión de actividad iniciada para {maquina_nombre}")
                else:
                    # Acumular horas de uso en herramienta si existe
                    if herramienta_id:
                        await cur.execute("""
                            UPDATE herramientas 
                            SET horas_uso = horas_uso + (1.0 / 60.0), ultimo_uso = CURRENT_TIMESTAMP 
                            WHERE id = %s
                        """, (herramienta_id,))

            elif estado == "PARADA":
                if act_activa and act_activa['transcurrido_min'] >= timeout_minutos:
                    await cur.execute("""
                        UPDATE actividades 
                        SET estado = 'FINALIZADA', fecha_fin = CURRENT_TIMESTAMP, comentario = 'Cierre automatico por inactividad'
                        WHERE id = %s
                    """, (act_activa['id'],))
                    logging.info(f"⏳ Actividad {act_activa['id']} para {maquina_nombre} cerrada por timeout de inactividad.")

            elif estado == "PARADA_EMERGENCIA":
                if act_activa:
                    await cur.execute("""
                        UPDATE actividades 
                        SET estado = 'PARADA_EMERGENCIA', fecha_fin = CURRENT_TIMESTAMP, comentario = 'Detenido por Parada de Emergencia'
                        WHERE id = %s
                    """, (act_activa['id'],))
                # Disparar alerta a Telegram
                await notificar_emergencia_http(maquina_nombre, causa)

        conn.close()

    except Exception as e:
        logging.error(f"❌ Error al procesar evento MQTT: {e}")
        logging.error(traceback.format_exc())

async def main():
    servidor = os.getenv("SERVIDOR", "mosquitto")
    puerto = int(os.getenv("PUERTO_MQTTS", os.getenv("PUERTO_MQTT", 1883)))
    usuario = os.getenv("MQTT_USR")
    password = os.getenv("MQTT_PASS")
    topico = os.getenv("TOPICO", "industrial/metalurgica/+/estado")

    tls_params = None
    if puerto == 8883:
        try:
            tls_context = ssl.create_default_context()
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE
            tls_params = aiomqtt.TLSParameters(tls_context=tls_context)
            logging.info("TLS configurado para MQTTS (puerto 8883)")
        except Exception as e:
            logging.warning(f"No se pudo inicializar TLS context: {e}")

    logging.info(f"Iniciando Cliente MQTT -> Broker: {servidor}:{puerto}, Tópico: '{topico}'")

    while True:
        try:
            client_kwargs = {
                "hostname": servidor,
                "port": puerto,
                "identifier": "worker-ingestor-metalurgica"
            }
            if usuario and password:
                client_kwargs["username"] = usuario
                client_kwargs["password"] = password
            if tls_params:
                client_kwargs["tls_params"] = tls_params

            async with aiomqtt.Client(**client_kwargs) as client:
                logging.info(f"Conectado exitosamente a Broker MQTT '{servidor}'")
                await client.subscribe(topico)
                logging.info(f"Suscrito a tópico '{topico}'")

                async for message in client.messages:
                    await guardar_evento(str(message.topic), message.payload)

        except aiomqtt.MqttError as e:
            logging.warning(f"Conexión MQTT perdida/fallida: {e}. Reintentando en 5 segundos...")
        except Exception as e:
            logging.error(f"Error inesperado en worker MQTT: {e}")
            logging.error(traceback.format_exc())
        
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())