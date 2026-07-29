# Industrial IoT Server Stack: Complete Operations & Usage Guide

This guide provides step-by-step instructions on running the server, sending MQTT telemetry, accessing phpMyAdmin and Grafana, and understanding the SQL database design on branch **`Kisiel_2026`**.

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
- **FastAPI REST API & Interactive Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **phpMyAdmin (Database Web GUI):** [http://localhost:8080](http://localhost:8080)
- **Grafana (Analytics Dashboards):** [http://localhost:3000](http://localhost:3000)
- **MQTT Broker (Eclipse Mosquitto):** `localhost:1883` (MQTT) / `localhost:8883` (MQTTS TLS)

---

## 2. How to Send Telemetry via MQTT

The ingestion worker (`clientemqtt`) subscribes to the wildcard topic pattern:
`industrial/metalurgica/+/estado`

### Target Topics
- **Lathe (Torno Pinacho):** `industrial/metalurgica/torno/estado`
- **Milling Machine (Fresadora Universal):** `industrial/metalurgica/fresadora/estado`

### Telemetry JSON Payload Format

#### Machine Started (`ACTIVA`)
```json
{
  "device_id": "esp32_torno_01",
  "maquina": "Torno_Pinacho",
  "estado": "ACTIVA",
  "codigo_estado": 1,
  "causa": "PULSADOR_ARRANQUE",
  "timestamp_ms": 1722283200000
}
```

#### Machine Stopped (`PARADA`)
```json
{
  "device_id": "esp32_torno_01",
  "maquina": "Torno_Pinacho",
  "estado": "PARADA",
  "codigo_estado": 0,
  "causa": "PULSADOR_PARADA",
  "timestamp_ms": 1722283260000
}
```

#### Emergency Stop (`PARADA_EMERGENCIA`)
```json
{
  "device_id": "esp32_fresadora_01",
  "maquina": "Fresadora_Universal",
  "estado": "PARADA_EMERGENCIA",
  "codigo_estado": 0,
  "causa": "PARADA_EMERGENCIA_HABILITADA",
  "timestamp_ms": 1722283300000
}
```

---

### Methods to Publish MQTT Test Messages

#### Option A: Using `mosquitto_pub` CLI
```bash
# Publish Lathe Start event
mosquitto_pub -h localhost -p 1883 -t "industrial/metalurgica/torno/estado" -m "{\"device_id\":\"esp32_torno_01\",\"maquina\":\"Torno_Pinacho\",\"estado\":\"ACTIVA\",\"codigo_estado\":1,\"causa\":\"PULSADOR_ARRANQUE\"}"

# Publish Milling Machine Stop event
mosquitto_pub -h localhost -p 1883 -t "industrial/metalurgica/fresadora/estado" -m "{\"device_id\":\"esp32_fresadora_01\",\"maquina\":\"Fresadora_Universal\",\"estado\":\"PARADA\",\"codigo_estado\":0,\"causa\":\"SELECTOR_PARADA\"}"
```

#### Option B: Using Python (`paho-mqtt` or `aiomqtt`)
```python
import paho.mqtt.client as mqtt
import json

client = mqtt.Client()
client.connect("localhost", 1883, 60)

payload = {
    "device_id": "esp32_torno_01",
    "maquina": "Torno_Pinacho",
    "estado": "ACTIVA",
    "codigo_estado": 1,
    "causa": "PULSADOR_ARRANQUE"
}

client.publish("industrial/metalurgica/torno/estado", json.dumps(payload))
client.disconnect()
```

#### Option C: Via FastAPI REST Simulation Endpoint
You can also simulate an event directly using HTTP without an MQTT client:
```bash
curl -X POST "http://localhost:8000/api/v1/simular-evento" \
  -H "Content-Type: application/json" \
  -d '{"maquina": "Torno_Pinacho", "estado": "ACTIVA", "codigo_estado": 1, "causa": "PULSADOR_ARRANQUE"}'
```

---

## 3. How to Access phpMyAdmin

1. Open your browser and navigate to: **[http://localhost:8080](http://localhost:8080)**
2. Fill in the login credentials:
   - **Server:** `mariadb`
   - **Username:** `mediciones` (or `root`)
   - **Password:** `secret` (or `rootsecret` for root)
3. Select the database **`metalurgica_db`** in the left sidebar to view the `maquinas`, `registro_actividad`, and `kpi_turnos` tables.

---

## 4. How to Access and Configure Grafana

1. Open your browser and navigate to: **[http://localhost:3000](http://localhost:3000)**
2. Login credentials:
   - **Username:** `admin`
   - **Password:** `admin` *(You will be prompted to set a new password on first login)*

### Step-by-Step: Adding MariaDB Data Source
1. In Grafana, click the **Gear Icon (Connections / Data Sources)** on the left navigation menu.
2. Click **Add data source** and select **MySQL** (or MariaDB).
3. Configure the following fields:
   - **Host:** `mariadb:3306`
   - **Database:** `metalurgica_db`
   - **User:** `mediciones`
   - **Password:** `secret`
4. Click **Save & test**. You should see a green checkmark confirming success.

---

### Step-by-Step: Creating Dashboard Panels

#### Panel 1: Machine Real-time Status (Stat Panel)
- **Panel Type:** Stat
- **Title:** State of Machines
- **SQL Query:**
  ```sql
  SELECT m.nombre AS metric, COALESCE(r.codigo_estado, 0) AS value
  FROM maquinas m
  LEFT JOIN registro_actividad r ON r.id = (
      SELECT id FROM registro_actividad 
      WHERE maquina_id = m.id 
      ORDER BY timestamp DESC LIMIT 1
  );
  ```
- **Value Mappings:**
  - `1` $\rightarrow$ Green text / background: `ACTIVA`
  - `0` $\rightarrow$ Red text / background: `PARADA`

#### Panel 2: Activity Timeline (State Timeline Panel)
- **Panel Type:** State Timeline
- **Title:** Machinery Activity History
- **SQL Query:**
  ```sql
  SELECT timestamp AS time, m.nombre AS metric, r.estado AS value
  FROM registro_actividad r
  JOIN maquinas m ON r.maquina_id = m.id
  WHERE $__timeFilter(timestamp)
  ORDER BY timestamp ASC;
  ```

#### Panel 3: Availability KPI Gauge (Gauge Panel)
- **Panel Type:** Gauge
- **Title:** Availability Uptime %
- **SQL Query:**
  ```sql
  SELECT 
      m.nombre AS metric,
      ROUND(
          (SUM(CASE WHEN r.estado = 'ACTIVA' THEN 1 ELSE 0 END) * 100.0) / 
          NULLIF(COUNT(r.id), 0), 2
      ) AS value
  FROM maquinas m
  JOIN registro_actividad r ON r.maquina_id = m.id
  GROUP BY m.id, m.nombre;
  ```
- **Unit:** Percent (0-100%)

---

## 5. SQL Database Schema Design

The relational schema in [schema.sql](file:///c:/Users/Kisiel/Desktop/iot_2026/docker_iot/schema.sql) follows a clean star-schema / relational pattern optimized for high-frequency telemetry logging and fast analytics query performance.

```
+------------------------------------+
|              maquinas              |  (Dimension Table)
+------------------------------------+
| id (PK)                            |<---+
| nombre (UNIQUE)                    |    |
| tipo                               |    |
| ubicacion                          |    |
+------------------------------------+    |
                                          | 1:N Foreign Keys
       +----------------------------------+----------------------------------+
       |                                                                     |
       v                                                                     v
+------------------------------------+                             +------------------------------------+
|         registro_actividad         |  (Fact Log Table)           |             kpi_turnos             |  (Aggregated KPIs)
+------------------------------------+                             +------------------------------------+
| id (PK, BIGINT)                    |                             | id (PK)                            |
| maquina_id (FK -> maquinas.id)     |                             | maquina_id (FK -> maquinas.id)     |
| estado (ENUM: ACTIVA, PARADA...)   |                             | fecha (DATE)                       |
| codigo_estado (TINYINT: 1, 0)      |                             | turno (ENUM: MAÑANA, TARDE, NOCHE) |
| causa (VARCHAR)                    |                             | tiempo_activo_seg (INT)            |
| timestamp (TIMESTAMP, INDEXED)     |                             | tiempo_inactivo_seg (INT)          |
+------------------------------------+                             | porcentaje_disponibilidad (DECIMAL)|
                                                                   | cantidad_paradas (INT)             |
                                                                   +------------------------------------+
```

### Table Details

1. **`maquinas` (Dimension Table):**
   - **`id`** (`INT PRIMARY KEY AUTO_INCREMENT`): Unique numeric machine ID.
   - **`nombre`** (`VARCHAR(50) UNIQUE`): Human-readable machine name (e.g. `Torno_Pinacho`, `Fresadora_Universal`).
   - **`tipo`** (`VARCHAR(50)`): Type of machine (`Torno`, `Fresadora`).
   - **`ubicacion`** (`VARCHAR(100)`): Plant section location.

2. **`registro_actividad` (Fact Log Table):**
   - **`id`** (`BIGINT PRIMARY KEY AUTO_INCREMENT`): Unique event log entry ID.
   - **`maquina_id`** (`INT`): Foreign key referencing `maquinas(id)`.
   - **`estado`** (`ENUM('ACTIVA', 'PARADA', 'PARADA_EMERGENCIA')`): High-level operational state.
   - **`codigo_estado`** (`TINYINT`): Binary state code (`1` = Running, `0` = Stopped).
   - **`causa`** (`VARCHAR(50)`): Reason or trigger for state change (e.g., `PULSADOR_ARRANQUE`, `PARADA_EMERGENCIA`).
   - **`timestamp`** (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`): Server timestamp when the event occurred.
   - **Index:** `idx_maquina_time (maquina_id, timestamp)` enables fast indexed filtering for Grafana dashboards and API range queries.

3. **`kpi_turnos` (Aggregated Summary Table):**
   - Stores pre-calculated availability metrics grouped per machine, date, and work shift (`MAÑANA`, `TARDE`, `NOCHE`).
   - **Unique Constraint:** `uk_maquina_turno (maquina_id, fecha, turno)` prevents duplicate metric records per shift.
