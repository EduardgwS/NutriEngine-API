import json
from dataclasses import dataclass
from pathlib import Path

_DICAS_PATH = Path(__file__).resolve().parent.parent / "data" / "dicas.json"

with open(_DICAS_PATH, "r", encoding="utf-8") as _f:
    _CATALOGO: dict[str, list[dict]] = json.load(_f)


@dataclass(frozen=True)
class Dica:
    icone:  str
    titulo: str
    corpo:  str


def selecionar_dica(maior_deficit: int, proteina_consumida: float) -> Dica | None:
    lista = _CATALOGO.get(str(maior_deficit))
    if lista is None:
        return None

    seed  = int(proteina_consumida * 10)
    entry = lista[seed % len(lista)]
    return Dica(icone=entry["icone"], titulo=entry["titulo"], corpo=entry["corpo"])
