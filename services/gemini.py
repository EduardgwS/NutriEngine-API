import json
import logging
import re

from google import genai
from google.genai import types, errors

from core.config import GEMINI_API_KEY, GEMINI_MODEL, MEGUMI_PROMPT, TACO_PROMPT

log = logging.getLogger("megumi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

client  = genai.Client(api_key=GEMINI_API_KEY)
_JSON_RE = re.compile(r'\{.*?}', re.DOTALL)


def extrair_alimento(texto: str, imagem_bytes: bytes | None = None) -> dict:
    """Normaliza texto/imagem para o padrão TACO e estima peso em gramas."""
    tem_texto  = bool(texto.strip())
    tem_imagem = bool(imagem_bytes)

    if not tem_texto and not tem_imagem:
        return {"alimento": None, "gramas": None}

    try:
        parts: list = []
        if tem_imagem:
            parts.append(types.Part.from_bytes(data=imagem_bytes, mime_type="image/jpeg"))
        parts.append(
            texto if tem_texto
            else "Identifique o alimento principal nesta imagem e estime o peso em gramas."
        )

        response = client.models.generate_content(
            model    = GEMINI_MODEL,
            contents = parts,
            config   = types.GenerateContentConfig(
                system_instruction = TACO_PROMPT,
                temperature        = 0.0,
                max_output_tokens  = 600,
            ),
        )

        raw = response.text
        if not raw:
            reason = getattr(
                getattr((response.candidates or [None])[0], "finish_reason", None),
                "name", "UNKNOWN",
            )
            log.warning(f"[EXTRAIR] Resposta vazia. finish_reason={reason}")
            return {"alimento": None, "gramas": None}

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].removeprefix("json").strip()

        match = _JSON_RE.search(raw)
        if not match:
            log.warning(f"[EXTRAIR] Nenhum JSON encontrado: {raw!r}")
            return {"alimento": None, "gramas": None}

        parsed   = json.loads(match.group())
        alimento = (parsed.get("alimento") or "").strip().lower() or None
        gramas   = parsed.get("gramas")

        if gramas is not None:
            try:
                gramas = float(gramas)
            except (TypeError, ValueError):
                gramas = None

        log.info(f"[EXTRAIR] alimento={alimento!r} gramas={gramas} imagem={'sim' if tem_imagem else 'não'}")
        return {"alimento": alimento, "gramas": gramas}

    except Exception as e:
        log.warning(f"[EXTRAIR] Falha: {e}")
        return {"alimento": None, "gramas": None}


def _formatar_saude(saude: dict) -> str:
    """Converte dados de saúde do usuário para texto legível pela Megumi."""
    partes = []

    perfil = saude.get("perfil", {})
    if perfil:
        campos = [
            ("peso_kg",           lambda v: f"peso {v} kg"),
            ("altura_m",          lambda v: f"altura {v} m"),
            ("idade",             lambda v: f"{v} anos"),
            ("sexo",              lambda v: v),
            ("objetivo",          lambda v: f"objetivo: {v}"),
            ("nivel_atividade",   lambda v: f"atividade: {v}"),
            ("kcal_recomendadas", lambda v: f"meta calórica: {v} kcal/dia"),
        ]
        linha = [fmt(perfil[k]) for k, fmt in campos if k in perfil]
        if linha:
            partes.append("Perfil do usuário: " + ", ".join(linha))

    historico = saude.get("historico_nutricional", [])
    if historico:
        partes.append("Histórico nutricional dos últimos 7 dias:")
        for dia in historico:
            partes.append(
                f"  {dia['data']}: {dia['kcal']} kcal | "
                f"prot {dia['proteinas_g']}g | "
                f"carbo {dia['carboidratos_g']}g | "
                f"gord {dia['gorduras_g']}g"
            )

    return "\n".join(partes)


def responder_megumi(
        texto:        str,
        contexto:     str              = "",
        imagem_bytes: bytes | None     = None,
        historico:    list[dict] | None = None,
        saude_json:   dict | None      = None,
) -> str:
    contents: list[types.Content] = [
        types.Content(
            role  = "user" if msg["papel"] == "user" else "model",
            parts = [types.Part(text=msg["mensagem"])],
        )
        for msg in (historico or [])
    ]

    turno: list = []
    if imagem_bytes:
        turno.append(types.Part.from_bytes(data=imagem_bytes, mime_type="image/jpeg"))

    partes_ctx = [p for p in [contexto, _formatar_saude(saude_json) if saude_json else ""] if p]
    texto_turno = f"{texto}\n\n{chr(10).join(partes_ctx)}".strip() or "Analise esta imagem nutricional."
    turno.append(types.Part(text=texto_turno))
    contents.append(types.Content(role="user", parts=turno))

    log.info(f"[MEGUMI] texto={texto!r} taco={contexto or '(vazio)'} "
             f"saúde={'sim' if saude_json else 'não'} imagem={'sim' if imagem_bytes else 'não'} "
             f"histórico={len(historico or [])} msgs")

    try:
        response = client.models.generate_content(
            model    = GEMINI_MODEL,
            contents = contents,
            config   = types.GenerateContentConfig(
                system_instruction = MEGUMI_PROMPT,
                temperature        = 0.2,
                max_output_tokens  = 2048,
            ),
        )
        return response.text

    except errors.ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            log.error("[QUOTA] Tokens esgotados.")
            return "Desculpa, já estou cansada demais por hoje. Amanhã podemos conversar mais!"
        log.error("[MEGUMI] Erro de cliente na API.")
        return "Tive um probleminha aqui, mas já volto!"

    except Exception:
        log.error("[MEGUMI] Erro inesperado.")
        return "Tive um problemão aqui, espera aí que eu vou tentar resolver e já volto!"