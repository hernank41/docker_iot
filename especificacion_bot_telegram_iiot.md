# Especificación Técnica de Requerimientos: Módulo Telegram Bot y Motor de Actividades
**Proyecto:** Industrial IoT Stack (Extensión v2.0)  
**Objetivo:** Guía de implementación detallada para agente desarrollador / AI Coding Assistant.

---

## 1. Resumen Ejecutivo y Alcance
El proyecto actual de **Industrial IoT Stack** (basado en 7 microservicios: Mosquitto, Worker Python, MariaDB, FastAPI, Grafana, phpMyAdmin y SWAG) se extenderá para incorporar:
1. **Bot de Telegram** como interfaz principal de interacción y control en tiempo real.
2. **Gestión de Roles y Usuarios** (Administradores y Operarios).
3. **Motor de Actividades Industriales** con lógica de agregación temporal de micro-eventos (arranques/paradas) basada en ventana de inactividad configurable.
4. **Control de Ciclo de Vida de Herramientas** por máquina (horas de uso real vs. expectativa).
5. **Notificaciones Proactivas y Reportes Programados** para turnos, días y semanas.

---

## 2. Definición de Perfiles y Autenticación

### 2.1. Perfil Administrador
- **Autenticación:** Usuario y contraseña mediante comando/formulario seguro en el bot.
- **Alcance:** Control total sobre la configuración del sistema, gestión de usuarios, asignación retroactiva, definición de turnos y métricas.
- **Funcionalidades en Bot:**
  - **Gestión de Operarios:** Crear operarios, eliminar operarios existentes, consultar resumen de actividades por operario.
  - **Monitoreo en Tiempo Real:** Estado actual de cada máquina, tiempo transcurrido en la actividad activa, operario asignado y herramienta en uso.
  - **Visualización de Informes:**
    - Informe del último turno finalizado de cada día (últimos 7 días).
    - Informe consolidado de la última semana completa.
  - **Gestión de Herramientas:**
    - Registrar nueva herramienta: Nombre, Máquina asignada, Horas acumuladas de uso, Horas de expectativa de vida útil.
    - Ver herramientas: Listado jerárquico por Tipo de Máquina -> Herramientas asignadas (mostrando horas uso / expectativa y fecha/hora de último uso).
  - **Configuración del Sistema:**
    - Definición de horarios de turnos (Mañana, Tarde, Noche).
    - Definición del tiempo máximo de inactividad ($T_{\text{inactividad}}$) para el cierre automático de actividades.
  - **Notificaciones Recibidas:**
    - Alertas de Parada de Emergencia (`PARADA_EMERGENCIA`) en tiempo real.
    - Notificación de inicio / fin de actividad por parte de un operario.
    - Reportes automáticos al finalizar cada turno, día y semana.

### 2.2. Perfil Operario
- **Autenticación:** Vinculación directa por ID de usuario de Telegram o registro creado por el Administrador.
- **Alcance:** Operaciones de planta cotidianas desde el dispositivo móvil.
- **Funcionalidades en Bot:**
  - **Asignación a Máquina:** Auto-asignación a una máquina específica antes de iniciar la jornada/tarea.
  - **Gestión de Herramientas:** Seleccionar, asignar o cambiar la herramienta activa instalada en la máquina.
  - **Finalización de Actividad y Comentarios:** Al concluir una actividad (manualmente o tras una parada de emergencia), el bot solicitará un comentario u observación sobre la tarea realizada.

---

## 3. Lógica del Servidor: Motor de Actividades y Herramientas

### 3.1. Algoritmo de Agregación de Actividades (*Activity Session Engine*)
En planta, una máquina arranca y para múltiples veces dentro de un mismo trabajo. Para evitar fragmentar el registro en cientos de eventos menores, se implementa una **Sesión de Actividad**:
1. **Inicio de Actividad:** Se desencadena con la primera señal de arranque (`ACTIVA`) enviada por el microcontrolador (ESP32/ESP8266).
2. **Ventana de Inactividad Configurable ($T_{\text{inactividad}}$):**
   - Mientras los ciclos de parada y arranque ocurran dentro del umbral $T_{\text{inactividad}}$ (ej. 15 minutos), el servidor agrupa todos los eventos dentro de la **misma actividad**.
   - El tiempo de operación acumulado se calcula sumando únicamente las fracciones de tiempo en que la máquina estuvo efectivamente en estado `ACTIVA`.
3. **Cierre de Actividad:**
   - **Cierre Automático:** Si la máquina permanece en estado `PARADA` por un tiempo superior a $T_{\text{inactividad}}$, la actividad actual se marca automáticamente como `FINALIZADA`. El próximo arranque creará una actividad nueva.
   - **Cierre Manual:** El operario finaliza la actividad desde el Bot de Telegram.
   - **Cierre por Emergencia:** Un evento `PARADA_EMERGENCIA` congela la actividad y emite una alerta inmediata.

### 3.2. Operaciones Administrativas Retroactivas
El Administrador podrá ejecutar correcciones desde la API / Bot:
- **Asignación Posterior de Operario:** Si una máquina arranca sin operario asignado, el Administrador puede asociar el operario correspondiente a la actividad iniciada.
- **Fusión de Actividades (*Merge*):** Unir dos o más actividades consecutivas fragmentadas en una sola actividad consolidada.
- **División de Actividades (*Split*):** Separar una actividad prolongada en dos o más actividades independientes.

### 3.3. Contabilidad de Horas de Uso de Herramientas
- Cuando la máquina pasa a estado `ACTIVA`, el tiempo transcurrido se acumula en el contador `horas_uso` de la herramienta asignada a esa máquina.
- Al consultar las herramientas, el sistema evalúa el desgaste: $\text{Porcentaje de Desgaste} = \left( \frac{\text{Horas Uso}}{\text{Horas Expectativa}} \right) \times 100\%$.
- Alerta al Administrador cuando una herramienta supere el $90\%$ de su vida útil esperada.

---

## 4. Extensión del Esquema de Base de Datos (`schema.sql`)

```sql
-- Tabla de Usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    telegram_id BIGINT UNIQUE NULL,
    nombre VARCHAR(100) NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NULL,
    rol ENUM('ADMIN', 'OPERARIO') NOT NULL DEFAULT 'OPERARIO',
    activo BOOLEAN DEFAULT TRUE,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Herramientas
CREATE TABLE IF NOT EXISTS herramientas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maquina_id INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    horas_uso DECIMAL(10,2) DEFAULT 0.00,
    horas_expectativa DECIMAL(10,2) NOT NULL,
    ultimo_uso TIMESTAMP NULL,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id) ON DELETE CASCADE
);

-- Tabla de Asignación Actual de Máquinas
CREATE TABLE IF NOT EXISTS asignaciones_actuales (
    maquina_id INT PRIMARY KEY,
    operario_id INT NULL,
    herramienta_id INT NULL,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id),
    FOREIGN KEY (operario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (herramienta_id) REFERENCES herramientas(id) ON DELETE SET NULL
);

-- Tabla de Actividades Consolidadas
CREATE TABLE IF NOT EXISTS actividades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maquina_id INT NOT NULL,
    operario_id INT NULL,
    herramienta_id INT NULL,
    fecha_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin TIMESTAMP NULL,
    tiempo_activo_segundos INT DEFAULT 0,
    estado ENUM('EN_CURSO', 'FINALIZADA', 'PARADA_EMERGENCIA') DEFAULT 'EN_CURSO',
    comentario TEXT NULL,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id),
    FOREIGN KEY (operario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (herramienta_id) REFERENCES herramientas(id) ON DELETE SET NULL
);

-- Configuración Global del Sistema
CREATE TABLE IF NOT EXISTS configuracion_sistema (
    clave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL,
    descripcion VARCHAR(255) NULL
);

-- Inserción de parámetros por defecto
INSERT INTO configuracion_sistema (clave, valor, descripcion) VALUES
('timeout_inactividad_minutos', '15', 'Tiempo de inactividad para cerrar actividad automaticamente'),
('turno_manana_inicio', '06:00', 'Hora inicio turno mañana'),
('turno_tarde_inicio', '14:00', 'Hora inicio turno tarde'),
('turno_noche_inicio', '22:00', 'Hora inicio turno noche');
```

---

## 5. Especificación del Microservicio Bot de Telegram (`telegrambot`)

### 5.1. Estructura de Archivos Recomendada
```
telegrambot/
├──Dockerfile
├──requirements.txt
├──bot.py
├──handlers/
│   ├──admin.py
│   ├──operario.py
│   └──common.py
├──services/
│   ├──api_client.py
│   └──auth.py
└──keyboards/
    ├──inline.py
    └──reply.py
```

### 5.2. Flujo de Comandos e Interacción

#### Comandos Generales:
- `/start` - Mensaje de bienvenida e identificación de usuario/rol.
- `/login` - Autenticación para Administradores (`/login <usuario> <password>`).
- `/logout` - Cierre de sesión de administrador.

#### Menú Administrador (Botones Inline):
1. `👥 Gestión Operarios` -> `[Crear Operario]`, `[Eliminar Operario]`, `[Ver Resumen Actividad]`
2. `🏭 Estado Máquinas` -> Muestra tarjeta por máquina: Estado, Operario, Herramienta, Tiempo Activo.
3. `📊 Informes` -> `[Último Turno (7 Días)]`, `[Semana Completa]`
4. `🔧 Herramientas` -> Selección por Máquina -> Lista con barras de desgaste (ej: `[██████░░░░] 60% (120/200 hs)`).
5. `⚙️ Configuración` -> Modificar $T_{\text{inactividad}}$ y horarios de turnos.

#### Menú Operario (Botones Inline):
1. `⚙️ Asignarme a Máquina` -> Selección de máquina disponible.
2. `🔧 Cambiar Herramienta` -> Selección de herramienta para la máquina asignada.
3. `📝 Finalizar Actividad` -> Solicita comentario/observación final mediante teclado del bot.

---

## 6. Plan de Implementación para el Agente (Checklist)

- [ ] **Fase 1: Base de Datos & Modelos**
  - Actualizar `schema.sql` con las nuevas tablas (`usuarios`, `herramientas`, `actividades`, `asignaciones_actuales`, `configuracion_sistema`).
  - Crear datos de prueba (seed data) para administradores, operarios y herramientas.

- [ ] **Fase 2: Backend API (FastAPI - `app.py`)**
  - Implementar CRUD de Usuarios y Herramientas.
  - Implementar endpoints para gestión de Actividades (Crear, Finalizar, Asignar Operario, Merge, Split).
  - Implementar endpoints para cálculo de KPIs e informes por turno/semana.
  - Crear endpoints de webhook/alertas para el bot de Telegram.

- [ ] **Fase 3: Motor de Ingesta y Actividades (`clienteMqtt.py`)**
  - Integrar la lógica de ventana de inactividad $T_{\text{inactividad}}$.
  - Actualizar el contador de horas de uso de la herramienta activa durante el estado `ACTIVA`.
  - Disparar notificaciones a la API cuando ocurra un evento de inicio/fin o `PARADA_EMERGENCIA`.

- [ ] **Fase 4: Microservicio Bot de Telegram (`telegrambot/`)**
  - Crear el servicio en Python usando `python-telegram-bot` o `aiogram`.
  - Configurar manejadores de comandos y teclados interactivos para Admin y Operario.
  - Implementar llamadas HTTP al backend FastAPI (`apiiot`).
  - Configurar envío programado de notificaciones (cron/task-scheduler interno) para fin de turno/día/semana.

- [ ] **Fase 5: Orquestación y Despliegue (`compose.yaml`)**
  - Agregar el servicio `telegrambot` a `compose.yaml`.
  - Pasar variables de entorno: `TELEGRAM_BOT_TOKEN`, `API_URL`, `ADMIN_PASSWORD`.
  - Verificar comunicación en la red Docker interna `backend_net`.
