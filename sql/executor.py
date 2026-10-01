"""Exécution des requêtes SQL sur la base de démonstration.

Point d'application unique des garde-fous : **aucun** appelant — outil de
l'agent, script, test, développement futur — ne peut atteindre la base sans
passer par ``ensure_safe()``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from sql.guard import ensure_safe


def run_query(sql: str, engine: Engine) -> list[tuple[Any, ...]]:
    """Valide puis exécute ``sql``, et renvoie les lignes résultantes.

    Lève ``UnsafeQueryError`` si la requête ne respecte pas les garde-fous —
    la base n'est alors pas sollicitée.
    """
    sql = ensure_safe(sql)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        if result.returns_rows:
            return [tuple(row) for row in result.fetchall()]
        return []
