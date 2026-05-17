import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from core.auth import usuario_atual
from core.database import buscar_alimento, carregar_historico, salvar_mensagem
from services.gemini import responder_megumi

megumi_router = APIRouter(prefix="/megumi", tags=["megumi"])


@megumi_router.post("/chat")
async def megumi_chat(
        text:            str               = Form(...),
        image:           UploadFile | None = File(None),
        historico_saude: str | None        = Form(None),
        usuario:         dict              = Depends(usuario_atual),
):
    imagem_bytes = await image.read() if image else None
    saude_json   = None

    if historico_saude:
        try:
            saude_json = json.loads(historico_saude)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="historico_saude não é um JSON válido")

    historico = carregar_historico(usuario["user"], limite=20)
    resposta  = responder_megumi(
        texto        = text,
        contexto     = buscar_alimento(text),
        imagem_bytes = imagem_bytes,
        historico    = historico,
        saude_json   = saude_json,
    )

    salvar_mensagem(usuario["user"], "user",   text)
    salvar_mensagem(usuario["user"], "megumi", resposta)

    return {"response": resposta}


@megumi_router.get("/historico")
def megumi_historico(
        limite:  int  = 50,
        usuario: dict = Depends(usuario_atual),
):
    return {"mensagens": carregar_historico(usuario["user"], limite=limite)}