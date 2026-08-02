# Industrial IoT Server Stack: Complete Operations & Usage Guide

This guide provides step-by-step instructions on running the server, sending MQTT telemetry, accessing phpMyAdmin and Web Admin SPA, and understanding the SQL database design on branch **`Kisiel_2026`**.

---

## 1. Quick Start: Spinning Up the Server Stack

Make sure you are inside the `docker_iot` repository on the `Kisiel_2026` branch:

```powershell
cd c:\Users\Kisiel\Desktop\iot_2026\docker_iot
git checkout Kisiel_2026

# Build and start all 7 microservices in detached mode
docker compose up -d --build

# Verify all containers are running cleanly
docker compose ps
```

### Access Points Summary
- **Web Admin Control Panel SPA:** [http://localhost:8000/admin](http://localhost:8000/admin) (or via Nginx reverse proxy at [http://localhost/admin](http://localhost/admin))
- **FastAPI REST API & Interactive Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **phpMyAdmin (Database Web GUI):** [http://localhost:8080](http://localhost:8080)
- **MQTT Broker (Eclipse Mosquitto):** `localhost:1883` (MQTT) / `localhost:8883` (MQTTS TLS)

---

## 2. Key System Operations & Workflow

### 2.1 Web Admin Single Page Application (SPA)
- **Authentication:** Accessing `/admin` requires logging in with Admin credentials (`admin` / `admin123`).
- **Real-Time Monitoring:** Live cards for Torno 1 and Fresadora 1 with auto-refresh every 5 seconds.
- **Operarios Management:** Deduplicated database maintaining active operarios (`juanperez` and `carlosgomez`). View individual performance line charts per machine.
- **Herramientas & Vida Útil:** Track wear progress bars (`Green < 70%`, `Yellow 70-90%`, `Red > 90%`).
- **Control de Actividades (Fit):** Retroactive Merge (fusion of consecutive sessions), Split (divide at cut datetime), and Operario assignment.
- **Configuración Sistema:** Configure $T_{\text{inactividad}}$ timeout as well as both Start and End hours for Morning, Afternoon, and Night shifts.

### 2.2 Telegram Bot 2.0 (`@Kisiel_iot_bot`)
- **Step-by-step Admin Login:** Interactive 2-step prompt asking first for Username (`admin`), then Password (`admin123`).
- **Operario Machine Assignment Constraint:** Operarios are strictly constrained to 1 assigned machine at a time. Selecting a new machine automatically unassigns them from any previous machine.
- **Tool Selection Filter:** Operarios can only select tools registered to their currently assigned machine.
- **Active Activity Comment:** Operarios can attach/update custom notes or comments to their ongoing session.
- **Clean Caption Reports:** Photo reports (7-day shifts, weekly donut chart, operario line stats) automatically format captions cleanly to prevent length errors.

---

## 3. How to Send Telemetry via MQTT

The ingestion worker (`clientemqtt`) subscribes to the wildcard topic pattern:
`industrial/metalurgica/+/estado`

### Target Topics
- **Lathe (Torno 1):** `industrial/metalurgica/torno_1/estado`
- **Milling Machine (Fresadora 1):** `industrial/metalurgica/fresadora_1/estado`

> **Note on Timestamps & ESP Payloads:** Timestamps are generated **server-side** automatically upon message arrival (via MariaDB `CURRENT_TIMESTAMP`). The ESP microcontrollers only need to send the machine `estado`.

### Telemetry JSON Payload Format

#### Machine Started (`ACTIVA`)
```json
{
  "maquina": "Torno_1",
  "estado": "ACTIVA",
  "codigo_estado": 1,
  "causa": "PULSADOR_ARRANQUE"
}
```

#### Minimal ESP Payload (Name & State inferred from topic & status)
```json
{
  "estado": "ACTIVA"
}
```

#### Machine Stopped (`PARADA`)
```json
{
  "maquina": "Torno_1",
  "estado": "PARADA",
  "codigo_estado": 0,
  "causa": "PULSADOR_PARADA"
}
```

#### Emergency Stop (`PARADA_EMERGENCIA`)
```json
{
  "maquina": "Fresadora_1",
  "estado": "PARADA_EMERGENCIA",
  "codigo_estado": 0,
  "causa": "PARADA_EMERGENCIA_HABILITADA"
}
```

---

### Methods to Publish MQTT Test Messages

#### Option A: Using `mosquitto_pub` CLI
```bash
# Publish Lathe Start event
mosquitto_pub -h localhost -p 1883 -t "industrial/metalurgica/torno_1/estado" -m "{\"maquina\":\"Torno_1\",\"estado\":\"ACTIVA\",\"codigo_estado\":1,\"causa\":\"PULSADOR_ARRANQUE\"}"

# Publish Milling Machine Stop event
mosquitto_pub -h localhost -p 1883 -t "industrial/metalurgica/fresadora_1/estado" -m "{\"maquina\":\"Fresadora_1\",\"estado\":\"PARADA\",\"codigo_estado\":0,\"causa\":\"SELECTOR_PARADA\"}"
```

#### Option B: Using Python (`paho-mqtt` or `aiomqtt`)
```python
import paho.mqtt.client as mqtt
import json

client = mqtt.Client()
client.connect("localhost", 1883, 60)

payload = {
    "maquina": "Torno_1",
    "estado": "ACTIVA",
    "codigo_estado": 1,
    "causa": "PULSADOR_ARRANQUE"
}

client.publish("industrial/metalurgica/torno_1/estado", json.dumps(payload))
client.disconnect()
```

---

## 4. Database Schema Structure (`metalurgica_db`)

The MariaDB database consists of 8 core tables:

1. **`maquinas`**: Master registry of machines (`id`, `nombre`, `tipo`, `ubicacion`).
2. **`usuarios`**: User accounts & Telegram linkages (`id`, `nombre`, `username`, `rol`, `telegram_id`, `activo`).
3. **`herramientas`**: Tool catalog & wear tracking (`id`, `maquina_id`, `nombre`, `horas_expectativa`, `horas_uso`).
4. **`asignaciones_actuales`**: Real-time snapshot mapping (`maquina_id`, `operario_id`, `herramienta_id`).
5. **`registro_actividad`**: Immutable raw telemetry events log (`id`, `maquina_id`, `estado`, `codigo_estado`, `causa`, `timestamp`).
6. **`actividades`**: Consolidated work sessions (`id`, `maquina_id`, `operario_id`, `herramienta_id`, `fecha_inicio`, `fecha_fin`, `tiempo_activo_segundos`, `estado`, `comentario`).
7. **`kpi_turnos`**: Aggregated shift KPIs (`id`, `maquina_id`, `fecha`, `turno`, `tiempo_activo_seg`, `disponibilidad_pct`).
8. **`configuracion_sistema`**: Global dynamic parameters ($T_{\text{inactividad}}$, start/end hours for morning, afternoon, and night shifts).
