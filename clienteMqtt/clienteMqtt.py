import asyncio, ssl, certifi, logging, os
import aiomqtt

logging.basicConfig(format='%(asctime)s - cliente mqtt - %(levelname)s:%(message)s', level=logging.INFO, datefmt='%d/%m/%Y %H:%M:%S %z')

class contador:
    def __init__(self):
        self.valor = 0
    
    def aumentar(self):
        self.valor += 1

async def publicar(cont):
    while True:
        await client.publish(os.environ['TOPIC2'], contador1.valor)
        await asyncio.sleep(5)

async def contar():
    while True:
        contador1.aumentar()
        await asyncio.sleep(3)

async def recibir():
    while True:
        async for message in client.messages:
            logging.info(str(message.topic) + ": " + message.payload.decode("utf-8"))

async def main():
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()

    async with aiomqtt.Client(
        os.environ['SERVIDOR'],
        port=8883,
        tls_context=tls_context,
    ) as client:
        await client.subscribe(os.environ['TOPIC0'])
        await client.subscribe(os.environ['TOPIC1'])
        async with asyncio.TaskGroup() as Grupo_1:
            task0 = Grupo_1.create_task(recibir())
            task1 = Grupo_1.create_task(contar())
            task2 = Grupo_1.create_task(publicar())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupcion")
        sys.exit(0)