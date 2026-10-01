"""Génération de requêtes SQL à partir de questions en langage naturel.

Le schéma envoyé au LLM est **introspecté depuis la base** plutôt qu'écrit en
dur : ``information_schema`` reflète l'état réel des tables, là où une
description figée dérive au premier ``ALTER TABLE`` ou à la première migration
appliquée hors SQLAlchemy.

L'introspection a lieu **côté application**, au moment de construire le prompt.
L'agent n'interroge jamais ``information_schema`` lui-même : le catalogue reste
hors de son périmètre SQL (cf. note de conception §3.2).

Le résultat est mis en cache : le schéma ne change pas entre deux questions.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine

from sql.guard import ALLOWED_TABLES


class ModeleChat(Protocol):
    """Contrat minimal attendu d'un modèle de chat.

    Décrit ce que ``generate_sql`` utilise réellement, sans dépendre d'une
    implémentation : tout objet exposant ``invoke`` convient, y compris un
    faux modèle en test.
    """

    def invoke(self, entree: Any, /) -> Any: ...

# Utilisée si la base est injoignable — l'agent doit pouvoir échouer
# proprement plutôt que de ne pas démarrer.
SCHEMA_DE_SECOURS = """Tables disponibles (base Sorabel) :
- clients(id, raison_sociale, ville, actif)
- produits(id, libelle, prix_unitaire)
- commandes(id, client_id, date_commande, montant)
- lignes_commande(id, commande_id, produit_id, quantite)
"""

_INTROSPECTION = text(
    """
    SELECT table_name, column_name, data_type
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = ANY(:tables)
     ORDER BY table_name, ordinal_position
    """
)

_cache: dict[str, str] = {}


def describe_schema(engine: Engine, *, rafraichir: bool = False) -> str:
    """Décrit les tables autorisées d'après l'état réel de la base.

    Le périmètre est doublement borné : par ``ALLOWED_TABLES`` dans la requête,
    et par les privilèges du rôle — ``information_schema`` ne montre que les
    objets accessibles à l'appelant.
    """
    cle = str(engine.url)
    if not rafraichir and cle in _cache:
        return _cache[cle]

    colonnes: dict[str, list[str]] = {}
    with engine.connect() as conn:
        for table, colonne, type_sql in conn.execute(
            _INTROSPECTION, {"tables": sorted(ALLOWED_TABLES)}
        ):
            colonnes.setdefault(table, []).append(f"{colonne} {type_sql}")

    if not colonnes:
        raise RuntimeError(
            "Aucune table du périmètre n'est visible : base non alimentée "
            "(`make seed`) ou droits insuffisants sur le rôle."
        )

    lignes = [f"- {t}({', '.join(cols)})" for t, cols in sorted(colonnes.items())]
    description = "Tables disponibles (base Sorabel) :\n" + "\n".join(lignes) + "\n"
    _cache[cle] = description
    return description


def build_prompt(question: str, schema: str) -> str:
    """Assemble le prompt envoyé au LLM pour une question donnée."""
    return (
        "Tu traduis une question en une requête SQL PostgreSQL.\n\n"
        f"{schema}\n"
        "Réponds uniquement par la requête SQL, sans commentaire ni texte "
        "autour.\n\n"
        f"Question : {question}\nSQL :"
    )


def generate_sql(
    question: str,
    llm: ModeleChat | None = None,
    engine: Engine | None = None,
) -> str:
    """Génère une requête SQL pour ``question``."""
    if llm is None:
        from agent.llm import get_llm

        llm = get_llm()

    if engine is None:
        from db import agent_engine

        engine = agent_engine()

    try:
        schema = describe_schema(engine)
    except Exception:  # noqa: BLE001 — base injoignable : on dégrade, sans bloquer
        schema = SCHEMA_DE_SECOURS

    message = llm.invoke(build_prompt(question, schema))
    contenu = getattr(message, "content", message)
    return str(contenu).strip().strip("`").removeprefix("sql").strip()
