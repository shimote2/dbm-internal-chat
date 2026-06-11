import asyncio
import websockets
import json
import os

conexoes = set()

async def gerenciador_chat(websocket):
    conexoes.add(websocket)
    try:
        async for mensagem in websocket:
            websockets.broadcast(conexoes, mensagem)
    finally:
        conexoes.remove(websocket)

async def main():
    # O Render exige que a porta seja pega das variáveis de ambiente
    port = int(os.environ.get("PORT", 8001))
    
    async with websockets.serve(gerenciador_chat, "0.0.0.0", port):
        print(f"Servidor rodando na porta {port}...")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
