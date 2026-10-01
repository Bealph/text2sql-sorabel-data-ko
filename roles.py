"""Crée le rôle PostgreSQL en lecture seule utilisé par l'agent.

Défense en profondeur (note de conception §5) : le garde-fou applicatif
*filtre*, le rôle *garantit*. Même en cas de faille du parseur SQL, l'écriture
devient impossible au niveau du moteur.

Deux connexions coexistent :

- ``DB_URL``       — rôle propriétaire, utilisé par ``seed.py`` (écriture)
- ``AGENT_DB_URL`` — rôle ``sorabel_agent``, utilisé par l'agent (lecture seule)

Le périmètre du rôle reflète ``ALLOWED_TABLES`` : les droits sont accordés
table par table, jamais via ``ALL TABLES``. Une table ajoutée plus tard
(``utilisateurs``, journaux…) reste donc inaccessible par défaut.

Usage : ``make roles`` — après ``make seed``, car les ``GRANT`` portent sur des
tables qui doivent exister.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import text

from db import engine_from_env
from sql.guard import ALLOWED_TABLES

ROLE = "sorabel_agent"
MOT_DE_PASSE = os.environ.get("AGENT_DB_PASSWORD", "sorabel_agent")


def main() -> None:
    load_dotenv()
    engine = engine_from_env("DB_URL")
    tables = ", ".join(sorted(ALLOWED_TABLES))

    with engine.begin() as conn:
        base = conn.execute(text("select current_database()")).scalar()

        # Idempotent : relancer le script ne doit pas échouer.
        conn.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN
                        CREATE ROLE {ROLE} LOGIN PASSWORD '{MOT_DE_PASSE}';
                    END IF;
                END
                $$;
                """
            )
        )

        # Repartir d'un état vierge : le script fait autorité sur les droits.
        conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}"))
        conn.execute(text(f"REVOKE ALL ON SCHEMA public FROM {ROLE}"))

        conn.execute(text(f'GRANT CONNECT ON DATABASE "{base}" TO {ROLE}'))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROLE}"))
        conn.execute(text(f"GRANT SELECT ON {tables} TO {ROLE}"))

        # USAGE seul ne permet pas de créer d'objets ; on l'explicite.
        conn.execute(text(f"REVOKE CREATE ON SCHEMA public FROM {ROLE}"))

    print(f"Rôle {ROLE} prêt — SELECT sur : {tables}")
    print()
    print("À renseigner dans .env :")
    print(f"  AGENT_DB_URL=postgresql+psycopg://{ROLE}:{MOT_DE_PASSE}"
          f"@localhost:5433/{base}")


if __name__ == "__main__":
    main()
