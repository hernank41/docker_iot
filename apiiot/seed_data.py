import asyncio
import aiomysql
import os
import random
from datetime import datetime, timedelta, time

MARIADB_SERVER = os.getenv("MARIADB_SERVER", "localhost")
MARIADB_PORT = int(os.getenv("MARIADB_PORT", 3306))
MARIADB_USER = os.getenv("MARIADB_USER", "mediciones")
MARIADB_USER_PASS = os.getenv("MARIADB_USER_PASS", "secret")
MARIADB_DB = os.getenv("MARIADB_DB", "metalurgica_db")

async def seed_database():
    print(f"Connecting to MariaDB at {MARIADB_SERVER}:{MARIADB_PORT}/{MARIADB_DB}...")
    conn = await aiomysql.connect(
        host=MARIADB_SERVER,
        port=MARIADB_PORT,
        user=MARIADB_USER,
        password=MARIADB_USER_PASS,
        db=MARIADB_DB,
        autocommit=True
    )

    async with conn.cursor() as cur:
        print("Cleaning tables: actividades, registro_actividad, asignaciones_actuales, herramientas...")
        await cur.execute("DELETE FROM actividades")
        await cur.execute("DELETE FROM registro_actividad")
        await cur.execute("DELETE FROM asignaciones_actuales")
        await cur.execute("DELETE FROM herramientas")

        # 1. Ensure Usuarios
        await cur.execute("SELECT id, username FROM usuarios")
        rows = await cur.fetchall()
        users_by_name = {r[1]: r[0] for r in rows}

        if "admin" not in users_by_name:
            await cur.execute("INSERT INTO usuarios (nombre, username, password_hash, rol) VALUES ('Administrador', 'admin', 'admin123', 'ADMIN')")
            admin_id = cur.lastrowid
        else:
            admin_id = users_by_name["admin"]

        if "juanperez" not in users_by_name:
            await cur.execute("INSERT INTO usuarios (nombre, username, rol, telegram_id) VALUES ('Juan Pérez', 'juanperez', 'OPERARIO', '2')")
            juan_id = cur.lastrowid
        else:
            juan_id = users_by_name["juanperez"]

        if "carlosgomez" not in users_by_name:
            await cur.execute("INSERT INTO usuarios (nombre, username, rol, telegram_id) VALUES ('Carlos Gómez', 'carlosgomez', 'OPERARIO', '3')")
            carlos_id = cur.lastrowid
        else:
            carlos_id = users_by_name["carlosgomez"]

        operarios = [juan_id, carlos_id]

        # 2. Ensure Maquinas
        await cur.execute("SELECT id, nombre FROM maquinas")
        rows = await cur.fetchall()
        maq_by_name = {r[1]: r[0] for r in rows}

        if "Torno_1" not in maq_by_name:
            await cur.execute("INSERT INTO maquinas (nombre, tipo, estado) VALUES ('Torno_1', 'Torno', 'PARADA')")
            torno_id = cur.lastrowid
        else:
            torno_id = maq_by_name["Torno_1"]

        if "Fresadora_1" not in maq_by_name:
            await cur.execute("INSERT INTO maquinas (nombre, tipo, estado) VALUES ('Fresadora_1', 'Fresadora', 'PARADA')")
            fresa_id = cur.lastrowid
        else:
            fresa_id = maq_by_name["Fresadora_1"]

        maquinas = [torno_id, fresa_id]

        # 3. Re-create new tools
        tools_by_maq = {torno_id: [], fresa_id: []}

        # Torno Tools
        torno_tools_def = [
            ('Torno_1 / Inserto de desbaste general / CNMG 120408', 60.0),
            ('Torno_1 / Inserto de desbaste general / WNMG 080408', 60.0),
            ('Torno_1 / Inserto de acabado y perfilado / DCMT 11T304', 50.0),
            ('Torno_1 / Inserto de acabado y perfilado / VBMT 160404', 50.0),
            ('Torno_1 / Inserto de tronzado y ranurado / MGMN 200', 30.0),
            ('Torno_1 / Inserto de tronzado y ranurado / MGMN 300', 30.0)
        ]
        for name, expect in torno_tools_def:
            await cur.execute("INSERT INTO herramientas (maquina_id, nombre, horas_expectativa, horas_uso) VALUES (%s, %s, %s, 0.0)", (torno_id, name, expect))
            tools_by_maq[torno_id].append(cur.lastrowid)

        # Fresadora Tools
        fresa_tools_def = [
            ('Fresadora_1 / Mecha helicoidal estándar / DIN 338', 40.0),
            ('Fresadora_1 / Mecha helicoidal estándar / DIN 1897', 40.0),
            ('Fresadora_1 / Mecha de centrar / DIN 333-A', 50.0),
            ('Fresadora_1 / Mecha de centrar / DIN 333-R', 50.0),
            ('Fresadora_1 / Mecha de puntear (NC Drill) / DIN 1836', 60.0),
            ('Fresadora_1 / Mecha de puntear (NC Drill) / DIN 6539', 60.0)
        ]
        for name, expect in fresa_tools_def:
            await cur.execute("INSERT INTO herramientas (maquina_id, nombre, horas_expectativa, horas_uso) VALUES (%s, %s, %s, 0.0)", (fresa_id, name, expect))
            tools_by_maq[fresa_id].append(cur.lastrowid)

        # Ensure asignaciones_actuales has tools
        await cur.execute("INSERT INTO asignaciones_actuales (maquina_id, operario_id, herramienta_id, comentario) VALUES (%s, %s, %s, 'Operación normal')", (torno_id, juan_id, tools_by_maq[torno_id][1]))
        await cur.execute("INSERT INTO asignaciones_actuales (maquina_id, operario_id, herramienta_id, comentario) VALUES (%s, %s, %s, 'Operación normal')", (fresa_id, carlos_id, tools_by_maq[fresa_id][0]))

        # 4. Generate Realistic Past Month Data (30 days ago to today)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        curr_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        random.seed(2026) # Deterministic realistic seed

        total_actividades = 0
        emergency_stops_placed = 0
        max_emergencies = 4

        comentarios_normales = [
            "Mecanizado de lote eje primario",
            "Corte y torneado de bujes",
            "Planeado de bancada fresadora",
            "Mecanizado de chaveteros",
            "Operación de desbaste grueso",
            "Acabado superficial con refrigerante",
            "Fabricación de piñones industriales",
            "Refrentado de bridas de acero"
        ]

        comentarios_emergencia = [
            "EMERGENCIA: Presion aceite baja",
            "EMERGENCIA: Sobrecalentamiento husillo",
            "EMERGENCIA: Atascamiento viruta bancada",
            "EMERGENCIA: Alerta vibracion excesiva"
        ]

        print("Generating activity history...")

        while curr_date <= end_date:
            weekday = curr_date.weekday()

            # Sunday (6): No work
            if weekday == 6:
                curr_date += timedelta(days=1)
                continue

            # Saturday (5): 50% chance only ONE operator works a morning shift
            if weekday == 5:
                if random.random() < 0.5:
                    op_working = [random.choice(operarios)]
                    shift_blocks = [(time(8, 0), time(12, 0))]
                else:
                    curr_date += timedelta(days=1)
                    continue
            else:
                # Monday to Friday (0..4): Regular shifts
                op_working = []
                if random.random() < 0.88: op_working.append(juan_id)
                if random.random() < 0.88: op_working.append(carlos_id)
                
                if not op_working:
                    op_working = [random.choice(operarios)]

                shift_blocks = [
                    (time(7, 0), time(12, 0)),
                    (time(14, 0), time(17, 0))
                ]

            for (start_t, end_t) in shift_blocks:
                block_start = datetime.combine(curr_date.date(), start_t)
                block_end = datetime.combine(curr_date.date(), end_t)

                # Keep track of occupied time windows
                op_busy_until = {op: block_start for op in op_working}
                maq_busy_until = {m: block_start for m in maquinas}

                current_pointer = block_start

                while current_pointer < block_end - timedelta(minutes=40):
                    # Pick available operators and machines
                    avail_ops = [op for op in op_working if op_busy_until[op] <= current_pointer]
                    avail_maqs = [m for m in maquinas if maq_busy_until[m] <= current_pointer]

                    if not avail_ops or not avail_maqs:
                        current_pointer += timedelta(minutes=10)
                        continue

                    # Select 1 op and 1 maq
                    op = random.choice(avail_ops)
                    maq = random.choice(avail_maqs)
                    tool = random.choice(tools_by_maq[maq])

                    # Activity duration between 40 min and 110 min
                    duration_min = random.randint(40, 110)
                    act_start = current_pointer + timedelta(minutes=random.randint(0, 10))
                    act_end = act_start + timedelta(minutes=duration_min)

                    if act_end > block_end:
                        act_end = block_end

                    active_sec = int((act_end - act_start).total_seconds())

                    if active_sec < 600: # skip under 10 min
                        current_pointer += timedelta(minutes=15)
                        continue

                    # Emergency stop logic
                    if emergency_stops_placed < max_emergencies and random.random() < 0.05:
                        estado = "PARADA_EMERGENCIA"
                        comentario = random.choice(comentarios_emergencia)
                        emergency_stops_placed += 1
                    else:
                        estado = "FINALIZADA"
                        comentario = random.choice(comentarios_normales)

                    # Insert actividad
                    await cur.execute(
                        """INSERT INTO actividades (maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, estado, comentario)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (maq, op, tool, act_start, act_end, active_sec, estado, comentario)
                    )
                    total_actividades += 1

                    # Insert telemetry events in registro_actividad
                    reg_estado = "PARADA_EMERGENCIA" if estado == "PARADA_EMERGENCIA" else "PARADA"
                    await cur.execute(
                        """INSERT INTO registro_actividad (maquina_id, timestamp, estado, codigo_estado, causa)
                           VALUES (%s, %s, 'ACTIVA', 1, 'START_SESSION')""",
                        (maq, act_start)
                    )
                    await cur.execute(
                        """INSERT INTO registro_actividad (maquina_id, timestamp, estado, codigo_estado, causa)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (maq, act_end, reg_estado, 0 if reg_estado == "PARADA" else 2, comentario)
                    )

                    # Update busy markers
                    op_busy_until[op] = act_end + timedelta(minutes=random.randint(5, 20))
                    maq_busy_until[maq] = act_end + timedelta(minutes=random.randint(5, 20))

                    current_pointer = act_end + timedelta(minutes=5)

            curr_date += timedelta(days=1)

        # 5. Recalculate tool usage hours
        print("Recalculating tool wear hours...")
        for maq_id, tools in tools_by_maq.items():
            for t_id in tools:
                await cur.execute("SELECT SUM(tiempo_activo_segundos) FROM actividades WHERE herramienta_id = %s", (t_id,))
                res = await cur.fetchone()
                seg = res[0] or 0
                horas_uso = round(float(seg) / 3600.0, 2)
                await cur.execute("UPDATE herramientas SET horas_uso = %s WHERE id = %s", (horas_uso, t_id))

        conn.close()
        print(f"Database successfully re-seeded with {total_actividades} activities and {emergency_stops_placed} emergency stops!")

if __name__ == "__main__":
    asyncio.run(seed_database())
