import asyncio
import aiomysql
import os

async def clean_users():
    conn = await aiomysql.connect(
        host=os.getenv("MARIADB_SERVER", "mariadb"),
        port=3306,
        user=os.getenv("MARIADB_USER", "mediciones"),
        password=os.getenv("MARIADB_USER_PASS", "secret"),
        db=os.getenv("MARIADB_DB", "metalurgica_db")
    )
    async with conn.cursor() as cur:
        await cur.execute("UPDATE actividades SET operario_id = 2 WHERE operario_id = 4")
        await cur.execute("UPDATE actividades SET operario_id = 3 WHERE operario_id = 5")
        await cur.execute("UPDATE asignaciones_actuales SET operario_id = 2 WHERE operario_id = 4")
        await cur.execute("UPDATE asignaciones_actuales SET operario_id = 3 WHERE operario_id = 5")
        await cur.execute("DELETE FROM usuarios WHERE id IN (4, 5)")
        await cur.execute("UPDATE usuarios SET username = 'juanperez', telegram_id = NULL WHERE id = 2")
        await cur.execute("UPDATE usuarios SET username = 'carlosgomez', telegram_id = NULL WHERE id = 3")
        await conn.commit()
    conn.close()
    print("Database operarios cleaned up! Only IDs 2 & 3 remain.")

if __name__ == "__main__":
    asyncio.run(clean_users())
