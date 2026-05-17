from fastapi import APIRouter, HTTPException, UploadFile, File, Query

from core.database import search_food_list
from services.gemini import extrair_alimento
from services.receitas import receita_do_dia, OBJETIVOS_RECEITAS
from services.dicas import selecionar_dica

food_router = APIRouter(
    prefix="/api",
    tags=["alimentos"],
)


@food_router.get("/search")
def search(q: str = Query(default="", min_length=0)):
    return search_food_list(q)


@food_router.post("/identificar-alimento")
async def identificar_alimento(image: UploadFile = File(...)):
    image_bytes = await image.read()

    resultado = extrair_alimento("", image_bytes)

    if not resultado or not resultado.get("alimento"):
        raise HTTPException(
            status_code=422,
            detail="Não foi possível identificar o alimento na imagem.",
        )

    return {
        "status": "success",
        "alimento": resultado.get("alimento"),
        "gramas": resultado.get("gramas") or 0.0,
    }


@food_router.get("/receita-do-dia")
def receita_do_dia_endpoint(objetivo: str = Query(...)):
    objetivo_upper = objetivo.strip().upper()

    if objetivo_upper not in OBJETIVOS_RECEITAS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Objetivo inválido. "
                f"Use um de: {', '.join(OBJETIVOS_RECEITAS)}"
            ),
        )

    receita = receita_do_dia(objetivo_upper)

    return {
        "status": "success",
        "receita": receita,
    }


@food_router.get("/dicas-macrocard")
def dicas_macrocard(
        maior_deficit: int = Query(...),
        proteina_consumida: float = Query(default=0.0, ge=0),
):
    dica = selecionar_dica(maior_deficit, proteina_consumida)

    if dica is None:
        raise HTTPException(
            status_code=400,
            detail="Parâmetro maior_deficit inválido.",
        )

    return {
        "status": "success",
        "dica": {
            "icone": dica.icone,
            "titulo": dica.titulo,
            "corpo": dica.corpo,
        },
    }