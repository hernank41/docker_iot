import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless Docker server
import matplotlib.pyplot as plt
import io
import logging

logging.basicConfig(level=logging.INFO)

# Set dark theme aesthetic
plt.style.use('dark_background')

def generar_grafico_turno(reporte_turno: list) -> io.BytesIO:
    """Genera un gráfico de barras horizontales/agrupadas de horas activas por día y máquina."""
    if not reporte_turno:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    fechas_maquinas = {}
    for r in reporte_turno:
        lbl = f"{r['fecha']}\n({r['maquina']})"
        fechas_maquinas[lbl] = float(r.get('horas_activas', 0.0))

    labels = list(fechas_maquinas.keys())
    horas = list(fechas_maquinas.values())

    colors = ['#89b4fa' if 'Torno' in l else '#a6e3a1' for l in labels]
    bars = ax.barh(labels, horas, color=colors, edgecolor='#cdd6f4', linewidth=0.8)

    ax.set_xlabel('Horas Operativas (hs)', color='#cdd6f4', fontsize=11, fontweight='bold')
    ax.set_title('Horas Operativas por Día y Máquina (Últimos 7 Días)', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
    ax.grid(axis='x', color='#45475a', linestyle='--', alpha=0.5)
    ax.tick_params(colors='#cdd6f4', labelsize=9)

    for bar in bars:
        width = bar.get_width()
        ax.text(width + 0.1, bar.get_y() + bar.get_height()/2, f"{width:.2f} hs",
                va='center', ha='left', color='#cdd6f4', fontsize=9, fontweight='bold')

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
    """Genera un gráfico de barras para el rendimiento de un operario específico."""
    if not maquinas_stats:
        return None

    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    fig.patch.set_facecolor('#1e1e2e')
    ax.set_facecolor('#181825')

    maquinas = [m['maquina'] for m in maquinas_stats]
    horas = [float(m['horas_activas']) for m in maquinas_stats]

    bars = ax.bar(maquinas, horas, color='#f5c2e7', edgecolor='#cdd6f4', width=0.4)

    ax.set_ylabel('Horas Operadas (hs)', color='#cdd6f4', fontsize=10, fontweight='bold')
    ax.set_title(f'Rendimiento de Operario: {nombre_operario}', color='#f5e0dc', fontsize=12, fontweight='bold', pad=15)
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
