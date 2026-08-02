// Dashboard & SPA Controller JS
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadDashboardData();
    setInterval(loadDashboardData, 5000); // Live refresh every 5s
});

function initNavigation() {
    const navLinks = document.querySelectorAll('#adminTab .nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const target = e.target.getAttribute('data-bs-target');
            if (target === '#operarios') loadOperarios();
            if (target === '#herramientas') loadHerramientas();
            if (target === '#actividades') loadActividades();
            if (target === '#informes') loadInformes();
            if (target === '#configuracion') loadConfiguracion();
        });
    });
}

// 0. Autenticación Web Admin
async function iniciarSesionWeb(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const errorDiv = document.getElementById('login-error');

    try {
        const res = await fetch('/api/v1/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
            document.cookie = "admin_session=authenticated; path=/; max-age=86400";
            window.location.href = "/admin";
        } else {
            errorDiv.innerText = data.detail || "Usuario o contraseña de Administrador incorrectos.";
            errorDiv.classList.remove('d-none');
        }
    } catch (err) {
        errorDiv.innerText = "Error al conectar con el servidor.";
        errorDiv.classList.remove('d-none');
    }
}

async function cerrarSesionWeb() {
    try {
        await fetch('/api/v1/admin/logout', { method: 'POST' });
        document.cookie = "admin_session=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;";
        window.location.href = "/admin";
    } catch (e) {
        document.cookie = "admin_session=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;";
        window.location.href = "/admin";
    }
}

function formatDuracionSegundos(sec) {
    if (isNaN(sec) || sec < 0) sec = 0;
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h > 0) {
        return `${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`;
    }
    return `${m}m ${s.toString().padStart(2, '0')}s`;
}

// 1. Dashboard Monitoreo en Tiempo Real
async function loadDashboardData() {
    try {
        const data = await API.get('/api/v1/maquinas/estado-actual');
        const container = document.getElementById('cards-maquinas-container');
        if (!container) return;

        const now = new Date();
        let html = '';

        data.maquinas.forEach(m => {
            const estadoUpper = (m.estado || 'PARADA').toUpperCase();
            const enActividad = !!m.en_actividad;

            let badgeClass = '';
            let cardBorderClass = '';
            let badgeText = estadoUpper;
            let timerHtml = '';

            if (estadoUpper === 'PARADA_EMERGENCIA') {
                badgeClass = 'bg-danger text-white';
                cardBorderClass = 'border-danger';
                badgeText = 'PARADA DE EMERGENCIA';
                if (m.ultimo_estado_timestamp) {
                    const secEstado = Math.floor((now - new Date(m.ultimo_estado_timestamp)) / 1000);
                    timerHtml = `<p class="card-text mb-1 text-danger fw-bold"><strong>Tiempo en emergencia:</strong> ${formatDuracionSegundos(secEstado)}</p>`;
                }
            } else if (enActividad && estadoUpper === 'ACTIVA') {
                badgeClass = 'bg-success text-white';
                cardBorderClass = 'border-success';
                badgeText = 'ACTIVA';

                const secEstado = m.ultimo_estado_timestamp ? Math.floor((now - new Date(m.ultimo_estado_timestamp)) / 1000) : 0;
                const secSesion = m.actividad_fecha_inicio ? Math.floor((now - new Date(m.actividad_fecha_inicio)) / 1000) : 0;

                timerHtml = `
                    <div class="mt-2 pt-2 border-top border-secondary">
                        <p class="card-text mb-1 text-success"><strong>Tiempo en estado activo (última señal):</strong> ${formatDuracionSegundos(secEstado)}</p>
                        <p class="card-text mb-1 text-success"><strong>Tiempo total de sesión activa:</strong> ${formatDuracionSegundos(secSesion)}</p>
                    </div>
                `;
            } else if (enActividad && estadoUpper === 'PARADA') {
                badgeClass = 'bg-primary text-white';
                cardBorderClass = 'border-primary';
                badgeText = 'PAUSADA EN SESIÓN';

                const secEstado = m.ultimo_estado_timestamp ? Math.floor((now - new Date(m.ultimo_estado_timestamp)) / 1000) : 0;
                const secSesion = m.actividad_fecha_inicio ? Math.floor((now - new Date(m.actividad_fecha_inicio)) / 1000) : 0;

                timerHtml = `
                    <div class="mt-2 pt-2 border-top border-secondary">
                        <p class="card-text mb-1 text-primary"><strong>Tiempo detenido (pausa desde última señal):</strong> ${formatDuracionSegundos(secEstado)}</p>
                        <p class="card-text mb-1 text-primary"><strong>Tiempo acumulado de sesión:</strong> ${formatDuracionSegundos(secSesion)}</p>
                    </div>
                `;
            } else {
                badgeClass = 'bg-warning text-dark';
                cardBorderClass = 'border-warning';
                badgeText = 'PARADA';
            }

            html += `
                <div class="col-md-6 mb-4">
                    <div class="card h-100 border-start border-4 ${cardBorderClass}">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h5 class="card-title mb-0">${m.maquina} (${m.tipo})</h5>
                            <span class="badge ${badgeClass} fs-6">${badgeText}</span>
                        </div>
                        <div class="card-body">
                            <p class="card-text mb-2"><strong>Operario:</strong> ${m.operario_nombre || 'Sin Operario'}</p>
                            <p class="card-text mb-2"><strong>Herramienta:</strong> ${m.herramienta_nombre || 'Sin Herramienta'}</p>
                            <p class="card-text mb-2"><strong>Causa / Estado:</strong> <code class="text-info">${m.causa || 'OPERACION_NORMAL'}</code></p>
                            ${timerHtml}
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    } catch (e) {
        console.error("Error cargando dashboard:", e);
    }
}

// 2. Gestión de Operarios
async function loadOperarios() {
    try {
        const data = await API.get('/api/v1/usuarios');
        const tbody = document.getElementById('tabla-operarios-body');
        if (!tbody) return;

        let html = '';
        data.usuarios.forEach(u => {
            if (u.rol !== 'OPERARIO') return;
            const estadoBadge = u.activo ? '<span class="badge bg-success">Activo</span>' : '<span class="badge bg-secondary">Inactivo</span>';
            const telegramBadge = u.telegram_id ? '<span class="badge bg-info text-dark">Vinculado</span>' : '<span class="badge bg-warning text-dark">Pendiente</span>';
            
            html += `
                <tr>
                    <td>${u.id}</td>
                    <td><strong>${u.nombre}</strong></td>
                    <td><code>@${u.username}</code></td>
                    <td>${estadoBadge}</td>
                    <td>${telegramBadge}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-info me-1" onclick="verStatsOperario(${u.id}, '${u.nombre}')">Ver Gráfico Stats</button>
                        <button class="btn btn-sm btn-outline-danger" onclick="eliminarOperario(${u.id})">Eliminar</button>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error("Error cargando operarios:", e);
    }
}

async function guardarNuevoOperario() {
    const nombre = document.getElementById('op-nombre').value.trim();
    const username = document.getElementById('op-username').value.trim();
    if (!nombre || !username) return alert("Complete todos los campos.");

    try {
        await API.post('/api/v1/usuarios', { nombre, username, rol: 'OPERARIO' });
        bootstrap.Modal.getInstance(document.getElementById('modalCrearOperario')).hide();
        document.getElementById('formCrearOperario').reset();
        loadOperarios();
    } catch (e) {
        alert("Error creando operario.");
    }
}

async function eliminarOperario(id) {
    if (!confirm("¿Desea eliminar permanentemente este operario?")) return;
    try {
        await API.delete(`/api/v1/usuarios/${id}`);
        loadOperarios();
    } catch (e) {
        alert("Error al eliminar operario.");
    }
}

async function verStatsOperario(id, nombre) {
    const img = document.getElementById('img-operario-stats');
    img.src = `/api/v1/admin/usuarios/${id}/grafico-stats?t=${Date.now()}`;
    document.getElementById('modalStatsLabel').innerText = `Estadísticas de Desempeño: ${nombre}`;
    const modal = new bootstrap.Modal(document.getElementById('modalOperarioStats'));
    modal.show();
}

// 3. Control y Gestión de Herramientas
async function loadHerramientas() {
    try {
        const data = await API.get('/api/v1/herramientas');
        const tbody = document.getElementById('tabla-herramientas-body');
        if (!tbody) return;

        let html = '';
        data.herramientas.forEach(h => {
            const porcentaje = h.porcentaje_desgaste || 0;
            const isHigh = porcentaje >= 90;
            const progressClass = isHigh ? 'bg-danger' : (porcentaje >= 60 ? 'bg-warning' : 'bg-success');
            
            html += `
                <tr>
                    <td>${h.id}</td>
                    <td><strong>${h.nombre}</strong></td>
                    <td>${h.maquina_nombre}</td>
                    <td>${h.horas_uso} hs / ${h.horas_expectativa} hs</td>
                    <td style="width: 250px;">
                        <div class="progress position-relative" style="height: 22px;">
                            <div class="progress-bar ${progressClass}" role="progressbar" style="width: ${porcentaje}%;">
                                ${porcentaje}%
                            </div>
                        </div>
                    </td>
                    <td>
                        ${isHigh ? '<span class="badge bg-danger">DESGASTE ALTO</span>' : '<span class="badge bg-success">OK</span>'}
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error("Error cargando herramientas:", e);
    }
}

async function guardarNuevaHerramienta() {
    const maquina_id = document.getElementById('h-maquina-id').value;
    const nombre = document.getElementById('h-nombre').value.trim();
    const horas_expectativa = document.getElementById('h-horas').value;

    if (!nombre || !horas_expectativa) return alert("Complete todos los campos.");

    try {
        await API.post('/api/v1/herramientas', {
            maquina_id: parseInt(maquina_id),
            nombre,
            horas_expectativa: parseFloat(horas_expectativa)
        });
        bootstrap.Modal.getInstance(document.getElementById('modalCrearHerramienta')).hide();
        document.getElementById('formCrearHerramienta').reset();
        loadHerramientas();
    } catch (e) {
        alert("Error creando herramienta.");
    }
}

// 4. Control de Actividades (Fit)
let actividadesData = [];

async function loadActividades() {
    try {
        const res = await API.get('/api/v1/admin/actividades');
        actividadesData = res.actividades;
        renderActividadesTabla();
    } catch (e) {
        console.error("Error cargando actividades:", e);
    }
}

function renderActividadesTabla() {
    const tbody = document.getElementById('tabla-actividades-body');
    if (!tbody) return;

    let html = '';
    actividadesData.forEach(a => {
        const isEnCurso = a.estado === 'EN_CURSO';
        const estadoBadge = isEnCurso ? '<span class="badge bg-success">EN_CURSO</span>' : `<span class="badge bg-secondary">${a.estado}</span>`;
        const fechaFinStr = a.fecha_fin ? a.fecha_fin.replace('T', ' ') : '<em>En ejecución</em>';
        
        html += `
            <tr>
                <td><input type="checkbox" class="chk-actividad form-check-input" value="${a.id}"></td>
                <td>#${a.id}</td>
                <td><strong>${a.maquina}</strong></td>
                <td>${a.operario_nombre || '<span class="text-muted">Sin Asignar</span>'}</td>
                <td>${a.herramienta_nombre || '<span class="text-muted">Sin Asignar</span>'}</td>
                <td><small>${a.fecha_inicio.replace('T', ' ')}</small></td>
                <td><small>${fechaFinStr}</small></td>
                <td>${a.tiempo_activo_horas} hs</td>
                <td>${estadoBadge}</td>
                <td><small>${a.comentario || '-'}</small></td>
                <td>
                    <button class="btn btn-sm btn-outline-warning me-1" onclick="abrirModalSplit(${a.id})">Split</button>
                    <button class="btn btn-sm btn-outline-info" onclick="abrirModalReasignar(${a.id})">Reasignar</button>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

async function ejecutarMerge() {
    const seleccionados = Array.from(document.querySelectorAll('.chk-actividad:checked')).map(cb => parseInt(cb.value));
    if (seleccionados.length < 2) return alert("Seleccione al menos 2 actividades para fusionar.");

    if (!confirm(`¿Desea fusionar las ${seleccionados.length} actividades seleccionadas?`)) return;

    try {
        await API.post('/api/v1/admin/actividades/merge', { actividad_ids: seleccionados });
        alert("Actividades fusionadas correctamente.");
        loadActividades();
    } catch (e) {
        alert("Error al fusionar actividades.");
    }
}

function abrirModalSplit(actividadId) {
    document.getElementById('split-actividad-id').value = actividadId;
    const modal = new bootstrap.Modal(document.getElementById('modalSplitActividad'));
    modal.show();
}

async function ejecutarSplit() {
    const actividadId = document.getElementById('split-actividad-id').value;
    const fechaCorte = document.getElementById('split-fecha-corte').value.trim();

    if (!fechaCorte) return alert("Ingrese la fecha y hora de corte (YYYY-MM-DD HH:MM:SS).");

    try {
        await API.post(`/api/v1/admin/actividades/${actividadId}/split`, { fecha_corte: fechaCorte });
        bootstrap.Modal.getInstance(document.getElementById('modalSplitActividad')).hide();
        alert("Actividad dividida correctamente.");
        loadActividades();
    } catch (e) {
        alert("Error al realizar split de la actividad.");
    }
}

async function abrirModalReasignar(actividadId) {
    document.getElementById('reasignar-actividad-id').value = actividadId;
    
    const data = await API.get('/api/v1/usuarios');
    const select = document.getElementById('select-operario-reasignar');
    select.innerHTML = '<option value="">Seleccione Operario...</option>';
    data.usuarios.forEach(u => {
        if (u.rol === 'OPERARIO') {
            select.innerHTML += `<option value="${u.id}">${u.nombre} (@${u.username})</option>`;
        }
    });

    const modal = new bootstrap.Modal(document.getElementById('modalReasignarOperario'));
    modal.show();
}

async function ejecutarReasignacion() {
    const actividadId = document.getElementById('reasignar-actividad-id').value;
    const operarioId = document.getElementById('select-operario-reasignar').value;

    if (!operarioId) return alert("Seleccione un operario.");

    try {
        await API.post(`/api/v1/admin/actividades/${actividadId}/asignar-operario`, { operario_id: parseInt(operarioId) });
        bootstrap.Modal.getInstance(document.getElementById('modalReasignarOperario')).hide();
        alert("Operario reasignado a la actividad correctamente.");
        loadActividades();
    } catch (e) {
        alert("Error reasignando operario.");
    }
}

// 5. Informes & Analítica de Planta (Carga los 4 Gráficos: Mes, Turnos, Día y Semana)
async function loadInformes() {
    try {
        const turnoData = await API.get('/api/v1/informes/reporte-turno');
        const turnosDetalleData = await API.get('/api/v1/informes/reporte-turnos-detalle');

        // Render Turno Tabla (7 Días)
        const tbodyTurno = document.getElementById('tabla-reporte-turno-body');
        if (tbodyTurno) {
            let html = '';
            turnoData.reporte_turno.forEach(r => {
                html += `
                    <tr>
                        <td>${r.fecha}</td>
                        <td><strong>${r.maquina}</strong></td>
                        <td>${r.total_actividades}</td>
                        <td>${r.horas_activas} hs</td>
                        <td><small>${r.operarios || 'Sin Operario'}</small></td>
                    </tr>
                `;
            });
            tbodyTurno.innerHTML = html;
        }

        // Render Shift Breakdown Tabla
        const tbodyTurnosDetalle = document.getElementById('tabla-reporte-turnos-detalle-body');
        if (tbodyTurnosDetalle) {
            let html = '';
            turnosDetalleData.turnos_detalle.forEach(r => {
                html += `
                    <tr>
                        <td><strong>${r.turno}</strong></td>
                        <td>${r.actividades_count} sesiones</td>
                        <td>${r.horas_activas} hs</td>
                    </tr>
                `;
            });
            tbodyTurnosDetalle.innerHTML = html;
        }

        // Refresh Matplotlib dynamic plots (All 4 charts)
        const timestamp = Date.now();

        const imgMes = document.getElementById('img-grafico-mes');
        if (imgMes) imgMes.src = `/api/v1/admin/informes/grafico-mes?t=${timestamp}`;

        const imgTurnosDetalle = document.getElementById('img-grafico-turnos-detalle');
        if (imgTurnosDetalle) imgTurnosDetalle.src = `/api/v1/admin/informes/grafico-turnos-detalle?t=${timestamp}`;

        const imgTurno = document.getElementById('img-grafico-turno');
        if (imgTurno) imgTurno.src = `/api/v1/admin/informes/grafico-turno?t=${timestamp}`;

        const imgSemana = document.getElementById('img-grafico-semana');
        if (imgSemana) imgSemana.src = `/api/v1/admin/informes/grafico-semana?t=${timestamp}`;

    } catch (e) {
        console.error("Error cargando informes:", e);
    }
}

// 6. Configuración del Sistema
async function loadConfiguracion() {
    try {
        const res = await API.get('/api/v1/configuracion');
        const cfg = res.configuracion;

        document.getElementById('cfg-inactividad').value = cfg.inactividad_minutos || 10;
        document.getElementById('cfg-manana-init').value = cfg.inicio_turno_manana || '07:00';
        document.getElementById('cfg-manana-end').value = cfg.fin_turno_manana || '12:00';
        document.getElementById('cfg-tarde-init').value = cfg.inicio_turno_tarde || '14:00';
        document.getElementById('cfg-tarde-end').value = cfg.fin_turno_tarde || '17:00';
        document.getElementById('cfg-noche-init').value = cfg.inicio_turno_noche || '22:00';
        document.getElementById('cfg-noche-end').value = cfg.fin_turno_noche || '06:00';
    } catch (e) {
        console.error("Error cargando configuración:", e);
    }
}

async function guardarConfiguracion(e) {
    e.preventDefault();
    const items = [
        { clave: 'inactividad_minutos', valor: document.getElementById('cfg-inactividad').value },
        { clave: 'inicio_turno_manana', valor: document.getElementById('cfg-manana-init').value },
        { clave: 'fin_turno_manana', valor: document.getElementById('cfg-manana-end').value },
        { clave: 'inicio_turno_tarde', valor: document.getElementById('cfg-tarde-init').value },
        { clave: 'fin_turno_tarde', valor: document.getElementById('cfg-tarde-end').value },
        { clave: 'inicio_turno_noche', valor: document.getElementById('cfg-noche-init').value },
        { clave: 'fin_turno_noche', valor: document.getElementById('cfg-noche-end').value }
    ];

    try {
        await API.post('/api/v1/configuracion', { items });
        alert("Configuración del sistema guardada exitosamente.");
    } catch (e) {
        alert("Error guardando configuración.");
    }
}

// Helper genérico para llamadas API Fetch
const API = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
    },
    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
    },
    async delete(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        return await res.json();
    }
};
