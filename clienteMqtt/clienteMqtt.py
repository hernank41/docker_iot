import asyncio
import ssl
import logging
import os
import json
import traceback
import aiomqtt
import aiomysql

logging.basicConfig(
    format='%(asctime)s - [MQTT Ingestion] - %(levelname)s: %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Helper function to get database connection pool / connection
async def get_db_connection():
    return await aiomysql.connect(
        host=os.getenv("MARIADB_SERVER", "mariadb"),
        port=int(os.getenv("MARIADB_PORT", 3306)),
        user=os.getenv("MARIADB_USER", "mediciones"),
        password=os.getenv("MARIADB_USER_PASS", "secret"),
        db=os.getenv("MARIADB_DB", "metalurgica_db"),
        autocommit=True
    )

async def guardar_evento(topic: str, payload_raw: bytes):
    try:
        data = json.loads(payload_raw.decode('utf-8'))
        logging.info(f"Payload recibido en '{topic}': {data}")

        maquina_nombre = data.get("maquina")
        # Extract from topic if payload lacks machine name (e.g. industrial/metalurgica/torno/estado)
        if not maquina_nombre:
            parts = topic.split('/')
            if len(parts) >= 3:
                sub = parts[-2].lower()
                if "torno" in sub:
                    maquina_nombre = "Torno_Pinacho"
                elif "fresadora" in sub:
                    maquina_nombre = "Fresadora_Universal"

        if not maquina_nombre:
            maquina_nombre = "Torno_Pinacho"

        estado = data.get("estado", "PARADA")
        codigo_estado = int(data.get("codigo_estado", 0 if estado == "PARADA" else 1))
        causa = data.get("causa", "OPERACION_NORMAL")

        conn = await get_db_connection()
        async with conn.cursor() as cur:
            # Get machine ID
            await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (maquina_nombre,))
            res = await cur.fetchone()
            
            if not res:
                # Insert machine if missing
                tipo = "Torno" if "torno" in maquina_nombre.lower() else "Fresadora"
                await cur.execute("INSERT INTO maquinas (nombre, tipo) VALUES (%s, %s)", (maquina_nombre, tipo))
                await cur.execute("SELECT id FROM maquinas WHERE nombre = %s", (maquina_nombre,))
                res = await cur.fetchone()
            
            maquina_id = res[0]

            # Insert activity log
            sql = """
                INSERT INTO registro_actividad (maquina_id, estado, codigo_estado, causa)
                VALUES (%s, %s, %s, %s)
            """
            await cur.execute(sql, (maquina_id, estado, codigo_estado, causa))
            logging.info(f"✅ Evento registrado: Maquina '{maquina_nombre}' (ID {maquina_id}) -> {estado} [{causa}]")

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

    # SSL Context if TLS port 8883
    tls_params = None
    if puerto == 8883:
        try:
            tls_context = ssl.create_default_context()
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE  # for local test setup / self-signed proxy cert
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