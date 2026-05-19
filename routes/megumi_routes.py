from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.auth import usuario_atual
from core.database import (
    buscar_alimento,
    buscar_ultimo_insight,
    carregar_historico,
    salvar_insight,
    salvar_mensagem,
)
from services.gemini import extrair_alimento, gerar_insight_nutricional, responder_megumi

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
    nome:           str
    quantidade_g:   float
    kcal:           float
    proteinas_g:    float
    carboidratos_g: float
    gorduras_g:     float


class Refeicao(BaseModel):
    hora:      str
    alimentos: list[AlimentoRefeicao]


class DiaNutricional(BaseModel):
    data:           str
    kcal_total:     float
    proteinas_g:    float
    carboidratos_g: float
    gorduras_g:     float
    refeicoes:      list[Refeicao] = []


class HistoricoSaude(BaseModel):
    perfil:                PerfilSaude         | None = None
    historico_nutricional: list[DiaNutricional]       = []


class MegumiChatRequest(BaseModel):
    text:            str            = Field(..., strip_whitespace=True, min_length=1)
    historico_saude: HistoricoSaude | None = None


class MegumiInsightRequest(BaseModel):
    historico_saude: HistoricoSaude



@megumi_router.post("/chat")
def megumi_chat(
        payload: MegumiChatRequest,
        usuario: dict = Depends(usuario_atual),
):
    username = usuario["user"]

    alimento_info = extrair_alimento(payload.text)
    contexto = buscar_alimento(alimento_info["alimento"]) if alimento_info.get("alimento") else ""

    historico = carregar_historico(username, limite=20)
    resposta  = responder_megumi(
        texto      = payload.text,
        contexto   = contexto,
        historico  = historico,
        saude_json = payload.historico_saude.model_dump() if payload.historico_saude else None,
    )

    salvar_mensagem(username, "user",   payload.text)
    salvar_mensagem(username, "megumi", resposta)
    return {"response": resposta}


@megumi_router.get("/historico")
def megumi_historico(
        limite:  int  = 50,
        usuario: dict = Depends(usuario_atual),
):
    return {"mensagens": carregar_historico(usuario["user"], limite=limite)}


@megumi_router.post("/insight")
def megumi_insight(
        payload: MegumiInsightRequest,
        usuario: dict = Depends(usuario_atual),
):
    username = usuario["user"]

    ultimo = buscar_ultimo_insight(username)
    if ultimo:
        criado_em = ultimo["created_at"]
        agora     = datetime.now(criado_em.tzinfo) if criado_em.tzinfo else datetime.now()
        if agora - criado_em < timedelta(hours=24):
            return {"insight": ultimo["insight"]}

    if not payload.historico_saude.historico_nutricional:
        return {"insight": "Continue registrando suas refeições, que irei te dar um apoio!"}

    resposta = gerar_insight_nutricional(saude_json=payload.historico_saude.model_dump())
    if resposta:
        salvar_insight(username, resposta)
    return {"insight": resposta}