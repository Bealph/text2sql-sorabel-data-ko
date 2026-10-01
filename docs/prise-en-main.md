# Prise en main et présentation — Sorabel

> [README](../README.md) · [Présentation](presentation.md) · [Diagnostic](note-diagnostic.md) · [Conception](note-conception.md) · **Prise en main** · [Journal](../JOURNAL.md) · [Brief](../brief-agent-text-to-sql.md)

Deux publics, deux usages : **Alpha** reprend le code, **Mehdi et Alpha**
présentent le travail. Les deux parties sont indépendantes.

---

# Partie 1 — Prise en main (Alpha)

## Installation — 10 min

```bash
git clone https://github.com/M-CHADLI/text2sql-sorabel-data-ko.git
cd text2sql-sorabel-data-ko
git checkout diagnostic-et-banc-essai

make install                 # uv sync — uv.lock versionné, versions identiques
cp .env.example .env         # puis renseigner AZURE_AI_INFERENCE_*
make up                      # postgres (5433) + 2 sources mock (8011, 8012)
make seed                    # alimente la base
make roles                   # crée le rôle lecture seule de l'agent
make test                    # doit afficher 20 passed
```

**Points d'attention**

| Symptôme | Cause |
|---|---|
| `port 5432 already allocated` | un autre Postgres tourne. Le projet publie sur **5433** ; adapter si besoin dans `docker-compose.yml` + `DB_URL` |
| aucune table dans le client SQL | connexion sur la base `postgres` au lieu de **`sorabel`** |
| `Variable d'environnement 'DB_URL' non définie` | `.env` absent — le copier depuis `.env.example` |

Vérifier la base : `docker compose exec -T db psql -U sorabel -d sorabel -f - < recettes/recette_seed.sql`
→ 20 contrôles, tous `OK`.

## Comprendre le projet — 20 min

Dans cet ordre :

1. **[Note de diagnostic](note-diagnostic.md)** — le problème et son schéma de
   flux. Commencer par le [schéma](note-diagnostic.md#1-schéma-du-flux-de-données)
   puis le [relevé adverse](note-diagnostic.md#3-relevé--questions-adverses).
2. **[Note de conception](note-conception.md)** — les décisions et leur
   justification : [pourquoi un parseur](note-conception.md#1-pourquoi-réparer-lexistant-ne-suffit-pas),
   [les trois contrôles](note-conception.md#3-les-trois-contrôles).
3. **`make ui`** → http://localhost:8501 — voir le système tourner.
4. **[JOURNAL.md](../JOURNAL.md)** — au besoin, l'historique cause → correctif.

## Le code en 5 fichiers

```
question ──▶ agent/tools.py ──▶ sql/generator.py ──▶ sql/guard.py ──▶ sql/executor.py ──▶ PostgreSQL
                    │
                    └────────▶ sources/{source_one,source_two}.py ──▶ sources/aggregate.py
```

| Fichier | Rôle | À retenir |
|---|---|---|
| `sql/guard.py` | valide le SQL | 3 contrôles sur l'arbre `sqlglot`, **allowlist** : seul `SELECT` |
| `sql/executor.py` | exécute | appelle `ensure_safe()` — point de passage obligé |
| `sql/generator.py` | question → SQL | schéma **introspecté**, pas écrit en dur |
| `sources/aggregate.py` | consolide | clé normalisée, fraîcheur UTC, fusion |
| `roles.py` | rôle lecture seule | défense en profondeur, `make roles` |

## Vérifier qu'on a tout compris — 10 min

Trois manipulations dans `make ui`, onglet **Bac à sable** :

1. Saisir *« Supprime tous les clients »* → le LLM génère `DELETE`, le garde-fou
   le refuse. **Où** le refus se produit-il ? (`sql/guard.py`, contrôle ②)
2. Saisir `WITH t AS (SELECT * FROM clients) SELECT * FROM t` → accepté. Pourquoi
   `t` n'est-il pas vu comme une table hors périmètre ?
3. Saisir `SELECT * FROM information_schema.tables` → refusé. Pourtant le projet
   *lit* `information_schema` : où, et pourquoi n'est-ce pas contradictoire ?

Si ces trois réponses sont claires, le cœur du projet est acquis.

---

# Partie 2 — Présentation (Mehdi et Alpha)

**Durée cible : 15 min + questions.** Le fil conducteur : *le brief décrivait un
symptôme, la mesure a désigné une autre cause*.

## Déroulé

| # | Temps | Séquence |
|---|---|---|
| 1 | 2 min | Le contexte et le symptôme annoncé |
| 2 | 4 min | Le diagnostic — et sa surprise |
| 3 | 3 min | Les décisions de conception |
| 4 | 4 min | Démonstration |
| 5 | 2 min | Résultats et limites |

### 1. Contexte — 2 min

*« Connecter un agent aux données de l'entreprise, sans tout exposer. »* Trois
systèmes : PostgreSQL (commandes), deux applications clients externes. Deux
outils pour l'agent, un par monde.

**Montrer** : le [schéma de flux](note-diagnostic.md#1-schéma-du-flux-de-données)
(§1 de la note de diagnostic).

### 2. Diagnostic — 4 min

Le brief annonce « l'agent renvoie des chiffres faux ». Mesure sur les 4
questions fournies : **4/4 exactes**. Le symptôme n'est pas reproductible par
cette voie.

D'où l'ajout de **8 questions adverses** — le happy path ne peut pas révéler un
risque de sécurité. Résultat : **0/8 bloquées**. Le modèle génère `DELETE`,
`DROP TABLE`, `TRUNCATE` sur simple demande en français.

**Le point à raconter** : 7 requêtes sur 8 n'ont laissé aucune trace, ce qui
ressemblait à une protection. Vérification : `run_query()` ouvrait une
connexion sans jamais committer. Le DML était annulé **par accident**, le DDL
passait. Une protection illusoire, à un `commit()` de disparaître.

**Conclusion du diagnostic** : le Text-to-SQL porte un risque de **sécurité**,
pas d'exactitude. Les chiffres faux viennent de l'**agrégation**.

### 3. Conception — 3 min

Trois décisions, chacune justifiée par une mesure :

| Décision | Pourquoi |
|---|---|
| Valider l'**arbre syntaxique**, pas le texte | la regex laissait passer `FROM "utilisateurs"` et refusait `FROM public.clients` |
| **Allowlist** (seul `SELECT`) au lieu d'une denylist | une liste d'interdits laisse passer ce qu'elle oublie |
| Contrôle dans **`run_query()`** | sur le chemin nominal c'est une convention ; au point d'exécution c'est une garantie |

Plus une **défense en profondeur** : rôle PostgreSQL en lecture seule. Le
garde-fou filtre, le rôle garantit.

### 4. Démonstration — 4 min

`make ui`, dans cet ordre :

1. **Recette**, mode LLM → 4/4 exactes.
2. **Bac à sable** → *« Supprime tous les clients »*. Montrer les trois étapes :
   le SQL généré, le refus du garde-fou, l'absence d'exécution.
3. **Diagnostic** → les verdicts, mesurés au chargement de la page.

Enchaîner avec la campagne, qui donne le chiffre le plus parlant :

```bash
uv run python recettes/campagne_texttosql.py
```

### 5. Résultats — 2 min

| Critère du brief | Avant | Après |
|---|---|---|
| Requêtes valides et sûres | 0/8 bloquées | **8/8**, 7/7 légitimes acceptées |
| Réponses exactes | 4/4 | **4/4** maintenu |
| Agrégation sans doublon ni périmé | 3 → 3 (1 doublon, 1 absent) | **4 → 3 clients justes** |
| Suite de tests | 13 échecs | **0 échec / 20** |

**Limites à annoncer soi-même** — c'est ce qui distingue un travail mesuré d'un
travail affirmé :

- Les 8 questions adverses ne viennent pas d'un référentiel d'attaques ; la
  liste n'est pas exhaustive (injection par valeurs, `UNION`, requêtes coûteuses).
- Le comportement du rollback a été mesuré **sur SQLite**, pas sur PostgreSQL.
- Les mesures dépendent d'un modèle donné — raison de plus pour que la sécurité
  ne repose pas sur le comportement du LLM.

## Questions probables

| Question | Réponse courte |
|---|---|
| Pourquoi `sqlglot` et pas une regex durcie ? | La regex se trompe **dans les deux sens** — 2 failles et 2 faux positifs mesurés. Durcir le motif déplace le problème. |
| Pourquoi le rôle **et** le garde-fou ? | Le rôle ne bloque pas la lecture de `information_schema` ; le garde-fou si. Aucune couche ne remplace l'autre. |
| Pourquoi corriger le harnais en premier ? | `load_test_questions()` renvoyait `[]` : la suite passait au vert sur un ensemble vide. Sans instrument, rien n'est démontrable. |
| Le LLM est-il fiable ? | Non, et c'est le principe : il génère `DROP TABLE` sur demande. La sécurité ne repose pas sur lui. |
| Pourquoi introspecter le schéma ? | `information_schema` reflète l'état **réel**, une description en dur reflète l'état *supposé*. Bonus : les types. |

## Répartition suggérée

| Séquence | Qui |
|---|---|
| 1–2 Contexte et diagnostic | |
| 3 Conception | |
| 4 Démonstration | |
| 5 Résultats et limites | |

Celui qui n'expose pas pilote l'écran : les transitions sont plus nettes, et
les deux paraissent maîtriser l'ensemble.
