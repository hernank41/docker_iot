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
            window.location.reload();
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
        window.location.reload();
    } catch (e) {
        window.location.reload();
    }
}

// 1. Dashboard Monitoreo en Tiempo Real
async function loadDashboardData() {
    try {
        const data = await API.get('/api/v1/maquinas/estado-actual');
        const container = document.getElementById('cards-maquinas-container');
        if (!container) return;

        let html = '';
        data.maquinas.forEach(m => {
            const isActiva = m.estado === 'ACTIVA';
            const isEmergencia = m.estado === 'PARADA_EMERGENCIA';
            const badgeClass = isActiva ? 'bg-success' : (isEmergencia ? 'bg-danger' : 'bg-warning text-dark');
            
            html += `
                <div class="col-md-6 mb-4">
                    <div class="card h-100 border-start border-4 ${isActiva ? 'border-success' : (isEmergencia ? 'border-danger' : 'border-warning')}">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h5 class="card-title mb-0">${m.maquina} (${m.tipo})</h5>
                            <span class="badge ${badgeClass} fs-6">${m.estado}</span>
                        </div>
                        <div class="card-body">
                            <p class="card-text mb-2"><strong>Operario:</strong> ${m.operario_nombre || 'Sin Operario'}</p>
                            <p class="card-text mb-2"><strong>Herramienta:</strong> ${m.herramienta_nombre || 'Sin Herramienta'}</p>
                            <p class="card-text mb-2"><strong>Causa / Estado:</strong> <code class="text-info">${m.causa || 'OPERACION_NORMAL'}</code></p>
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
    try {
        const stats = await API.get(`/api/v1/usuarios/${id}/stats`);
        const u = stats.usuario;
        const r = stats.resumen;
        
        document.getElementById('stats-op-title').innerText = `Rendimiento de Operario: ${nombre}`;
        let infoHtml = `<p class="mb-1"><strong>Username:</strong> <code>@${u.username}</code> | <strong>Total Sesiones:</strong> <code>${r.total_actividades}</code> | <strong>Horas Totales:</strong> <code>${r.total_horas} hs</code></p>`;
        document.getElementById('stats-op-info').innerHTML = infoHtml;
        
        // Cargar imagen de gráfico de líneas dinámico de Matplotlib
        const chartImg = document.getElementById('stats-op-chart');
        chartImg.src = `/api/v1/admin/usuarios/${id}/grafico-stats?t=${new Date().getTime()}`;

        new bootstrap.Modal(document.getElementById('modalStatsOperario')).show();
    } catch (e) {
        alert("Error al cargar estadísticas.");
    }
}

// 3. Herramientas y Desgaste
async function loadHerramientas() {
    try {
        const data = await API.get('/api/v1/herramientas');
        const tbody = document.getElementById('tabla-herramientas-body');
        if (!tbody) return;

        let html = '';
        data.herramientas.forEach(h => {
            const pct = parseFloat(h.porcentaje_desgaste || 0);
            let barClass = 'bg-success';
            if (pct >= 70 && pct < 90) barClass = 'bg-warning text-dark';
            if (pct >= 90) barClass = 'bg-danger';

            html += `
                <tr>
                    <td>${h.id}</td>
                    <td><strong>${h.nombre}</strong></td>
                    <td>${h.maquina_nombre}</td>
                    <td>${h.horas_uso} hs / ${h.horas_expectativa} hs</td>
                    <td style="width: 250px;">
                        <div class="progress" style="height: 20px;">
                            <div class="progress-bar ${barClass}" role="progressbar" style="width: ${Math.min(pct, 100)}%;">
                                ${pct.toFixed(1)}%
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        loadMaquinasSelectOptions();
    } catch (e) {
        console.error("Error cargando herramientas:", e);
    }
}

async function loadMaquinasSelectOptions() {
    try {
        const res = await API.get('/api/v1/maquinas');
        const select = document.getElementById('h-maquina-id');
        if (!select) return;
        select.innerHTML = res.maquinas.map(m => `<option value="${m.id}">${m.nombre} (${m.tipo})</option>`).join('');
    } catch (e) {}
}

async function guardarNuevaHerramienta() {
    const maquina_id = parseInt(document.getElementById('h-maquina-id').value);
    const nombre = document.getElementById('h-nombre').value.trim();
    const horas_expectativa = parseFloat(document.getElementById('h-expectativa').value);

    if (!nombre || isNaN(horas_expectativa)) return alert("Complete los datos requeridos.");

    try {
        await API.post('/api/v1/herramientas', { maquina_id, nombre, horas_expectativa });
        bootstrap.Modal.getInstance(document.getElementById('modalCrearHerramienta')).hide();
        document.getElementById('formCrearHerramienta').reset();
        loadHerramientas();
    } catch (e) {
        alert("Error registrando herramienta.");
    }
}

// 4. Control de Actividades (Fit: Merge & Split)
let actividadesData = [];
async function loadActividades() {
    try {
        const res = await API.get('/api/v1/admin/actividades');
        actividadesData = res.actividades;
        const tbody = document.getElementById('tabla-actividades-body');
        if (!tbody) return;

        let html = '';
        actividadesData.forEach(a => {
            html += `
                <tr>
                    <td><input type="checkbox" class="form-check-input chk-merge" value="${a.id}"></td>
                    <td>#${a.id}</td>
                    <td><strong>${a.maquina}</strong></td>
                    <td>${a.operario_nombre || '<span class="badge bg-warning text-dark">Sin Operario</span>'}</td>
                    <td>${a.herramienta_nombre || 'N/A'}</td>
                    <td><small>${a.fecha_inicio}</small></td>
                    <td><small>${a.fecha_fin || 'En Curso'}</small></td>
                    <td><code>${a.tiempo_activo_horas} hs</code></td>
                    <td><small class="text-muted">${a.comentario || '-'}</small></td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary py-0" onclick="prepararSplit(${a.id}, '${a.fecha_inicio}', '${a.fecha_fin || ''}')">Split</button>
                        <button class="btn btn-sm btn-outline-secondary py-0" onclick="prepararAsignarOperario(${a.id})">Asignar</button>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error("Error cargando actividades:", e);
    }
}

async function ejecutarMerge() {
    const selected = Array.from(document.querySelectorAll('.chk-merge:checked')).map(cb => parseInt(cb.value));
    if (selected.length < 2) return alert("Seleccione al menos 2 actividades con la casilla de verificación para fusionar.");

    if (!confirm(`¿Confirma la fusión de ${selected.length} actividades seleccionadas en un único registro?`)) return;

    try {
        await API.post('/api/v1/admin/actividades/merge', { actividad_ids: selected });
        loadActividades();
    } catch (e) {
        alert("Error al fusionar actividades.");
    }
}

function prepararSplit(id, inicio, fin) {
    document.getElementById('split-act-id').value = id;
    document.getElementById('split-corte').value = inicio;
    new bootstrap.Modal(document.getElementById('modalSplitActividad')).show();
}

async function ejecutarSplit() {
    const id = document.getElementById('split-act-id').value;
    const fecha_corte = document.getElementById('split-corte').value.trim();

    try {
        await API.post(`/api/v1/admin/actividades/${id}/split`, { fecha_corte });
        bootstrap.Modal.getInstance(document.getElementById('modalSplitActividad')).hide();
        loadActividades();
    } catch (e) {
        alert("Error al dividir actividad. Verifique el formato de fecha (YYYY-MM-DD HH:MM:SS).");
    }
}

async function prepararAsignarOperario(actId) {
    try {
        const users = await API.get('/api/v1/usuarios');
        const operarios = users.usuarios.filter(u => u.rol === 'OPERARIO');
        const opId = prompt("Ingrese ID de Operario a asignar:\n" + operarios.map(o => `${o.id}: ${o.nombre}`).join('\n'));
        if (!opId) return;

        await API.post(`/api/v1/admin/actividades/${actId}/asignar-operario`, { operario_id: parseInt(opId) });
        loadActividades();
    } catch (e) {
        alert("Error al asignar operario retroactivo.");
    }
}

// 5. Informes & KPIs
async function loadInformes() {
    try {
        const resTurno = await API.get('/api/v1/informes/reporte-turno');
        const resSemana = await API.get('/api/v1/informes/reporte-semana');
        
        let htmlTurno = '<ul class="list-group list-group-flush mb-3">';
        resTurno.reporte_turno.slice(0, 8).forEach(t => {
            htmlTurno += `<li class="list-group-item bg-transparent text-light border-secondary px-0"><strong>${t.fecha} (${t.maquina}):</strong> ${t.horas_activas} hs (${t.total_actividades} sesiones)</li>`;
        });
        htmlTurno += '</ul>';

        let htmlSemana = '<ul class="list-group list-group-flush mb-3">';
        resSemana.reporte_semana.forEach(s => {
            htmlSemana += `<li class="list-group-item bg-transparent text-light border-secondary px-0"><strong>${s.maquina}:</strong> ${s.total_horas_activas} hs operativas totales</li>`;
        });
        htmlSemana += '</ul>';

        document.getElementById('informes-turno-text').innerHTML = htmlTurno;
        document.getElementById('informes-semana-text').innerHTML = htmlSemana;

        const ts = new Date().getTime();
        document.getElementById('informes-turno-img').src = `/api/v1/admin/informes/grafico-turno?t=${ts}`;
        document.getElementById('informes-semana-img').src = `/api/v1/admin/informes/grafico-semana?t=${ts}`;
    } catch (e) {
        console.error("Error cargando informes:", e);
    }
}

function exportarCSV() {
    window.location.href = '/api/v1/admin/informes/exportar-csv';
}

// 6. Configuración Global
async function loadConfiguracion() {
    try {
        const data = await API.get('/api/v1/configuracion');
        const cfg = data.configuracion || {};

        if (cfg.inactividad_minutos) document.getElementById('cfg-timeout').value = cfg.inactividad_minutos;
        if (cfg.inicio_turno_manana) document.getElementById('cfg-manana').value = cfg.inicio_turno_manana;
        if (cfg.fin_turno_manana) document.getElementById('cfg-fin-manana').value = cfg.fin_turno_manana;
        if (cfg.inicio_turno_tarde) document.getElementById('cfg-tarde').value = cfg.inicio_turno_tarde;
        if (cfg.fin_turno_tarde) document.getElementById('cfg-fin-tarde').value = cfg.fin_turno_tarde;
        if (cfg.inicio_turno_noche) document.getElementById('cfg-noche').value = cfg.inicio_turno_noche;
        if (cfg.fin_turno_noche) document.getElementById('cfg-fin-noche').value = cfg.fin_turno_noche;
    } catch (e) {
        console.error("Error cargando configuración:", e);
    }
}

async function guardarConfiguracion() {
    const items = [
        { clave: 'inactividad_minutos', valor: document.getElementById('cfg-timeout').value },
        { clave: 'inicio_turno_manana', valor: document.getElementById('cfg-manana').value },
        { clave: 'fin_turno_manana', valor: document.getElementById('cfg-fin-manana').value },
        { clave: 'inicio_turno_tarde', valor: document.getElementById('cfg-tarde').value },
        { clave: 'fin_turno_tarde', valor: document.getElementById('cfg-fin-tarde').value },
        { clave: 'inicio_turno_noche', valor: document.getElementById('cfg-noche').value },
        { clave: 'fin_turno_noche', valor: document.getElementById('cfg-fin-noche').value }
    ];

    try {
        await API.post('/api/v1/admin/configuracion', { items });
        alert("Configuración guardada exitosamente.");
    } catch (e) {
        alert("Error al guardar configuración.");
    }
}
