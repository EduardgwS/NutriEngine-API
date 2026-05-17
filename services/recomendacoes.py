import logging

log = logging.getLogger("megumi")

TAGS_VALIDAS: frozenset[str] = frozenset({
    "ALTA_PROTEINA",
    "CARBOIDRATO",
    "GORDURA_BOA",
    "GANHAR_MUSCULOS",
    "PERDER_PESO",
    "MELHORAR_ALIMENTACAO",
})

_TAG_CONFIG: dict[str, dict] = {
    "ALTA_PROTEINA": {
        "categorias_alvo":      ["proteína"],
        "categorias_penalizar": [],
        "motivo":               "Excelente para bater sua meta de proteínas do dia.",
        "scorer": lambda p: min(p["proteinas"] / 30.0, 1.0),
    },
    "CARBOIDRATO": {
        "categorias_alvo":      ["carboidrato"],
        "categorias_penalizar": [],
        "motivo":               "Boa fonte de carboidrato para repor sua energia.",
        "scorer": lambda p: min(p["carboidratos"] / 50.0, 1.0),
    },
    "GORDURA_BOA": {
        "categorias_alvo":      ["gordura"],
        "categorias_penalizar": [],
        "motivo":               "Rico em gorduras boas para complementar sua dieta.",
        "scorer": lambda p: min(p["gorduras"] / 20.0, 1.0),
    },
    "GANHAR_MUSCULOS": {
        "categorias_alvo":      ["proteína", "carboidrato"],
        "categorias_penalizar": [],
        "motivo":               "Alta densidade calórica e proteica, ideal para ganho de massa.",
        "scorer": lambda p: min((p["proteinas"] * 1.5 + p["kcal"] * 0.01) / 50.0, 1.0),
    },
    "PERDER_PESO": {
        "categorias_alvo":      ["proteína"],
        "categorias_penalizar": ["gordura", "snack"],
        "motivo":               "Baixa caloria e bom teor proteico, aliado do seu emagrecimento.",
        "scorer": lambda p: min(p["proteinas"] / max(p["kcal"], 1) * 10, 1.0),
    },
    "MELHORAR_ALIMENTACAO": {
        "categorias_alvo":      ["proteína", "carboidrato", "gordura"],
        "categorias_penalizar": ["snack"],
        "motivo":               "Produto de qualidade nutricional para uma alimentação equilibrada.",
        "scorer": lambda p: 0.5,
    },
}


def _pontuar_por_tags(produto: dict, tags: list[str]) -> tuple[float, str]:
    score  = 0.0
    motivo = "Complementa sua dieta de forma equilibrada."
    cat    = produto.get("categoria", "").lower()

    for tag in tags:
        cfg = _TAG_CONFIG.get(tag)
        if not cfg:
            continue

        score += cfg["scorer"](produto)

        if cat in [c.lower() for c in cfg["categorias_alvo"]]:
            score += 0.4
            motivo = cfg["motivo"]

        for pen_cat in cfg["categorias_penalizar"]:
            if cat == pen_cat.lower():
                score -= 0.3

    if produto.get("preco_antigo") is not None:
        score += 0.1

    return max(score, 0.0), motivo


def recomendar_por_tags(tags: list[str], produtos: list[dict], n: int = 6) -> list[dict]:
    pontuados = sorted(
        ((p, *_pontuar_por_tags(p, tags)) for p in produtos),
        key=lambda x: x[1],
        reverse=True,
    )

    resultado:    list[dict]     = []
    contagem_cat: dict[str, int] = {}
    MAX_POR_CAT = 3

    for produto, score, motivo in pontuados:
        if len(resultado) >= n:
            break
        cat = produto.get("categoria", "outro")
        if contagem_cat.get(cat, 0) >= MAX_POR_CAT:
            continue

        resultado.append({
            "id":           produto["id"],
            "nome":         produto["nome"],
            "marca":        produto.get("marca", ""),
            "imagem_url":   produto.get("imagem_url", ""),
            "nome_mercado": produto.get("nome_mercado", ""),
            "logo_mercado": produto.get("logo_mercado", ""),
            "preco_atual":  produto["preco_atual"],
            "preco_antigo": produto.get("preco_antigo"),
            "quantidade_g": produto.get("quantidade_g", 0.0),
            "motivo":       motivo,
            "url_compra":   produto["url_compra"],
            "categoria":    produto.get("categoria", ""),
            "kcal":         produto.get("kcal", 0.0),
            "proteinas":    produto.get("proteinas", 0.0),
            "carboidratos": produto.get("carboidratos", 0.0),
            "gorduras":     produto.get("gorduras", 0.0),
        })
        contagem_cat[cat] = contagem_cat.get(cat, 0) + 1

    log.info(f"[RECOMENDACAO] tags={tags} selecionados={len(resultado)}")
    return resultado