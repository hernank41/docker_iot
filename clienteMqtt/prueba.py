import asyncio

class contador:
    def __init__(self):
        self.valor = 0
    
    def aumentar(self):
        self.valor += 1

async def publicar():
    while True:
        print(contador1.valor)
        await asyncio.sleep(5)

async def contar():
    while True:
        contador1.aumentar()
        await asyncio.sleep(3)

async def main():
    async with asyncio.TaskGroup() as Grupo_1:
        task1 = Grupo_1.create_task((contar()))
        task2 = Grupo_1.create_task(publicar())

contador1 = contador()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupcion")
        sys.exit(0)