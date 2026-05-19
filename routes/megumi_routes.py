from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from core.auth import usuario_atual
from core.database import buscar_alimento, carregar_historico, salvar_mensagem
from services.gemini import extrair_alimento, responder_megumi

megumi_router = APIRouter(prefix="/megumi", tags=["megumi"])


class PerfilSaude(BaseModel):
    peso_kg:           float | None = None
    altura_m:          float | None = None
    idade:             int   | None = None
    sexo:              str   | None = None
    objetivo:          str   | None = None
    nivel_atividade:   str   | None = None
    kcal_recomendadas: float | None = None


class AlimentoRefeicao(BaseModel):
    nome:             str
    quantidade_g:     float
    kcal:             float
    proteinas_g:      float
    carboidratos_g:   float
    gorduras_g:       float


class Refeicao(BaseModel):
    hora:      str
    alimentos: list[AlimentoRefeicao]


class DiaNutricional(BaseModel):
    data:             str
    kcal_total:       float
    proteinas_g:      float
    carboidratos_g:   float
    gorduras_g:       float
    refeicoes:        list[Refeicao] = []


class HistoricoSaude(BaseModel):
    perfil:                PerfilSaude         | None = None
    historico_nutricional: list[DiaNutricional]       = []


class MegumiChatRequest(BaseModel):
    text:            str
    historico_saude: HistoricoSaude | None = None

    @field_validator("text")
    @classmethod
    def text_nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("O campo 'text' não pode estar vazio.")
        return v



@megumi_router.post("/chat")
async def megumi_chat(
        payload: MegumiChatRequest,
        usuario: dict = Depends(usuario_atual),
):
    alimento_info = extrair_alimento(payload.text)
    contexto = (
        buscar_alimento(alimento_info["alimento"])
        if alimento_info.get("alimento")
        else ""
    )

    historico = carregar_historico(usuario["user"], limite=20)
    resposta  = responder_megumi(
        texto      = payload.text,
        contexto   = contexto,
        historico  = historico,
        saude_json = payload.historico_saude.model_dump() if payload.historico_saude else None,
    )

    salvar_mensagem(usuario["user"], "user",   payload.text)
    salvar_mensagem(usuario["user"], "megumi", resposta)

    return {"response": resposta}


@megumi_router.get("/historico")
def megumi_historico(
        limite:  int  = 50,
        usuario: dict = Depends(usuario_atual),
):
    return {"mensagens": carregar_historico(usuario["user"], limite=limite)}