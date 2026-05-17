import json
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger("megumi")

_RECEITAS_PATH = Path(__file__).resolve().parent.parent / "data" / "receitas.json"


def _carregar_receitas() -> dict:
    try:
        return json.loads(_RECEITAS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.error(f"[RECEITAS] Arquivo não encontrado: {_RECEITAS_PATH}")
        return {}
    except json.JSONDecodeError:
        log.error("[RECEITAS] Erro de formatação no JSON.")
        return {}


_CATALOGO = _carregar_receitas()

def receita_do_dia(objetivo: str) -> dict | None:
    lista = _CATALOGO.get(objetivo.upper())

    if not lista:
        log.warning(f"[RECEITAS] Objetivo '{objetivo}' não encontrado ou lista vazia.")
        return None

    return lista[date.today().timetuple().tm_yday % len(lista)]


OBJETIVOS_RECEITAS: frozenset[str] = frozenset(_carregar_receitas().keys())