import json
import logging
import re

from google import genai
from google.genai import types, errors
from core.config import (GEMINI_API_KEY, GEMINI_MODEL_CHAT, GEMINI_MODEL_EXTRACT, GEMINI_MODEL_INSIGHT, MEGUMI_INSIGHT_PROMPT, MEGUMI_PROMPT, TACO_PROMPT)

log = logging.getLogger("megumi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

client = genai.Client(api_key=GEMINI_API_KEY)

_RE_CONVERSA_FIADA = re.compile(
    r"^(oi|oii|oiii|ol[aá]|bom\s?dia|boa\s?tarde|boa\s?noite|tudo\s?bem|como\s?vai"
    r"|obrigad[oa]|valeu|tchau|vlw|flw|xau|menu|ajuda|quem\s?[eé]\s?voc?[eê])\??\!?$",
    re.IGNORECASE,
)


def _is_pure_conversation(texto: str) -> bool:
    t = texto.strip().lower()
    return bool(t and _RE_CONVERSA_FIADA.match(t) and not any(u in t for u in ["g ", "gr ", "grama", "kg"]))



def extrair_alimento(texto: str, imagem_bytes: bytes | None = None) -> dict:
    if not imagem_bytes and _is_pure_conversation(texto):
        return {"alimento": None, "gramas": None}

    try:
        parts: list = []
        if imagem_bytes:
            parts.append(types.Part.from_bytes(data=imagem_bytes, mime_type="image/jpeg"))
        parts.append(
            texto if texto.strip()
            else "Identifique o alimento principal nesta imagem e estime o peso em gramas."
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL_EXTRACT,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=TACO_PROMPT,
                temperature=0.0,
                max_output_tokens=600,
            ),
        )

        raw = response.text
        if not raw:
            reason = getattr(getattr((response.candidates or [None])[0], "finish_reason", None), "name", "UNKNOWN")
            log.warning(f"[EXTRAIR] Resposta vazia. finish_reason={reason}")
            return {"alimento": None, "gramas": None}

        match = re.search(r'\{.*?}', raw.strip(), re.DOTALL)
        if not match:
            log.warning(f"[EXTRAIR] Nenhum JSON encontrado: {raw!r}")
            return {"alimento": None, "gramas": None}

        parsed = json.loads(match.group())
        alimento = (parsed.get("alimento") or "").strip().lower() or None
        try:
            gramas = float(parsed["gramas"]) if parsed.get("gramas") is not None else None
        except (TypeError, ValueError):
            gramas = None

        log.info(f"[EXTRAIR] alimento={alimento!r} gramas={gramas}")
        return {"alimento": alimento, "gramas": gramas}

    except Exception as e:
        log.warning(f"[EXTRAIR] Falha: {e}")
        return {"alimento": None, "gramas": None}



def _formatar_saude(saude: dict) -> str:
    blocos: list[str] = []
    perfil = saude.get("perfil") or {}
    kcal_meta = perfil.get("kcal_recomendadas")

    if perfil:
        campos = {
            "peso_kg": lambda v: f"Peso: {v} kg",
            "altura_m": lambda v: f"Altura: {v} m",
            "idade": lambda v: f"Idade: {v} anos",
            "sexo": lambda v: f"Sexo: {v}",
            "objetivo": lambda v: f"Objetivo: {v}",
            "nivel_atividade": lambda v: f"Nível de atividade: {v}",
            "kcal_recomendadas": lambda v: f"Meta calórica diária: {v} kcal",
        }
        linhas = [fmt(perfil[k]) for k, fmt in campos.items() if perfil.get(k) is not None]
        if linhas:
            blocos.append("=== PERFIL DO USUÁRIO ===\n" + "\n".join(linhas))

    historico = saude.get("historico_nutricional") or []
    if historico:
        linhas_hist = ["=== HISTÓRICO NUTRICIONAL ==="]
        for dia in historico:
            kcal_total = dia.get("kcal_total", 0)
            saldo = f" | saldo: {kcal_total - kcal_meta:+.0f} kcal vs meta" if kcal_meta else ""
            linhas_hist.append(
                f"{dia.get('data', '?')} → {kcal_total:.0f} kcal{saldo} | "
                f"Prot: {dia.get('proteinas_g', 0):.1f}g | "
                f"Carbo: {dia.get('carboidratos_g', 0):.1f}g | "
                f"Gord: {dia.get('gorduras_g', 0):.1f}g"
            )
            for ref in (dia.get("refeicoes") or []):
                alimentos = ref.get("alimentos") or []
                if not alimentos:
                    continue
                linhas_hist.append(f"  {ref.get('hora', '?')}")
                for a in alimentos:
                    linhas_hist.append(
                        f"    • {a.get('nome', '?')} ({a.get('quantidade_g', 0):.0f}g) → "
                        f"{a.get('kcal', 0):.0f} kcal | "
                        f"Prot: {a.get('proteinas_g', 0):.1f}g | "
                        f"Carbo: {a.get('carboidratos_g', 0):.1f}g | "
                        f"Gord: {a.get('gorduras_g', 0):.1f}g"
                    )
        blocos.append("\n".join(linhas_hist))

    return "\n\n".join(blocos)



def responder_megumi(
        texto: str,
        contexto: str = "",
        historico: list[dict] | None = None,
        saude_json: dict | None = None,
) -> str | None:
    contents: list[types.Content] = [
        types.Content(
            role="user" if msg["papel"] == "user" else "model",
            parts=[types.Part(text=msg["mensagem"])],
        )
        for msg in (historico or [])
    ]

    partes_ctx = [p for p in [contexto, _formatar_saude(saude_json) if saude_json else ""] if p]
    texto_turno = f"{texto}\n\n{chr(10).join(partes_ctx)}".strip()
    contents.append(types.Content(role="user", parts=[types.Part(text=texto_turno)]))

    log.info(
        f"[MEGUMI] modelo={GEMINI_MODEL_CHAT} taco={contexto or '(vazio)'} saúde={'sim' if saude_json else 'não'} histórico={len(historico or [])} msgs")

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_CHAT,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=MEGUMI_PROMPT,
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )
        return response.text
    except errors.ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return "Desculpa, já estou cansada demais por hoje. Amanhã podemos conversar mais!"
        return "Tive um probleminha aqui, mas já volto!"
    except Exception:
        return "Tive um problemão aqui, tente novamente."



def gerar_insight_nutricional(saude_json: dict) -> str | None:
    if not saude_json:
        return "Não encontrei dados suficientes para gerar um insight."

    texto = f"Analise meus dados de saúde e alimentação dos últimos dias e me dê um insight:\n\n{_formatar_saude(saude_json)}"

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL_INSIGHT,
            contents=texto,
            config=types.GenerateContentConfig(
                system_instruction=MEGUMI_INSIGHT_PROMPT,
                temperature=0.3,
                max_output_tokens=2600,
            ),
        )
        return response.text
    except errors.ClientError as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return "Estou processando muitas análises agora. Pode tentar novamente em instantes?"
        return "Tive um problema técnico para analisar seus dados agora. Já estou verificando!"
    except Exception:
        return "Desculpe, ocorreu um erro inesperado ao processar o seu insight."
