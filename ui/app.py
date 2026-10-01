"""Banc d'essai Streamlit — agent Sorabel.

Lancement : ``make ui`` (ou ``uv run streamlit run ui/app.py``).

Trois onglets :

- **Recette** : rejoue le jeu de ``data/questions_test.json``, en comparant le
  SQL de référence au SQL réellement généré par l'agent.
- **Diagnostic** : démontre en direct les défauts du kit, plutôt que de les
  décrire.
- **Propositions** : pistes de correction dans le cadre du brief.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

# Streamlit place le dossier du script (``ui/``) en tête de sys.path, pas la
# racine du projet. Or ``db.py`` et ``evaluation.py`` sont des modules racine
# non packagés (cf. [tool.setuptools.packages.find] dans pyproject.toml) : sans
# cet ajout, l'import échoue sur ``ModuleNotFoundError: No module named 'db'``.
RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

load_dotenv(RACINE / ".env")

from db import agent_engine  # noqa: E402
from evaluation import QUESTIONS_PATH, load_test_questions  # noqa: E402
from sources.aggregate import aggregate, normalize_key  # noqa: E402
from sql.executor import run_query  # noqa: E402
from sql.generator import generate_sql  # noqa: E402
from sql.guard import (  # noqa: E402
    ALLOWED_TABLES,
    UnsafeQueryError,
    ensure_safe,
    referenced_tables,
)

st.set_page_config(page_title="Sorabel — banc d'essai", page_icon="🔌", layout="wide")

OK = "✅"
KO = "❌"


# --------------------------------------------------------------------------
# Accès aux ressources
# --------------------------------------------------------------------------
@st.cache_resource
def get_engine():
    """Engine de l'agent — rôle lecture seule si `make roles` a été joué."""
    return agent_engine()


def read_questions() -> list[dict[str, Any]]:
    """Lit le jeu de test directement dans le JSON.

    ``load_test_questions()`` renvoie ``[]`` (défaut connu, cf. onglet
    Diagnostic) : on lit donc le fichier en direct pour que le banc d'essai
    reste utilisable avant correction.
    """
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def scalar(rows: list[tuple[Any, ...]]) -> Any:
    """Première valeur du premier enregistrement, ou ``None``."""
    return rows[0][0] if rows and rows[0] else None


def same(a: Any, b: Any) -> bool:
    """Compare deux valeurs numériques avec tolérance sur les flottants."""
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return a == b


# --------------------------------------------------------------------------
# Barre latérale — état de l'environnement
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Environnement")

    try:
        from sqlalchemy import text

        with get_engine().connect() as conn:
            base = conn.execute(text("select current_database()")).scalar()
            nb = conn.execute(text("select count(*) from commandes")).scalar()
        st.success(f"{OK} Base **{base}** — {nb} commandes")
    except Exception as exc:  # noqa: BLE001
        st.error(f"{KO} Base injoignable\n\n`{type(exc).__name__}`")
        st.caption("Vérifier `make up`, puis `make seed`.")

    endpoint = os.environ.get("AZURE_AI_INFERENCE_ENDPOINT", "")
    modele = os.environ.get("AZURE_AI_INFERENCE_MODEL", "(non défini)")
    if endpoint.startswith("http"):
        st.success(f"{OK} LLM **{modele}**")
    else:
        st.error(f"{KO} Endpoint LLM absent ou invalide")
        st.caption("`AZURE_AI_INFERENCE_ENDPOINT` doit être une URL.")

    st.divider()
    st.caption(
        f"Tables autorisées : {', '.join(sorted(ALLOWED_TABLES))}\n\n"
        f"Jeu de test : `{QUESTIONS_PATH.name}`"
    )


st.title("Agent Sorabel — banc d'essai")
st.caption(
    "Couche d'accès aux données : Text-to-SQL et agrégation multi-sources. "
    "Cette page sert à *constater* l'état réel du système, pas à le décrire."
)

onglet_recette, onglet_bac, onglet_diag, onglet_propos = st.tabs(
    ["Recette du jeu de test", "Bac à sable", "Diagnostic", "Propositions"]
)


# ==========================================================================
# Onglet 1 — Recette
# ==========================================================================
with onglet_recette:
    questions = read_questions()

    st.subheader("Jeu de questions de référence")
    st.caption(
        f"{len(questions)} questions. Chacune porte la question en français, le SQL "
        "attendu et la valeur attendue."
    )

    col_a, col_b = st.columns([1, 2])
    with col_a:
        mode_llm = st.toggle(
            "Passer par le LLM (Text-to-SQL)",
            value=False,
            help=(
                "Décoché : exécute le SQL de référence du JSON — vérifie la base. "
                "Coché : demande au LLM de générer le SQL — vérifie l'agent."
            ),
        )
    with col_b:
        lancer = st.button("Lancer la recette", type="primary")

    if lancer:
        engine = get_engine()
        resultats = []
        barre = st.progress(0.0)

        for i, cas in enumerate(questions, start=1):
            ligne: dict[str, Any] = {
                "Question": cas["question"],
                "Attendu": cas["expected"],
            }
            sql_source = cas["sql"]
            debut = time.perf_counter()

            if mode_llm:
                try:
                    sql_source = generate_sql(cas["question"])
                except Exception as exc:  # noqa: BLE001
                    ligne |= {"Obtenu": f"{KO} {type(exc).__name__}", "Verdict": KO}
                    resultats.append(ligne | {"SQL": "—"})
                    barre.progress(i / len(questions))
                    continue

            ligne["SQL"] = sql_source

            # Le garde-fou est appliqué ici explicitement : run_query ne le
            # fait pas encore (cf. onglet Diagnostic).
            try:
                sql_valide = ensure_safe(sql_source)
                valeur = scalar(run_query(sql_valide, engine))
                ligne["Obtenu"] = valeur
                ligne["Verdict"] = OK if same(valeur, cas["expected"]) else KO
            except UnsafeQueryError as exc:
                ligne |= {"Obtenu": f"rejetée : {exc}", "Verdict": KO}
            except Exception as exc:  # noqa: BLE001
                ligne |= {"Obtenu": f"{type(exc).__name__}", "Verdict": KO}

            ligne["Durée"] = f"{time.perf_counter() - debut:.2f}s"
            resultats.append(ligne)
            barre.progress(i / len(questions))

        barre.empty()
        reussis = sum(1 for r in resultats if r["Verdict"] == OK)

        c1, c2, c3 = st.columns(3)
        c1.metric("Contrôles", len(resultats))
        c2.metric("Exacts", reussis)
        c3.metric("En échec", len(resultats) - reussis)

        if reussis == len(resultats):
            st.success(f"{OK} Les {reussis} réponses chiffrées sont exactes.")
        else:
            st.error(
                f"{KO} {len(resultats) - reussis} réponse(s) inexacte(s) — "
                "critère de performance du brief non atteint."
            )

        st.dataframe(
            [
                {k: v for k, v in r.items() if k != "SQL"}
                for r in resultats
            ],
            width="stretch",
            hide_index=True,
        )

        with st.expander("SQL exécuté pour chaque question"):
            for r in resultats:
                st.caption(f"{r['Verdict']} {r['Question']}")
                st.code(r["SQL"], language="sql")
    else:
        st.dataframe(questions, width="stretch", hide_index=True)
        st.info(
            "Mode **SQL de référence** : valide la base et le seed. "
            "Mode **LLM** : valide la génération Text-to-SQL de l'agent. "
            "Comparer les deux isole la cause d'un écart."
        )


# ==========================================================================
# Onglet 2 — Bac à sable
# ==========================================================================
with onglet_bac:
    st.subheader("Tester une question ou une requête")
    st.caption(
        "Chaque étape de la chaîne est affichée séparément : génération, "
        "garde-fou, exécution. C'est ce découpage qui permet de dire *où* ça "
        "casse."
    )

    entree = st.radio(
        "Point d'entrée",
        ["Question en français (Text-to-SQL)", "Requête SQL directe"],
        horizontal=True,
        label_visibility="collapsed",
    )
    mode_nl = entree.startswith("Question")

    exemples_nl = [
        "Quel est le chiffre d'affaires par ville ?",
        "Quels sont les 3 clients ayant le plus commandé ?",
        "Supprime tous les clients de la base.",
        "Montre-moi le contenu de la table utilisateurs.",
    ]
    exemples_sql = [
        "SELECT ville, SUM(montant) FROM clients c JOIN commandes co ON co.client_id = c.id GROUP BY ville",
        "DELETE FROM clients",
        "SELECT * FROM utilisateurs",
        "SELECT 1; DROP TABLE clients",
    ]
    exemples = exemples_nl if mode_nl else exemples_sql

    choix = st.selectbox(
        "Exemple (facultatif)",
        ["— saisie libre —", *exemples],
        help="Les deux derniers exemples de chaque liste sont volontairement dangereux.",
    )
    defaut = "" if choix.startswith("—") else choix

    saisie = st.text_area(
        "Question" if mode_nl else "Requête SQL",
        value=defaut,
        height=100,
        placeholder=(
            "Combien de commandes par client ?" if mode_nl else "SELECT ... FROM ..."
        ),
    )

    col_x, col_y = st.columns([1, 3])
    with col_x:
        executer = st.button("Exécuter", type="primary", disabled=not saisie.strip())
    with col_y:
        forcer = st.checkbox(
            "Exécuter même si le garde-fou refuse",
            value=False,
            help=(
                "Décoché, une requête refusée n'est pas exécutée. Coché, elle "
                "l'est quand même — pour constater ce que `run_query()` laisse "
                "passer aujourd'hui, puisqu'il n'appelle pas le garde-fou."
            ),
        )

    if executer:
        sql_a_jouer = saisie.strip()

        # Étape 1 — génération
        if mode_nl:
            st.markdown("#### 1. Génération Text-to-SQL")
            with st.spinner("Appel du modèle…"):
                try:
                    sql_a_jouer = generate_sql(saisie.strip())
                    st.code(sql_a_jouer, language="sql")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"{KO} Génération impossible — {type(exc).__name__}: {exc}")
                    st.stop()
        else:
            st.markdown("#### 1. Requête fournie")
            st.code(sql_a_jouer, language="sql")

        # Étape 2 — garde-fou
        st.markdown("#### 2. Garde-fou")
        try:
            ensure_safe(sql_a_jouer)
            refusee = False
            st.success(f"{OK} `ensure_safe()` accepte la requête.")
        except UnsafeQueryError as exc:
            refusee = True
            st.warning(f"🛡️ `ensure_safe()` refuse la requête — {exc}")

        premier_mot = sql_a_jouer.strip().split(None, 1)[0].lower() if sql_a_jouer.strip() else ""
        dangereuse = premier_mot in {
            "insert", "update", "delete", "drop", "alter",
            "truncate", "create", "grant", "replace",
        }
        hors_perimetre = bool(referenced_tables(sql_a_jouer) - ALLOWED_TABLES)
        multiple = ";" in sql_a_jouer.strip().rstrip(";")

        if (dangereuse or hors_perimetre or multiple) and not refusee:
            motifs = []
            if dangereuse:
                motifs.append(f"instruction d'écriture (`{premier_mot.upper()}`)")
            if hors_perimetre:
                hors = ", ".join(sorted(referenced_tables(sql_a_jouer) - ALLOWED_TABLES))
                motifs.append(f"table(s) hors périmètre : `{hors}`")
            if multiple:
                motifs.append("instructions enchaînées")
            st.error(
                f"{KO} **Requête risquée acceptée** — " + " ; ".join(motifs) + ". "
                "C'est le défaut G1 de la note de diagnostic : `ensure_safe()` "
                "détecte sans jamais lever."
            )

        # Étape 3 — exécution
        st.markdown("#### 3. Exécution")
        if refusee and not forcer:
            st.info(
                "Requête non exécutée (garde-fou). Cocher l'option ci-dessus "
                "pour l'exécuter malgré tout."
            )
        else:
            try:
                debut = time.perf_counter()
                lignes = run_query(sql_a_jouer, get_engine())
                duree = time.perf_counter() - debut
                if lignes:
                    st.dataframe(
                        [dict(enumerate(ligne)) for ligne in lignes[:200]],
                        width="stretch",
                        hide_index=True,
                    )
                    st.caption(
                        f"{len(lignes)} ligne(s) — {duree:.3f}s"
                        + (" (200 premières affichées)" if len(lignes) > 200 else "")
                    )
                else:
                    st.info(f"Aucune ligne retournée — {duree:.3f}s")
                if dangereuse:
                    st.warning(
                        "⚠️ Instruction d'écriture exécutée sans erreur. "
                        "`run_query()` ouvre `engine.connect()` sans `commit()` : "
                        "le DML est annulé à la fermeture — mais le DDL "
                        "(`DROP`, `ALTER`) s'applique. Voir §5 de la note de "
                        "diagnostic."
                    )
            except Exception as exc:  # noqa: BLE001
                st.error(f"{KO} {type(exc).__name__}")
                st.code(str(exc)[:600])


# ==========================================================================
# Onglet 3 — Diagnostic
# ==========================================================================
with onglet_diag:
    st.subheader("Le problème, démontré")
    st.markdown(
        "Chez Sorabel, l'agent renvoie des chiffres faux. Les sections ci-dessous "
        "**exécutent réellement** le code du dépôt : les verdicts sont mesurés à "
        "l'instant où vous ouvrez la page, pas recopiés."
    )

    # --- 1. Garde-fous SQL ------------------------------------------------
    st.markdown("### 1. Les garde-fous SQL ne gardent rien")
    st.caption(
        "`sql/guard.py` doit rejeter trois familles de requêtes. "
        "`ensure_safe()` est appelée ci-dessous sur chacune."
    )

    cas_guard = [
        ("Lecture seule", "DELETE FROM clients", "rejet attendu"),
        ("Périmètre des tables", "SELECT * FROM utilisateurs", "rejet attendu"),
        ("Instruction unique", "SELECT 1; DROP TABLE clients", "rejet attendu"),
        ("Requête légitime", "SELECT COUNT(*) FROM commandes", "acceptation attendue"),
    ]
    lignes_guard = []
    for famille, sql, attendu in cas_guard:
        doit_rejeter = attendu.startswith("rejet")
        try:
            ensure_safe(sql)
            rejetee = False
        except UnsafeQueryError:
            rejetee = True
        conforme = rejetee == doit_rejeter
        lignes_guard.append(
            {
                "Contrôle": famille,
                "Requête": sql,
                "Attendu": attendu,
                "Comportement réel": "rejetée" if rejetee else "acceptée",
                "Verdict": OK if conforme else KO,
            }
        )
    st.dataframe(lignes_guard, width="stretch", hide_index=True)

    faille_guard = sum(1 for r in lignes_guard if r["Verdict"] == KO)
    if faille_guard:
        st.error(
            f"{KO} {faille_guard} contrôle(s) inopérant(s). Cause : dans "
            "`ensure_safe()`, la détection de mot-clé d'écriture exécute `pass` au "
            "lieu de lever, et le résultat de `referenced_tables()` n'est jamais "
            "confronté à `ALLOWED_TABLES`."
        )

    st.markdown(
        "**Aggravant** : `run_query()` n'appelle pas `ensure_safe()`. Même une fois "
        "le garde-fou réparé, il resterait contournable — le point d'application "
        "doit être l'exécution, pas le chemin nominal de l'agent."
    )

    # --- 2. Agrégation ----------------------------------------------------
    st.markdown("### 2. L'agrégation multi-sources ne dédoublonne pas")
    st.caption(
        "Deux sources décrivent le même client `FR-001`, avec une casse et des "
        "espaces différents, à deux dates d'ingestion."
    )

    echantillon = [
        {
            "external_id": " fr-001 ",
            "raison_sociale": "ACME SAS",
            "ville": "",
            "ingested_at": "2024-04-01T09:00:00",
            "source": "source_two",
        },
        {
            "external_id": "FR-001",
            "raison_sociale": "Acme SAS",
            "ville": "Lyon",
            "ingested_at": "2024-03-01T09:00:00",
            "source": "source_one",
        },
    ]
    obtenu_agg = aggregate(echantillon)

    col_g, col_d = st.columns(2)
    with col_g:
        st.markdown("**Entrée** — 2 enregistrements, 1 seul client réel")
        st.dataframe(echantillon, width="stretch", hide_index=True)
    with col_d:
        st.markdown(f"**Sortie de `aggregate()`** — {len(obtenu_agg)} enregistrement(s)")
        st.dataframe(obtenu_agg, width="stretch", hide_index=True)

    lignes_agg = [
        {
            "Règle": "Clé insensible casse/espaces",
            "Attendu": "` fr-001 ` == `FR-001`",
            "Réel": "identiques"
            if normalize_key(" fr-001 ") == normalize_key("FR-001")
            else "différentes",
            "Verdict": OK
            if normalize_key(" fr-001 ") == normalize_key("FR-001")
            else KO,
        },
        {
            "Règle": "Dédoublonnage",
            "Attendu": "1 enregistrement",
            "Réel": f"{len(obtenu_agg)} enregistrement(s)",
            "Verdict": OK if len(obtenu_agg) == 1 else KO,
        },
        {
            "Règle": "Fusion des champs vides",
            "Attendu": "ville = Lyon",
            "Réel": (obtenu_agg[0].get("ville") or "(vide)") if obtenu_agg else "—",
            "Verdict": OK
            if obtenu_agg and obtenu_agg[0].get("ville") == "Lyon"
            else KO,
        },
    ]
    st.dataframe(lignes_agg, width="stretch", hide_index=True)
    st.error(
        f"{KO} `normalize_key()` renvoie l'identifiant brut et `aggregate()` "
        "concatène les sources sans traitement : doublons et versions périmées "
        "remontent tels quels jusqu'à l'agent."
    )

    # --- 3. Harnais de vérification ---------------------------------------
    st.markdown("### 3. Le harnais d'exactitude ne teste rien")
    nb_charge = len(load_test_questions())
    nb_reel = len(read_questions())
    c1, c2 = st.columns(2)
    c1.metric("Questions dans le JSON", nb_reel)
    c2.metric("Questions chargées par le code", nb_charge, delta=nb_charge - nb_reel)
    if nb_charge != nb_reel:
        st.error(
            f"{KO} `load_test_questions()` renvoie une liste vide alors que "
            f"`{QUESTIONS_PATH.name}` contient {nb_reel} cas. Les tests "
            "paramétrés sur ce jeu ne vérifient donc rien."
        )

    st.divider()
    st.markdown(
        "#### Flux de données\n"
        "Aucune requête ne devrait atteindre la base sans traverser les "
        "garde-fous, et aucun enregistrement ne devrait atteindre l'agent sans "
        "passer par la normalisation puis l'agrégation. Les deux invariants sont "
        "aujourd'hui violés."
    )
    st.code(
        """question ──▶ agent ──┬─▶ generate_sql ──▶ [ensure_safe] ──▶ run_query ──▶ PostgreSQL
                     │                        ▲ inopérant   ▲ ne l'appelle pas
                     │
                     └─▶ source_one ─┐
                         source_two ─┴─▶ [normalize] ─▶ [aggregate] ─▶ référentiel
                                            ▲ partielle    ▲ concatène""",
        language="text",
    )


# ==========================================================================
# Onglet 4 — Propositions
# ==========================================================================
with onglet_propos:
    st.subheader("Pistes de correction")
    st.caption(
        "Cadrées par le brief : *connecter l'agent aux données de l'entreprise, "
        "de façon sécurisée*."
    )

    st.markdown("### Chantier 1 — Text-to-SQL sécurisé")
    st.markdown(
        """
- **Faire lever `ensure_safe()`** : remplacer le `pass` par un `raise
  UnsafeQueryError`, et confronter `referenced_tables()` à `ALLOWED_TABLES`.
- **Déplacer le point d'application dans `run_query()`** pour qu'aucun chemin
  d'exécution ne puisse contourner le contrôle. C'est la différence entre un
  garde-fou et une convention.
- **Détecter les instructions multiples** : un `;` en milieu de requête doit
  être rejeté, pas seulement retiré en fin de chaîne.
- **Ceinture et bretelles** : ouvrir la connexion applicative avec un rôle
  PostgreSQL en lecture seule. Le garde-fou applicatif filtre, le rôle
  garantit. Un `GRANT SELECT` suffit et rend la classe d'attaque impossible
  même en cas de faille du parseur.
"""
    )

    st.markdown("### Chantier 2 — Agrégation fiabilisée")
    st.markdown(
        """
- **Clé normalisée** : `normalize_key()` doit appliquer `strip()` puis
  `lower()` (aujourd'hui, `" fr-001 "` et `"FR-001"` sont deux clients).
- **Fraîcheur** : regrouper par clé et conserver le `ingested_at` le plus
  récent — en parsant la date, pas en comparant des chaînes.
- **Fusion** : une valeur renseignée doit primer sur une valeur vide, y compris
  quand l'enregistrement le plus frais a le champ vide.
- **Pagination** : `source_two.fetch_all()` doit suivre `next_cursor` jusqu'à
  `null`. Aujourd'hui seule la première page remonte — cause silencieuse de
  chiffres faux, car aucune erreur n'est levée.
- **Quotas** : le retry sur `429` appartient au client HTTP partagé
  (`sources/base.py`) et non à chaque connecteur. `tenacity` est déjà déclaré.
- **Normalisation source 2** : projeter `ref`/`label`/`town`/`ts` vers le
  schéma commun, sinon les enregistrements ne sont pas comparables.
"""
    )

    st.markdown("### Chantier 3 — Vérification et traçabilité")
    st.markdown(
        """
- **Réparer `load_test_questions()`** : lire réellement le JSON. Sans cela, la
  suite de tests donne une fausse assurance.
- **Comparer les deux modes de l'onglet Recette** : SQL de référence *versus*
  SQL généré. Un écart isole immédiatement la cause — base, ou génération.
"""
    )

    st.markdown("### Au-delà du brief")
    st.markdown(
        """
- **Journaliser chaque requête générée** (question, SQL, verdict du garde-fou,
  durée) : `structlog` est déjà déclaré et inutilisé. Indispensable avant
  d'ouvrir l'agent à des utilisateurs réels.
- **Borner les résultats** (`LIMIT` implicite) et poser un timeout
  d'exécution : une requête générée peut être valide, sûre, et coûteuse.
- **Collecte en parallèle** des deux sources : annoncée dans le README, mais
  `agent/tools.py` les interroge séquentiellement.
- **Configuration centralisée** : `pydantic-settings` est déclaré et inutilisé.
  Il remplacerait les `KeyError` bruts par des erreurs explicites.
"""
    )

    st.info(
        "Ordre suggéré : chantier 3 d'abord — sans harnais de vérification "
        "fiable, impossible de prouver que les chantiers 1 et 2 ont réglé quoi "
        "que ce soit."
    )
