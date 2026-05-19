from contextlib import contextmanager
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from core.config import PG_DSN

_pool = ThreadedConnectionPool(
    2, 10,
    PG_DSN,
    cursor_factory=psycopg2.extras.RealDictCursor,
)


@contextmanager
def conn():
    c = _pool.getconn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        _pool.putconn(c)


def _build_like_parts(query: str) -> tuple[list[str], list[str]]:
    palavras = [p for p in query.strip().lower().split() if len(p) > 2] or query.split()
    return palavras, [f"%{p}%" for p in palavras]


def upsert_user(username: str, name: str, email: str):
    with conn() as c, c.cursor() as cur:
        cur.execute("""
            INSERT INTO users (username, name, email) VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
        """, (username, name, email))


def salvar_mensagem(username: str, papel: str, mensagem: str):
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_history (username, papel, mensagem) VALUES (%s, %s, %s)",
            (username, papel, mensagem)
        )


def carregar_historico(username: str, limite: int = 20) -> list[dict]:
    with conn() as c, c.cursor() as cur:
        # Como o RealDictCursor já retorna dicionários e filtramos as colunas exatas, retornamos direto
        cur.execute("""
            SELECT papel, mensagem FROM (
                SELECT papel, mensagem, created_at FROM chat_history
                WHERE username = %s ORDER BY created_at DESC LIMIT %s
            ) sub ORDER BY created_at ASC
        """, (username, limite))
        return cur.fetchall()


def buscar_alimento(query: str) -> str:
    if not query or len(query) < 2:
        return ""

    palavras, like_params = _build_like_parts(query)
    n = len(palavras)

    and_clauses = " AND ".join(["lower(a.descricao) LIKE %s"] * n)
    or_clauses  = " OR  ".join(["lower(a.descricao) LIKE %s"] * n)
    count_expr  = " + ".join(["(CASE WHEN lower(a.descricao) LIKE %s THEN 1 ELSE 0 END)"] * n)

    sql = f"""
        SELECT a.descricao,
            COALESCE(MAX(CASE WHEN n.componente = 'Energia..kcal.'    THEN n.valor END), 0)::float AS kcal,
            COALESCE(MAX(CASE WHEN n.componente = 'Proteína..g.'      THEN n.valor END), 0)::float AS protein,
            COALESCE(MAX(CASE WHEN n.componente = 'Carboidrato..g.'   THEN n.valor END), 0)::float AS carbs,
            COALESCE(MAX(CASE WHEN n.componente = 'Lipídeos..g.'      THEN n.valor END), 0)::float AS fat,
            ({count_expr}) AS word_score,
            similarity(lower(a.descricao), %s) AS sim_score
        FROM alimento a
        LEFT JOIN nutriente n ON n.codigo_alimento = a.codigo
        WHERE ({and_clauses}) OR ({or_clauses}) OR similarity(lower(a.descricao), %s) > 0.2
        GROUP BY a.codigo, a.descricao
        ORDER BY word_score DESC, sim_score DESC, length(a.descricao)
        LIMIT 1
    """
    params = like_params + [query] + like_params + like_params + [query]

    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()

    if not row:
        return ""

    return (
        f"[Dados NutriEngine – {row['descricao']}]: "
        f"Proteína: {row['protein']}g, Carboidrato: {row['carbs']}g, "
        f"Gordura: {row['fat']}g, Energia: {row['kcal']} kcal."
    )


def search_food_list(query: str) -> list[dict]:
    if not query:
        return []

    palavras, like_params = _build_like_parts(query)
    n = len(palavras)

    or_clauses = " OR ".join(["lower(a.descricao) LIKE %s"] * n)
    count_expr = " + ".join(["(CASE WHEN lower(a.descricao) LIKE %s THEN 1 ELSE 0 END)"] * n)

    sql = f"""
        SELECT a.codigo AS id, a.descricao AS description, a.classe AS category,
            COALESCE(MAX(CASE WHEN n.componente = 'Energia..kcal.'    THEN n.valor END), 0)::float AS kcal,
            COALESCE(MAX(CASE WHEN n.componente = 'Proteína..g.'      THEN n.valor END), 0)::float AS protein,
            COALESCE(MAX(CASE WHEN n.componente = 'Carboidrato..g.'   THEN n.valor END), 0)::float AS carbs,
            COALESCE(MAX(CASE WHEN n.componente = 'Lipídeos..g.'      THEN n.valor END), 0)::float AS fat,
            ({count_expr}) AS word_score,
            similarity(lower(a.descricao), %s) AS sim_score
        FROM alimento a
        LEFT JOIN nutriente n ON n.codigo_alimento = a.codigo
        WHERE ({or_clauses}) OR similarity(lower(a.descricao), %s) > 0.2
        GROUP BY a.codigo, a.descricao, a.classe
        ORDER BY word_score DESC, sim_score DESC, length(a.descricao)
        LIMIT 10
    """
    params = like_params + [query] + like_params + [query]

    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "id": r["id"],
            "description": r["description"],
            "category": r["category"],
            "macros": {"kcal": r["kcal"], "protein": r["protein"], "carbs": r["carbs"], "fat": r["fat"]}
        }
        for r in rows
    ]


def listar_parceiros() -> list[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute("""
            SELECT id::text, nome, COALESCE(logo_url, '') AS logo_url, COALESCE(site_url, '') AS site_url
            FROM parceiros WHERE ativo = true ORDER BY nome
        """)
        return cur.fetchall()


def listar_produtos_ativos() -> list[dict]:
    with conn() as c, c.cursor() as cur:
        # Tratamos todos os floats, nulos e fallbacks direto no banco de dados de uma vez só
        cur.execute("""
            SELECT
                p.id, p.nome, COALESCE(p.marca, '') AS marca,
                COALESCE(p.imagem_url, '') AS imagem_url, 
                p.preco_atual::float, p.preco_antigo::float,
                COALESCE(p.quantidade_g, 0)::float AS quantidade_g, 
                p.url_compra, COALESCE(p.categoria, '') AS categoria,
                COALESCE(p.kcal, 0)::float AS kcal, 
                COALESCE(p.proteinas, 0)::float AS proteinas, 
                COALESCE(p.carboidratos, 0)::float AS carboidratos, 
                COALESCE(p.gorduras, 0)::float AS gorduras,
                pa.nome AS nome_mercado, COALESCE(pa.logo_url, '') AS logo_mercado
            FROM produtos p
            JOIN parceiros pa ON pa.id = p.parceiro_id
            WHERE p.ativo = true AND pa.ativo = true
            ORDER BY p.categoria, p.nome
        """)
        return cur.fetchall()


def buscar_ultimo_insight(username: str) -> dict | None:
    sql = """
        SELECT insight, created_at FROM user_insights 
        WHERE username = %s ORDER BY created_at DESC LIMIT 1
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, (username,))
        return cur.fetchone()


def salvar_insight(username: str, insight: str):
    with conn() as c, c.cursor() as cur:
        cur.execute("INSERT INTO user_insights (username, insight) VALUES (%s, %s)", (username, insight))