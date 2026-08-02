import matplotlib
matplotlib.use('Agg')  # Headless backend for Docker
import matplotlib.pyplot as plt
import io
import logging

logging.basicConfig(level=logging.INFO)
plt.style.use('dark_background')

def generar_grafico_turno(reporte_turno: list) -> io.BytesIO:
    """Genera un gráfico de barras comparativas por fecha y máquina (últimos 7 días)."""
    if not reporte_turno:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    fechas_set = sorted(list(set(str(r['fecha'])[:10] for r in reporte_turno)))
    torno_data = {f: 0.0 for f in fechas_set}
    fresa_data = {f: 0.0 for f in fechas_set}

    for r in reporte_turno:
        f_str = str(r['fecha'])[:10]
        m_name = r['maquina']
        h_val = float(r.get('horas_activas', 0.0))
        if 'Torno' in m_name:
            torno_data[f_str] += h_val
        else:
            fresa_data[f_str] += h_val

    x_labels = [f[5:].replace('-', '/') for f in fechas_set]
    torno_y = [torno_data[f] for f in fechas_set]
    fresa_y = [fresa_data[f] for f in fechas_set]

    import numpy as np
    x = np.arange(len(x_labels))
    width = 0.35

    ax.bar(x - width/2, torno_y, width, label='Torno 1', color='#89b4fa', edgecolor='#cdd6f4')
    ax.bar(x + width/2, fresa_y, width, label='Fresadora 1', color='#a6e3a1', edgecolor='#cdd6f4')

    ax.set_ylabel('Horas Operativas (hs)', color='#cdd6f4', fontsize=11, fontweight='bold')
    ax.set_title('Horas Operativas por Día y Máquina (Últimos 7 Días)', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, color='#cdd6f4', fontsize=9)
    ax.grid(axis='y', color='#45475a', linestyle='--', alpha=0.5)
    ax.legend(facecolor='#1e1e2e', edgecolor='#45475a', labelcolor='#cdd6f4', fontsize=9)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf

def generar_grafico_semana(reporte_semana: list) -> io.BytesIO:
    """Genera un gráfico de BARRAS HORIZONTALES (evitando gráfico de donut) de uso semanal por máquina."""
    if not reporte_semana:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    maquinas = [r['maquina'] for r in reporte_semana]
    horas = [float(r.get('total_horas_activas', 0.0)) for r in reporte_semana]
    sesiones = [int(r.get('total_actividades', 0)) for r in reporte_semana]

    import numpy as np
    y_pos = np.arange(len(maquinas))
    colors = ['#89b4fa', '#a6e3a1', '#f9e2af', '#fab387']

    bars = ax.barh(y_pos, horas, align='center', color=colors[:len(maquinas)], edgecolor='#cdd6f4', height=0.45)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(maquinas, color='#cdd6f4', fontsize=11, fontweight='bold')
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
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf

def generar_grafico_mes(reporte_turno: list) -> io.BytesIO:
    """Genera un gráfico de producción mensual (30 días) separado por máquina en subgráficos verticales."""
    if not reporte_turno:
        return None

    import numpy as np
    by_maquina = {}
    for r in reporte_turno:
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
        by_maquina[m]['horas'].append(float(r.get('horas_activas', 0.0)))

    num_maquinas = len(by_maquina)
    fig, axes = plt.subplots(num_maquinas, 1, figsize=(8.5, 3.8 * num_maquinas), dpi=150)
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

        ax.bar(x_indices, horas, color=c, alpha=0.35, edgecolor=c, linewidth=1.2, width=0.5)
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

    fig.suptitle("Evolución de Producción Diario por Máquina (Último Mes / 30 Días)", color='#cdd6f4', fontsize=12, fontweight='bold', y=0.99)
    plt.tight_layout(pad=2.8)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf

def generar_grafico_turnos_detalle(turnos_detalle: list) -> io.BytesIO:
    """Genera gráfico PNG de barras mostrando la distribución por turno de trabajo."""
    if not turnos_detalle:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    turnos_order = ['Turno Mañana (07:00-12:00)', 'Turno Tarde (14:00-17:00)', 'Turno Noche (22:00-06:00)']
    horas_map = {r['turno']: float(r['horas_activas']) for r in turnos_detalle}
    sesiones_map = {r['turno']: int(r['actividades_count']) for r in turnos_detalle}

    labels_display = ['Mañana\n(07-12h)', 'Tarde\n(14-17h)', 'Noche\n(22-06h)']
    horas_list = [horas_map.get(t, 0.0) for t in turnos_order]
    sesiones_list = [sesiones_map.get(t, 0) for t in turnos_order]

    colors = ['#89b4fa', '#f9e2af', '#cba6f7']
    bars = ax.bar(labels_display, horas_list, color=colors, edgecolor='#cdd6f4', width=0.45)

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
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf

def generar_grafico_operario(nombre_operario: str, maquinas_stats: list) -> io.BytesIO:
    """Genera un gráfico espacioso y claro con 1 subgráfico separado por máquina (uno debajo del otro) para un operario."""
    if not maquinas_stats:
        return None

    import numpy as np
    num_maquinas = len(maquinas_stats)
    fig, axes = plt.subplots(num_maquinas, 1, figsize=(8.5, 3.8 * num_maquinas), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')

    if num_maquinas == 1:
        axes_list = [axes]
    elif isinstance(axes, np.ndarray):
        axes_list = list(axes.flatten())
    else:
        axes_list = list(axes)

    colors = ['#89b4fa', '#a6e3a1', '#f9e2af', '#f38ba8']

    for idx, m in enumerate(maquinas_stats):
        ax = axes_list[idx]
        ax.set_facecolor('#181825')
        c = colors[idx % len(colors)]
        
        m_nombre = m['maquina']
        h_val = float(m['horas_activas'])
        ses_count = int(m['actividades_count'])

        bars = ax.bar([m_nombre], [h_val], color=c, edgecolor='#cdd6f4', width=0.3)
        
        ax.set_ylim(0, max(h_val * 1.35, 1.0))
        ax.set_ylabel('Horas Operadas (hs)', color='#cdd6f4', fontsize=10, fontweight='bold')
        ax.set_title(f'Máquina: {m_nombre} — Operario: {nombre_operario}', color='#f5e0dc', fontsize=11, fontweight='bold', pad=12)
        ax.grid(axis='y', color='#45475a', linestyle='--', alpha=0.5)
        ax.tick_params(colors='#cdd6f4', labelsize=10)

        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.05, f"{height:.2f} hs  ({ses_count} sesiones)",
                    ha='center', va='bottom', color='#cdd6f4', fontsize=9, fontweight='bold')

    fig.suptitle(f'Rendimiento Detallado por Máquina: {nombre_operario}', color='#f5e0dc', fontsize=12, fontweight='bold', y=0.99)
    plt.tight_layout(pad=2.8)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf

def generar_grafico_herramientas(herramientas_list: list) -> io.BytesIO:
    """Genera un gráfico de barras horizontales con el porcentaje de desgaste por herramienta y línea de umbral crítico."""
    if not herramientas_list:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    nombres = [h['nombre'][:25] for h in herramientas_list]
    desgastes = [float(h.get('porcentaje_desgaste', 0.0)) for h in herramientas_list]
    colors = ['#f38ba8' if d >= 90 else ('#f9e2af' if d >= 60 else '#a6e3a1') for d in desgastes]

    import numpy as np
    y_pos = np.arange(len(nombres))
    bars = ax.barh(y_pos, desgastes, align='center', color=colors, edgecolor='#cdd6f4', height=0.5)

    ax.axvline(x=90, color='#f38ba8', linestyle='--', linewidth=1.5, label='Umbral Crítico (90%)')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(nombres, color='#cdd6f4', fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('Desgaste (%)', color='#cdd6f4', fontsize=10, fontweight='bold')
    ax.set_title('Estado de Desgaste y Salud de Herramientas de Corte', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
    ax.set_xlim(0, 110)
    ax.grid(axis='x', color='#45475a', linestyle='--', alpha=0.5)
    ax.legend(facecolor='#1e1e2e', edgecolor='#45475a', labelcolor='#cdd6f4', fontsize=9)

    for bar in bars:
        width = bar.get_width()
        ax.text(width + 1.5, bar.get_y() + bar.get_height()/2., f"{width:.1f}%",
                ha='left', va='center', color='#cdd6f4', fontsize=9, fontweight='bold')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf
