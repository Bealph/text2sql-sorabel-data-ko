"""Garde-fous appliqués aux requêtes SQL avant exécution.

L'agent génère du SQL à partir de questions en langage naturel. Avant de
toucher la base, une requête doit être :

- composée d'**une seule** instruction (pas d'enchaînement),
- en **lecture seule** (aucune écriture / DDL),
- restreinte au **périmètre** des tables autorisées.

La validation porte sur l'**arbre syntaxique**, pas sur le texte : une
expression régulière ne connaît pas la grammaire SQL et se trompe dans les deux
sens — elle laisse passer ``SELECT * FROM "utilisateurs"`` (guillemets) et
refuse ``SELECT * FROM public.clients`` (schéma qualifié). Voir
``docs/note-conception.md`` §1.

Le point d'application est ``run_query()`` : un garde-fou placé sur le chemin
nominal est une convention, placé à l'exécution c'est une garantie.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

DIALECTE = "postgres"


class UnsafeQueryError(Exception):
    """Levée quand une requête ne respecte pas les garde-fous."""


ALLOWED_TABLES = {"clients", "produits", "commandes", "lignes_commande"}


def _tables_de(arbre: exp.Expression) -> set[str]:
    """Tables **physiques** de l'arbre, alias de CTE exclus.

    ``WITH t AS (SELECT * FROM clients) SELECT * FROM t`` référence la seule
    table ``clients`` : ``t`` est un nom temporaire, pas un objet de la base.
    """
    ctes = {cte.alias_or_name.lower() for cte in arbre.find_all(exp.CTE)}
    return {table.name.lower() for table in arbre.find_all(exp.Table)} - ctes


def referenced_tables(sql: str) -> set[str]:
    """Tables référencées par ``sql``, ou un ensemble vide si non analysable."""
    try:
        arbre = sqlglot.parse_one(sql, dialect=DIALECTE)
    except ParseError:
        return set()
    return _tables_de(arbre) if arbre is not None else set()


def ensure_safe(sql: str) -> str:
    """Renvoie la requête si elle est sûre, sinon lève ``UnsafeQueryError``."""
    statement = sql.strip()
    if not statement:
        raise UnsafeQueryError("requête vide")

    # Ce qui n'est pas analysable n'est pas exécuté : une requête que les
    # garde-fous ne peuvent pas comprendre ne peut pas être déclarée sûre.
    try:
        instructions = [i for i in sqlglot.parse(statement, dialect=DIALECTE) if i]
    except ParseError as exc:
        raise UnsafeQueryError(f"requête non analysable — {exc}") from exc

    # ① Instruction unique — vérifié d'abord : analyser la première instruction
    #    sans avoir compté reviendrait à ignorer silencieusement les suivantes.
    if len(instructions) != 1:
        raise UnsafeQueryError(
            f"instructions multiples refusées ({len(instructions)} détectées)"
        )
    arbre = instructions[0]

    # ② Lecture seule — allowlist : seul SELECT est autorisé. Une denylist de
    #    mots-clés interdits laisserait passer tout ce qu'elle a oublié
    #    (COPY, CALL, MERGE, VACUUM…).
    if not isinstance(arbre, exp.Select):
        recu = type(arbre).__name__.upper()
        raise UnsafeQueryError(
            f"instruction refusée — seules les requêtes SELECT sont "
            f"autorisées (reçu : {recu})"
        )

    # ③ Périmètre — toutes les tables citées doivent être autorisées.
    hors_perimetre = _tables_de(arbre) - ALLOWED_TABLES
    if hors_perimetre:
        raise UnsafeQueryError(
            f"table hors périmètre — {', '.join(sorted(hors_perimetre))}"
        )

    return statement.rstrip(";")
