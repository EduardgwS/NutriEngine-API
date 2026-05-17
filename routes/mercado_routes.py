from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from core.database import listar_parceiros, listar_produtos_ativos
from services.recomendacoes import recomendar_por_tags, TAGS_VALIDAS

mercado_router = APIRouter(prefix="/mercado", tags=["mercado"])


class RecomendacoesRequest(BaseModel):
    necessidades: list[str]

    @field_validator("necessidades")
    @classmethod
    def validar_tags(cls, tags: list[str]) -> list[str]:
        tags_upper = [t.strip().upper() for t in tags]
        invalidas  = set(tags_upper) - TAGS_VALIDAS
        if invalidas:
            raise ValueError(
                f"Tags inválidas: {', '.join(sorted(invalidas))}. "
                f"Permitidas: {', '.join(sorted(TAGS_VALIDAS))}"
            )
        return tags_upper


@mercado_router.get("/parceiros")
def get_parceiros():
    return {"parceiros": listar_parceiros()}


@mercado_router.post("/recomendacoes")
def post_recomendacoes(body: RecomendacoesRequest):
    produtos = listar_produtos_ativos()
    if not produtos:
        return {"recomendacoes": []}
    return {"recomendacoes": recomendar_por_tags(body.necessidades, produtos)}