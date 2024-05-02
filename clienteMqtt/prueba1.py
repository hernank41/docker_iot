import asyncio
class contador:
    def __init__(self):
        self.valor = 0
    
    def aumentar(self):
        self.valor += 1


contador1 = contador()
contador1.aumentar()
print(contador1.valor)
contador1.aumentar()
print(contador1.valor)