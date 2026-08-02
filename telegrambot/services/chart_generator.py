import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless Docker server
import matplotlib.pyplot as plt
import io
import logging

logging.basicConfig(level=logging.INFO)

# Set dark theme aesthetic
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
    """Genera un gráfico circular/donut de distribución semanal por máquina."""
    if not reporte_semana:
        return None

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    labels = [r['maquina'] for r in reporte_semana]
    horas = [float(r.get('total_horas_activas', 0.0)) for r in reporte_semana]
    colors = ['#89b4fa', '#a6e3a1', '#f9e2af', '#fab387']

    wedges, texts, autotexts = ax.pie(
        horas, labels=labels, autopct='%1.1f%%',
        startangle=140, colors=colors[:len(labels)],
        wedgeprops=dict(width=0.4, edgecolor='#1e1e2e', linewidth=2),
        textprops=dict(color='#cdd6f4', fontsize=10, fontweight='bold')
    )

    for autotext in autotexts:
        autotext.set_color('#11111b')
        autotext.set_weight('bold')

    ax.set_title('Distribución Semanal de Uso por Máquina', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf

def generar_grafico_operario(nombre_operario: str, maquinas_stats: list) -> io.BytesIO:
    """Genera un gráfico de LÍNEAS limpio por máquina para el rendimiento de un operario."""
    if not maquinas_stats:
        return None

    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    maquinas = [m['maquina'] for m in maquinas_stats]
    horas = [float(m['horas_activas']) for m in maquinas_stats]
    colors = ['#89b4fa' if 'Torno' in m else '#a6e3a1' for m in maquinas]

    bars = ax.bar(maquinas, horas, color=colors, edgecolor='#cdd6f4', width=0.35)

    ax.set_ylabel('Horas Operadas Totales (hs)', color='#cdd6f4', fontsize=10, fontweight='bold')
    ax.set_title(f'Rendimiento por Máquina - {nombre_operario}', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
    ax.grid(axis='y', color='#45475a', linestyle='--', alpha=0.5)
    ax.tick_params(colors='#cdd6f4', labelsize=10)

    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.1, f"{height:.2f} hs",
                ha='center', va='bottom', color='#cdd6f4', fontsize=9, fontweight='bold')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf
