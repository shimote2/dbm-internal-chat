import os
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
from supabase import create_client, Client

app = FastAPI()
conexoes = {} # Dicionário: nick -> websocket

# Conexão com o Supabase a partir das variáveis do Render
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def limpar_mensagens_antigas():
    # Calcula a data de 5 dias atrás e deleta no Supabase
    limite = (datetime.now() - timedelta(days=5)).isoformat()
    try:
        supabase.table("messages").delete().lt("data_hora", limite).execute()
    except Exception as e:
        print("Erro ao limpar mensagens:", e)

@app.get("/")
@app.head("/")
async def health_check():
    return {"status": "Servidor Online e conectado ao Supabase"}

@app.websocket("/")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_logado = None

    try:
        while True:
            data = await websocket.receive_text()
            req = json.loads(data)
            acao = req.get("acao")

            if acao == "registrar":
                u, s = req["user"], req["senha"]
                res = supabase.table("users").select("nick").eq("nick", u).execute()
                if len(res.data) > 0:
                    await websocket.send_text(json.dumps({"acao": "erro", "msg": "Usuário já existe!"}))
                else:
                    supabase.table("users").insert({"nick": u, "senha": s}).execute()
                    await websocket.send_text(json.dumps({"acao": "sucesso", "msg": "Conta criada! Clique em Entrar."}))
            
            elif acao == "login":
                u, s = req["user"], req["senha"]
                res = supabase.table("users").select("senha").eq("nick", u).execute()
                
                if len(res.data) == 0 or res.data[0]["senha"] != s:
                    await websocket.send_text(json.dumps({"acao": "erro", "msg": "Usuário ou senha incorretos!"}))
                else:
                    user_logado = u
                    conexoes[u] = websocket
                    await websocket.send_text(json.dumps({"acao": "login_ok"}))
                    
                    limpar_mensagens_antigas()
                    
                    # Carrega grupos do usuário
                    g_res = supabase.table("grupo_membros").select("nome").eq("nick", u).execute()
                    meus_grupos = list(set([r["nome"] for r in g_res.data]))
                    for g in meus_grupos:
                        await websocket.send_text(json.dumps({"acao": "novo_grupo", "nome": g}))
                    
                    # Carrega histórico (Últimas 300 mensagens gerais para filtrar localmente e poupar requisições)
                    alvos_permitidos = ['Global', '@'+u] + meus_grupos
                    m_res = supabase.table("messages").select("*").order("data_hora", desc=True).limit(300).execute()
                    hist = []
                    for row in reversed(m_res.data):
                        if row["alvo"] in alvos_permitidos or row["de"] == u:
                            hist.append({"de": row["de"], "alvo": row["alvo"], "texto": row["texto"]})
                    
                    await websocket.send_text(json.dumps({"acao": "historico", "msgs": hist}))
                    await broadcast_online()

            elif acao == "enviar" and user_logado:
                alvo, texto = req["alvo"], req["texto"]
                
                # Salva a mensagem no Supabase
                supabase.table("messages").insert({"de": user_logado, "alvo": alvo, "texto": texto}).execute()
                
                msg = {"acao": "msg", "de": user_logado, "alvo": alvo, "texto": texto}
                msg_json = json.dumps(msg)
                
                if alvo.startswith("@"):
                    dest = alvo[1:]
                    if dest in conexoes:
                        await conexoes[dest].send_text(msg_json)
                    await websocket.send_text(msg_json)
                elif alvo.startswith("#"):
                    res = supabase.table("grupo_membros").select("nick").eq("nome", alvo).execute()
                    for row in res.data:
                        membro = row["nick"]
                        if membro in conexoes:
                            await conexoes[membro].send_text(msg_json)
                else:
                    for ws in conexoes.values():
                        await ws.send_text(msg_json)

            elif acao == "criar_grupo" and user_logado:
                nome = "#" + req["nome"].replace(" ", "")
                membros = list(set(req["membros"] + [user_logado]))
                
                # Prepara o lote (batch) de inserts no Supabase
                inserts = [{"nome": nome, "nick": m} for m in membros]
                supabase.table("grupo_membros").insert(inserts).execute()
                
                for m in membros:
                    if m in conexoes:
                        await conexoes[m].send_text(json.dumps({"acao": "novo_grupo", "nome": nome}))

    except WebSocketDisconnect:
        if user_logado and user_logado in conexoes:
            del conexoes[user_logado]
            await broadcast_online()

async def broadcast_online():
    # Pega todos os cadastrados no banco
    res = supabase.table("users").select("nick").execute()
    todos = [r["nick"] for r in res.data]
    ativos = list(conexoes.keys())
    
    msg = json.dumps({"acao": "online", "users": ativos, "todos": todos})
    for ws in conexoes.values():
        await ws.send_text(msg)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
