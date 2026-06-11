import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()
conexoes = set()

# 1. Rota HTTP normal para acalmar o Health Check do Render
@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "Servidor online e rodando!"}

# 2. Rota do WebSocket para o nosso chat
@app.websocket("/")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    conexoes.add(websocket)
    try:
        while True:
            # Recebe a mensagem e retransmite para todo mundo
            mensagem = await websocket.receive_text()
            for conexao in conexoes:
                await conexao.send_text(mensagem)
    except WebSocketDisconnect:
        # Remove a pessoa da lista se ela fechar o chat
        conexoes.remove(websocket)

if __name__ == "__main__":
    # Pega a porta dinâmica do Render
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
