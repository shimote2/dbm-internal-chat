import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI()

# Banco de dados em memória
usuarios = {}   # user: senha
conexoes = {}   # user: websocket
grupos = {}     # #nome_grupo: [lista_de_membros]

@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "Servidor de Chat Online"}

@app.websocket("/")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_logado = None

    try:
        while True:
            data = await websocket.receive_text()
            req = json.loads(data)
            acao = req.get("acao")

            if acao == "login":
                u, s = req["user"], req["senha"]
                
                # Validação de Senha (Cadastra automático se não existir)
                if u in usuarios and usuarios[u] != s:
                    await websocket.send_text(json.dumps({"acao": "erro", "msg": "Senha incorreta!"}))
                    continue
                
                usuarios[u] = s
                user_logado = u
                conexoes[u] = websocket
                
                await websocket.send_text(json.dumps({"acao": "login_ok"}))
                await broadcast_online()

            elif acao == "enviar" and user_logado:
                alvo = req["alvo"]
                msg = {"acao": "msg", "de": user_logado, "alvo": alvo, "texto": req["texto"]}
                
                if alvo.startswith("@"): # DM
                    dest = alvo[1:]
                    if dest in conexoes:
                        await conexoes[dest].send_text(json.dumps(msg))
                    await websocket.send_text(json.dumps(msg)) # Ecoa de volta para o remetente ver
                
                elif alvo.startswith("#"): # Grupo
                    if alvo in grupos:
                        for membro in grupos[alvo]:
                            if membro in conexoes:
                                await conexoes[membro].send_text(json.dumps(msg))
                
                else: # Global
                    for ws in conexoes.values():
                        await ws.send_text(json.dumps(msg))

            elif acao == "criar_grupo" and user_logado:
                nome = "#" + req["nome"]
                membros = req["membros"] + [user_logado]
                grupos[nome] = membros
                # Avisa apenas os membros que o grupo foi criado
                for m in membros:
                    if m in conexoes:
                        await conexoes[m].send_text(json.dumps({"acao": "novo_grupo", "nome": nome}))

    except WebSocketDisconnect:
        if user_logado and user_logado in conexoes:
            del conexoes[user_logado]
            await broadcast_online()

async def broadcast_online():
    # Atualiza a lista de usuários para todo mundo montar as opções de DM
    ativos = list(conexoes.keys())
    msg = json.dumps({"acao": "online", "users": ativos})
    for ws in conexoes.values():
        await ws.send_text(msg)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
