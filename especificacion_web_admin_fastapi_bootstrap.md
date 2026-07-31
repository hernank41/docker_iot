# Especificación Técnica de Requerimientos: Módulo Panel Web Administrador (FastAPI + Bootstrap)
**Proyecto:** Industrial IoT Stack (Extensión v2.0 - Dashboard Web)  
**Objetivo:** Guía de implementación detallada para un subagente de desarrollo / AI Coding Assistant.

---

## 1. Resumen Ejecutivo y Alcance
Este módulo extiende el servicio **FastAPI (`apiiot`)** para servir un **Panel de Control Administrador basado en Web** utilizando **Bootstrap 5** y JavaScript vanilla (`fetch`). 

### Características Clave:
- **Sin compiladores ni frameworks JS pesados:** Archivos HTML estáticos o plantillas Jinja2 servidos directamente por FastAPI.
- **Acceso Exclusivo Administrador:** Enfocado únicamente en visualización de métricas, reportes y tareas de edición/gestión administrativa.
- **Reutilización de API:** Consume las mismas tablas de MariaDB (`usuarios`, `herramientas`, `actividades`, `configuracion_sistema`) y lógica de negocio descritas en la v2.0.
- **Enrutamiento Nginx:** Accesible localmente a través de la infraestructura existente sin exponer puertos adicionales.

---

## 2. Arquitectura de Frontend y Directorios

El frontend se integrará dentro del microservicio `apiiot` existente para mantener un despliegue liviano en Docker:

```text
apiiot/
├── app.py
├── static/
│   ├── css/
│   │   └── admin.css
│   └── js/
│       ├── api_client.js
│       ├── dashboard.js
│       ├── herramientas.js
│       ├── actividades.js
│       └── configuracion.js
└── templates/
    └── admin.html            <-- SPA HTML con Bootstrap 5
```

---

## 3. Estructura de la Interfaz Web (Vistas y Secciones)

El panel será una **Single Page Application (SPA)** de una sola página HTML estructurada con una barra de navegación lateral o superior de Bootstrap.

### 3.1. Vista 1: Monitoreo en Tiempo Real (Dashboard)
- **Tarjetas de Máquinas (Cards):**
  - Muestra el estado actual (`ACTIVA`, `PARADA`, `PARADA_EMERGENCIA`).
  - Tiempo transcurrido en la actividad en curso (contador dinámico en minutos/horas).
  - Nombre del operario actualmente asignado (o badge "Sin Operario").
  - Herramienta montada actualmente en la máquina.
- **Resumen de Turno:** Métricas de disponibilidad actual (Uptime %) de Torno_1 y Fresadora_1.

### 3.2. Vista 2: Gestión de Operarios
- **Tabla de Operarios:** Nombre, Username, Estado (`Activo`/`Inactivo`), Fecha de Creación.
- **Acciones:**
  - Botón modal "Crear Operario".
  - Botón modal "Eliminar / Desactivar Operario".
  - Botón modal "Ver Historial de Actividades del Operario".

### 3.3. Vista 3: Gestión y Desgaste de Herramientas
- **Agrupación por Tipo de Máquina:** Tablas independientes para Torno_1 y Fresadora_1.
- **Columnas de Tabla:** Nombre de Herramienta, Horas Acumuladas, Horas de Expectativa, Porcentaje de Desgaste, Último Uso.
- **Indicador Visual:** Barra de progreso de Bootstrap (`<div class="progress">`) codificada por colores:
  - `bg-success`: $0\%$ a $70\%$ de desgaste.
  - `bg-warning`: $70\%$ a $90\%$ de desgaste.
  - `bg-danger`: $> 90\%$ de desgaste (Supera expectativa).
- **Acciones:**
  - Modal "Registrar Nueva Herramienta".
  - Modal "Cambiar/Asignar Herramienta Activa a Máquina".

### 3.4. Vista 4: Control de Actividades y Ajustes Retroactivos (*Fit*)
- **Tabla Histórica de Actividades:** ID, Máquina, Operario, Herramienta, Fecha Inicio, Fecha Fin, Tiempo Activo Efectivo, Estado, Comentario.
- **Acciones de Ajuste Retroactivo:**
  - **Asignar Operario Retroactivo:** Permite seleccionar una actividad registrada como "Sin Operario" y asignarle un operario.
  - **Fusionar Actividades (*Merge*):** Selección múltiple de 2 o más actividades consecutivas para combinarlas en un único ID de actividad, re-calculando el tiempo activo total.
  - **Dividir Actividad (*Split*):** Modal para seleccionar una actividad extensa y cortarla en dos fragmentos independientes indicando la fecha/hora de corte.
  - **Agregar/Editar Comentario:** Añadir notas u observaciones de planta a cualquier actividad pasada.

### 3.5. Vista 5: Informes y Reportes
- **Filtros de Reporte:**
  - Selector de rango de fechas.
  - Selector de turno (*Mañana*, *Tarde*, *Noche*).
- **Visualización:**
  - Informe del último turno de cada día (últimos 7 días).
  - Informe consolidado de la última semana completa.
  - Botón de exportación a CSV / JSON.

### 3.6. Vista 6: Configuración del Sistema
- **Formulario de Parámetros Globales:**
  - Campo numérico para el tiempo límite de inactividad ($T_{\text{inactividad}}$) en minutos.
  - Inputs de hora (`HH:MM`) para los inicios de turno:
    - Inicio Turno Mañana (ej: `06:00`).
    - Inicio Turno Tarde (ej: `14:00`).
    - Inicio Turno Noche (ej: `22:00`).
- Botón "Guardar Configuración" que actualiza la tabla `configuracion_sistema` en MariaDB.

---

## 4. Nuevos Endpoints Requeridos en FastAPI (`app.py`)

El subagente deberá implementar los siguientes endpoints REST dentro del backend:

```python
# --- Servir Interfaz Web ---
@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_panel(request: Request):
    ...

# --- Operarios ---
@app.get("/api/v1/admin/operarios")
@app.post("/api/v1/admin/operarios")
@app.delete("/api/v1/admin/operarios/{operario_id}")

# --- Herramientas ---
@app.get("/api/v1/admin/herramientas")
@app.post("/api/v1/admin/herramientas")
@app.put("/api/v1/admin/herramientas/{herramienta_id}/asignar")

# --- Ajuste de Actividades (Fit) ---
@app.post("/api/v1/admin/actividades/{actividad_id}/asignar-operario")
@app.post("/api/v1/admin/actividades/merge")
@app.post("/api/v1/admin/actividades/{actividad_id}/split")
@app.put("/api/v1/admin/actividades/{actividad_id}/comentario")

# --- Configuración del Sistema ---
@app.get("/api/v1/admin/configuracion")
@app.post("/api/v1/admin/configuracion")

# --- Informes ---
@app.get("/api/v1/admin/informes/turnos-7dias")
@app.get("/api/v1/admin/informes/semana-consolidada")
```

---

## 5. Integración con Nginx y Docker Compose

### 5.1. Actualización de `compose.yaml`
Montar la carpeta de estáticos y plantillas dentro del contenedor `apiiot`:

```yaml
  apiiot:
    build: ./apiiot
    container_name: apiiot
    restart: always
    volumes:
      - ./apiiot/templates:/app/templates
      - ./apiiot/static:/app/static
    environment:
      - DATABASE_HOST=mariadb
      - DATABASE_NAME=metalurgica_db
    networks:
      - backend_net
```

### 5.2. Regla de Enrutamiento en Nginx (`nginx.conf` / SWAG)
Garantizar que tanto las rutas estáticas como las dinámicas del admin se redirijan correctamente a `apiiot`:

```nginx
location /admin {
    proxy_pass http://apiiot:8000/admin;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

location /static/ {
    proxy_pass http://apiiot:8000/static/;
}
```

---

## 6. Checklist de Implementación para el Subagente

- [ ] **Fase 1: Backend & Rutas API (`app.py`)**
  - Implementar endpoints CRUD para Operarios, Herramientas y Configuración.
  - Implementar lógica de negocio para **Merge** (fusión) y **Split** (división) de actividades.
  - Configurar `Jinja2Templates` y `StaticFiles` en FastAPI.

- [ ] **Fase 2: Plantilla HTML & Layout Bootstrap (`templates/admin.html`)**
  - Configurar el HTML base importando Bootstrap 5 CDN y Bootstrap Icons.
  - Crear la estructura de la barra de navegación lateral y paneles contenedores.
  - Diseñar modales de Bootstrap para creación de usuarios, herramientas, merge/split de actividades y comentarios.

- [ ] **Fase 3: Lógica Cliente JS (`static/js/`)**
  - Crear `api_client.js` para centralizar llamadas `fetch()` con manejo de errores.
  - Crear manejadores de eventos DOM para actualización dinámica de tablas y barras de desgaste.
  - Implementar temporizador JS (`setInterval`) para refrescar las tarjetas de estado del dashboard en segundo plano.

- [ ] **Fase 4: Verificación Nginx & Pruebas Integradas**
  - Probar acceso a `http://localhost/admin`.
  - Verificar que las modificaciones hechas en la web (ej: cambiar $T_{\text{inactividad}}$ o asignar operario) impacten correctamente en MariaDB y se reflejen en la API compartida.
