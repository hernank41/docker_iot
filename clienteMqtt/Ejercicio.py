import asyncio, ssl, certifi, logging, os
import aiomqtt

logging.basicConfig(format='%(asctime)s - cliente mqtt - %(levelname)s:%(message)s', level=logging.INFO, datefmt='%d/%m/%Y %H:%M:%S %z')

async def topic0():
    await client.subscribe(os.environ['TOPICO'])
    async for message in client.messages:
        logging.info(str(message.topic) + ": " + message.payload.decode("utf-8"))

async def topic1():
    await client.subscribe(os.environ['TOPIC1'])
    async for message in client.messages:
        logging.info(str(message.topic) + ": " + message.payload.decode("utf-8"))

async def publicar(cont):
    await client.publish("TOPIC2", cont)
    await asyncio.sleep(5)

async def contar(cont):
    cont = 0
    while True:
        cont += 1
        await asyncio.sleep(3)
    return cont

async def main():
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()
    cont = 0
    async with aiomqtt.Client(
        os.environ['SERVIDOR'],
        port=8883,
        tls_context=tls_context,
    ) as client:
        task0 = asyncio.create_task(topic0())
        task1 = asyncio.create_task(topic1())
        task2 = asyncio.create_task(contar(cont))
        task3 = asyncio.create_task(publicar(cont))
        

if __name__ == "__main__":
    asyncio.run(main())