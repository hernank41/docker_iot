import asyncio
import aiomysql
import os

async def dump_db():
    conn = await aiomysql.connect(
        host=os.getenv("MARIADB_SERVER", "mariadb"),
        port=3306,
        user=os.getenv("MARIADB_USER", "mediciones"),
        password=os.getenv("MARIADB_USER_PASS", "secret"),
        db=os.getenv("MARIADB_DB", "metalurgica_db")
    )
    async with conn.cursor(aiomysql.DictCursor) as cur:
        tables = ['maquinas', 'usuarios', 'herramientas', 'asignaciones_actuales', 'configuracion_sistema', 'registro_actividad', 'actividades']
        with open('schema_seeded.sql', 'w', encoding='utf-8') as f:
            f.write("USE metalurgica_db;\n\n")
            for t in tables:
                await cur.execute(f"SELECT * FROM {t}")
                rows = await cur.fetchall()
                if not rows:
                    continue
                cols = list(rows[0].keys())
                f.write(f"-- Data for table {t}\n")
                for r in rows:
                    vals = []
                    for c in cols:
                        v = r[c]
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        else:
                            vals.append("'" + str(v).replace("'", "''") + "'")
                    f.write(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(vals)});\n")
                f.write("\n")
    conn.close()
    print("Database dumped to schema_seeded.sql successfully!")

if __name__ == "__main__":
    asyncio.run(dump_db())
