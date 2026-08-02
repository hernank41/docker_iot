import httpx
import os
import logging

API_URL = os.getenv("API_URL", "http://apiiot:8000")

class APIClient:
    def __init__(self, base_url: str = API_URL):
        self.base_url = base_url

    async def login_admin(self, username: str, password: str):
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/v1/auth/login",
                json={"username": username, "password": password},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

    async def get_usuarios(self):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/usuarios", timeout=5.0)
            return res.json().get("usuarios", []) if res.status_code == 200 else []

    async def crear_usuario(self, nombre: str, username: str, rol: str = "OPERARIO"):
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/v1/usuarios",
                json={"nombre": nombre, "username": username, "rol": rol},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

    async def eliminar_usuario(self, usuario_id: int):
        async with httpx.AsyncClient() as client:
            res = await client.delete(f"{self.base_url}/api/v1/usuarios/{usuario_id}", timeout=5.0)
            return res.json() if res.status_code == 200 else None

    async def get_usuario_stats(self, usuario_id: int):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/usuarios/{usuario_id}/stats", timeout=5.0)
            return res.json() if res.status_code == 200 else None

    async def vincular_telegram(self, telegram_id: int, username: str):
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/v1/usuarios/vincular-telegram",
                params={"telegram_id": telegram_id, "username": username},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

    async def get_maquinas(self):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/maquinas", timeout=5.0)
            return res.json().get("maquinas", []) if res.status_code == 200 else []

    async def get_estado_actual(self):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/maquinas/estado-actual", timeout=5.0)
            return res.json().get("maquinas", []) if res.status_code == 200 else []

    async def get_asignacion_operario(self, operario_id: int):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/asignaciones/operario/{operario_id}", timeout=5.0)
            return res.json() if res.status_code == 200 else {}

    async def get_herramientas(self, maquina_id: int = None):
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/api/v1/herramientas"
            params = {"maquina_id": maquina_id} if maquina_id else {}
            res = await client.get(url, params=params, timeout=5.0)
            return res.json().get("herramientas", []) if res.status_code == 200 else []

    async def crear_herramienta(self, maquina_id: int, nombre: str, horas_expectativa: float):
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/v1/herramientas",
                json={"maquina_id": maquina_id, "nombre": nombre, "horas_expectativa": horas_expectativa},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

    async def actualizar_asignacion(self, maquina_id: int, operario_id: int = None, herramienta_id: int = None):
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/v1/asignaciones",
                json={"maquina_id": maquina_id, "operario_id": operario_id, "herramienta_id": herramienta_id},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

    async def get_actividades_activas(self):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/actividades/activas", timeout=5.0)
            return res.json().get("actividades_activas", []) if res.status_code == 200 else []

    async def finalizar_actividad(self, actividad_id: int, comentario: str):
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/v1/actividades/finalizar",
                json={"actividad_id": actividad_id, "comentario": comentario},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

    async def actualizar_comentario_actividad(self, actividad_id: int, comentario: str):
        async with httpx.AsyncClient() as client:
            res = await client.put(
                f"{self.base_url}/api/v1/admin/actividades/{actividad_id}/comentario",
                json={"comentario": comentario},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

    async def get_reporte_turno(self):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/informes/reporte-turno", timeout=5.0)
            return res.json().get("reporte_turno", []) if res.status_code == 200 else []

    async def get_reporte_semana(self):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/informes/reporte-semana", timeout=5.0)
            return res.json().get("reporte_semana", []) if res.status_code == 200 else []

    async def get_configuracion(self):
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{self.base_url}/api/v1/configuracion", timeout=5.0)
            return res.json().get("configuracion", {}) if res.status_code == 200 else {}

    async def actualizar_configuracion(self, clave: str, valor: str):
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/api/v1/configuracion",
                json={"items": [{"clave": clave, "valor": valor}]},
                timeout=5.0
            )
            return res.json() if res.status_code == 200 else None

api_client = APIClient()
