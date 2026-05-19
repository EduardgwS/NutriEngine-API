import json
import logging
import re

from google import genai
from google.genai import types, errors

from core.config import GEMINI_API_KEY, GEMINI_MODEL, MEGUMI_PROMPT, TACO_PROMPT

log = logging.getLogger("megumi")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

client = genai.Client(api_key=GEMINI_API_KEY)



def extrair_alimento(texto: str, imagem_bytes: bytes | None = None) -> dict:
    if not texto.strip() and not imagem_bytes:
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

        match = re.search(r'\{.*?}', raw, re.DOTALL)
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

        log.info(f"[EXTRAIR] alimento={alimento!r} gramas={gramas} imagem={'sim' if imagem_bytes else 'não'}")
        return {"alimento": alimento, "gramas": gramas}

    except Exception as e:
        log.warning(f"[EXTRAIR] Falha: {e}")
        return {"alimento": None, "gramas": None}



def _formatar_saude(saude: dict) -> str:
    blocos: list[str] = []

    perfil = saude.get("perfil") or {}
    if perfil:
        campos_perfil = {
            "peso_kg":           lambda v: f"Peso: {v} kg",
            "altura_m":          lambda v: f"Altura: {v} m",
            "idade":             lambda v: f"Idade: {v} anos",
            "sexo":              lambda v: f"Sexo: {v}",
            "objetivo":          lambda v: f"Objetivo: {v}",
            "nivel_atividade":   lambda v: f"Nível de atividade: {v}",
            "kcal_recomendadas": lambda v: f"Meta calórica diária: {v} kcal",
        }
        linhas_perfil = [fmt(perfil[k]) for k, fmt in campos_perfil.items() if k in perfil and perfil[k] is not None]
        if linhas_perfil:
            blocos.append("=== PERFIL DO USUÁRIO ===\n" + "\n".join(linhas_perfil))

    historico = saude.get("historico_nutricional") or []
    if historico:
        linhas_hist: list[str] = ["=== HISTÓRICO NUTRICIONAL ==="]
        for dia in historico:
            data           = dia.get("data", "?")
            kcal_total     = dia.get("kcal_total", 0)
            proteinas      = dia.get("proteinas_g", 0)
            carboidratos   = dia.get("carboidratos_g", 0)
            gorduras       = dia.get("gorduras_g", 0)
            kcal_meta      = (saude.get("perfil") or {}).get("kcal_recomendadas")

            saldo = ""
            if kcal_meta:
                diferenca = kcal_total - kcal_meta
                saldo = f" | saldo: {diferenca:+.0f} kcal vs meta"

            linhas_hist.append(
                f"{data}"
                f"Totais → {kcal_total:.0f} kcal{saldo}"
                f" | Prot: {proteinas:.1f}g | Carbo: {carboidratos:.1f}g | Gord: {gorduras:.1f}g"
            )

            refeicoes = dia.get("refeicoes") or []
            for refeicao in refeicoes:
                hora      = refeicao.get("hora", "?")
                alimentos = refeicao.get("alimentos") or []
                if not alimentos:
                    continue

                linhas_hist.append(f"   🕐 {hora}")
                for alimento in alimentos:
                    nome         = alimento.get("nome", "?")
                    qtd          = alimento.get("quantidade_g", 0)
                    kcal         = alimento.get("kcal", 0)
                    prot         = alimento.get("proteinas_g", 0)
                    carbo        = alimento.get("carboidratos_g", 0)
                    gord         = alimento.get("gorduras_g", 0)
                    linhas_hist.append(
                        f"      • {nome} ({qtd:.0f}g)"
                        f" → {kcal:.0f} kcal | Prot: {prot:.1f}g | Carbo: {carbo:.1f}g | Gord: {gord:.1f}g"
                    )

        blocos.append("\n".join(linhas_hist))

    return "\n\n".join(blocos)



def responder_megumi(
        texto:     str,
        contexto:  str               = "",
        historico: list[dict] | None = None,
        saude_json: dict | None      = None,
) -> str | None:
    contents: list[types.Content] = [
        types.Content(
            role  = "user" if msg["papel"] == "user" else "model",
            parts = [types.Part(text=msg["mensagem"])],
        )
        for msg in (historico or [])
    ]

    partes_ctx  = [p for p in [contexto, _formatar_saude(saude_json) if saude_json else ""] if p]
    texto_turno = f"{texto}\n\n{chr(10).join(partes_ctx)}".strip()
    contents.append(types.Content(role="user", parts=[types.Part(text=texto_turno)]))

    log.info(
        f"[MEGUMI] texto={texto!r} taco={contexto or '(vazio)'} "
        f"saúde={'sim' if saude_json else 'não'} "
        f"histórico={len(historico or [])} msgs"
    )

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
        return "Tive um problemão aqui, tente novamente."