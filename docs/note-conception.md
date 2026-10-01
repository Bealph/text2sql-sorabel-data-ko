# Note de conception — garde-fous SQL

> [README](../README.md) · [Présentation](presentation.md) · [Diagnostic](note-diagnostic.md) · **Conception** · [Prise en main](prise-en-main.md) · [Journal](../JOURNAL.md) · [Brief](../brief-agent-text-to-sql.md)

**Objet.** Définir les garde-fous SQL, la stratégie de fiabilisation de
l'agrégation et la vérification d'exactitude. Livrable §2 du
[brief](../brief-agent-text-to-sql.md), suite de la
[note de diagnostic](note-diagnostic.md).

| Volet du brief | Section |
|---|---|
| Définir les garde-fous SQL | §1 à §7 |
| Localiser doublons / données périmées et stratégie de correction | §8 |
| Définir la vérification d'exactitude | §9 |

---

## 1. Pourquoi réparer l'existant ne suffit pas

Le réflexe serait de remplacer le `pass` par un `raise` et de brancher
`ensure_safe()` dans `run_query()`. **Insuffisant** : la détection repose sur une
expression régulière qui se trompe dans les deux sens. Mesuré sur
`referenced_tables()` :

| Requête | Tables vues | Conséquence |
|---|---|---|
| `SELECT * FROM "utilisateurs"` | *aucune* | **passe** le contrôle |
| `SELECT * FROM/*x*/utilisateurs` | *aucune* | **passe** le contrôle |
| `SELECT * FROM public.clients` | `public` | **rejetée à tort** |
| `WITH t AS (SELECT * FROM clients) SELECT * FROM t` | `clients`, `t` | **rejetée à tort** (`t` = alias de CTE) |

Une regex lit du texte, elle ne connaît pas la grammaire SQL. Durcir le motif
déplacerait le problème : chaque correction ouvrirait un nouveau cas limite.

**Décision : valider sur l'arbre syntaxique, pas sur le texte.**

---

## 2. Outil retenu — `sqlglot`

Parseur SQL pur Python, dialecte PostgreSQL. Vérifié sur les quatre cas :

| Requête | `sqlglot` voit |
|---|---|
| `SELECT * FROM "utilisateurs"` | `utilisateurs` ✅ |
| `SELECT * FROM/*x*/utilisateurs` | `utilisateurs` ✅ |
| `SELECT * FROM public.clients` | `clients` ✅ |
| `WITH t AS (SELECT * FROM clients) SELECT * FROM t` | `clients` ✅ |

Les quatre erreurs disparaissent. Règle complémentaire : **une requête qui ne
parse pas est rejetée** — ce qu'on ne peut pas analyser, on ne l'exécute pas.

À ajouter : `sqlglot>=25,<28` dans `pyproject.toml`.

---

## 3. Les trois contrôles

Un **seul parsing** pour les trois, dans cet ordre :

```python
arbres = sqlglot.parse(sql, dialect="postgres")   # une seule analyse

if len(arbres) != 1:            # ① instruction unique
    raise UnsafeQueryError(...)
arbre = arbres[0]
if not isinstance(arbre, exp.Select):   # ② lecture seule
    raise UnsafeQueryError(...)
# ③ périmètre, sur ce même arbre
```

L'ordre importe : vérifier d'abord qu'il n'y a **qu'une** instruction rend
`arbres[0]` légitime. Analyser la première instruction avant d'avoir compté
reviendrait à ignorer silencieusement les suivantes.

### 3.1 Lecture seule — allowlist, pas denylist

L'existant liste les instructions **interdites** (`WRITE_KEYWORDS`) : tout ce
qui n'y figure pas est autorisé. Un mot-clé oublié (`COPY`, `CALL`, `MERGE`,
`VACUUM`…) suffit à ouvrir une brèche.

**Retenu : n'autoriser que `SELECT`.** Le reste est refusé sans être énuméré.

Vérifié : `SELECT` **et** `WITH … SELECT` produisent un nœud `Select`, donc les
CTE restent autorisées ; `DELETE`, `DROP`, `UPDATE` produisent des nœuds
distincts et sont refusés.

### 3.2 Périmètre des tables

Extraire les tables physiques de l'arbre, alias de CTE exclus :

```python
ctes = {c.alias_or_name.lower() for c in arbre.find_all(exp.CTE)}
tables = {t.name.lower() for t in arbre.find_all(exp.Table)} - ctes
if tables - ALLOWED_TABLES:
    raise UnsafeQueryError(...)
```

Couvre sous-requêtes, `UNION` et jointures — tous les nœuds `Table` sont
visités quelle que soit leur profondeur. Bloque `information_schema`.

### 3.3 Instruction unique

`sqlglot.parse()` renvoie une liste : plus d'un élément ⇒ refus. Le découpage
tient compte de la grammaire — un `;` à l'intérieur d'une chaîne
(`WHERE ville = 'a;b'`) n'est pas un séparateur.

Vérifié : `SELECT 1; DROP TABLE clients` → 2 instructions.

---

## 4. Point d'application

**Dans `run_query()`**, pas dans l'outil de l'agent :

```python
def run_query(sql: str, engine: Engine) -> list[tuple[Any, ...]]:
    sql = ensure_safe(sql)          # ← systématique, non contournable
    with engine.connect() as conn:
        ...
```

Un garde-fou sur le chemin nominal est une convention ; au point d'exécution,
c'est une garantie. Aucun appelant — outil, script, test, développement futur —
ne doit atteindre la base sans passer par lui.

Conséquence assumée : les tests exécutant du SQL passent aussi par le
garde-fou. C'est voulu — le jeu de référence ne contient que des `SELECT` sur
les tables autorisées.

---

## 5. Défense en profondeur — rôle PostgreSQL

Le garde-fou applicatif **filtre** ; un rôle restreint **garantit**.

```sql
CREATE ROLE sorabel_agent LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE sorabel TO sorabel_agent;
GRANT USAGE ON SCHEMA public TO sorabel_agent;
GRANT SELECT ON clients, produits, commandes, lignes_commande TO sorabel_agent;
```

**Implémenté** — [roles.py](../roles.py), lancé par `make roles`. Deux
connexions coexistent : `DB_URL` (propriétaire, pour `seed.py`) et
`AGENT_DB_URL` (rôle `sorabel_agent`, pour l'agent). Les droits sont accordés
**table par table**, jamais via `ALL TABLES` : une table ajoutée plus tard reste
inaccessible par défaut.

Mesures après création du rôle :

| Requête | Verdict moteur |
|---|---|
| `SELECT COUNT(*) FROM commandes` | passe ✅ |
| `DELETE` · `UPDATE` · `INSERT` · `TRUNCATE` · `CREATE` | **bloqués** — `InsufficientPrivilege` |
| `DROP TABLE` | **bloqué** — `must be owner of table` |
| `SELECT * FROM utilisateurs` (hors périmètre) | **bloqué** |
| `SELECT … FROM information_schema.tables` | **passe**, mais filtré : 4 tables visibles sur 5 |

**Ce que le rôle ne couvre pas.** `information_schema` reste interrogeable —
PostgreSQL l'expose à tous les rôles, en filtrant selon les privilèges. La
cartographie est donc limitée aux tables autorisées, mais non nulle. Le
contrôle de périmètre applicatif (§3.2) reste nécessaire pour la refuser
entièrement.

C'est la complémentarité recherchée : le rôle **garantit** l'absence d'écriture,
le garde-fou **filtre** ce que le rôle laisse passer en lecture. Cette mesure
supprime aussi la dépendance au rollback implicite relevée au diagnostic.

---

## 6. Refus et journalisation

`UnsafeQueryError` porte le motif et la règle violée, sans exposer la structure
de la base :

```
instruction refusée — seules les requêtes SELECT sont autorisées (reçu : DELETE)
table hors périmètre — 'utilisateurs'
instructions multiples refusées (2 détectées)
```

L'agent renvoie ce motif plutôt qu'un résultat inventé, conformément à son
prompt système. Chaque refus est journalisé via `structlog` (déjà déclaré,
inutilisé) : question d'origine, SQL généré, règle violée.

---

## 7. Critères de validation

- [ ] Les 5 tests de `tests/test_sql_guard.py` passent, **dont**
      `test_executor_refuses_dangerous_query` — qui vérifie le point d'application
- [ ] Campagne adverse : **8/8 bloquées** au lieu de 0/8
      (`recettes/campagne_texttosql.py`)
- [ ] Les 4 questions de référence restent exactes — aucun faux positif
- [ ] Les 4 cas limites du §1 sont correctement classés
- [ ] Une requête syntaxiquement invalide est rejetée, non transmise à la base

Le second critère est le plus démonstratif : passer de **0/8 à 8/8** sans
dégrader aucune réponse légitime.

---

## 8. Stratégie de fiabilisation de l'agrégation

### 8.1 Origine des doublons et des données périmées

| Origine | Mécanisme |
|---|---|
| **Doublons** | le même client existe dans les deux sources (`FR-001` / `" fr-001 "`) et `normalize_key()` renvoie l'identifiant brut : les deux clés diffèrent, donc rien n'est rapproché |
| **Données périmées** | `aggregate()` conserve les deux versions au lieu de garder la plus récente |
| **Données manquantes** | `fetch_all()` ne suit pas `next_cursor` : `FR-003` n'entre jamais dans le système |
| **Données inexploitables** | `source_two.normalize()` ne projette pas vers le schéma commun |

### 8.2 Correctifs retenus

**Clé de dédoublonnage** — normalisation par `strip()` puis `lower()` :

```python
def normalize_key(external_id: str) -> str:
    return external_id.strip().lower()      # " fr-001 " → "fr-001"
```

**Fraîcheur** — comparer des **dates parsées**, jamais des chaînes :

```python
datetime.fromisoformat(rec["ingested_at"])
```

Une comparaison de chaînes fonctionne par hasard sur l'ISO 8601 et casse au
premier format différent. Un enregistrement sans date exploitable est traité
comme le plus ancien, pas ignoré.

**Fusion** — champ par champ, une valeur renseignée prime sur une valeur vide,
**même si** l'enregistrement le plus frais a le champ vide. La fraîcheur
départage seulement quand les deux valeurs sont renseignées.

**Pagination** — suivre `next_cursor` jusqu'à `None`, avec une borne de
sécurité sur le nombre de pages pour éviter une boucle infinie si l'API
renvoie toujours le même curseur.

**Retry sur `429`** — dans `sources/base.py`, donc **partagé** par les deux
connecteurs : un quota est une propriété du transport HTTP, pas de la source.
`tenacity` avec backoff exponentiel, nombre d'essais borné. Un `429` persistant
doit lever, pas retourner une liste partielle silencieusement.

**Normalisation `source_two`** — mapping explicite
`ref → external_id`, `label → raison_sociale`, `town → ville`,
`ts → ingested_at`, plus `source: "source_two"`.

### 8.3 Critère de validation

Sur les sources réelles : **4 enregistrements collectés → 3 clients uniques**,
`FR-001` fusionné à la version du 2024-04-01, `FR-003` présent. Aujourd'hui :
3 collectés → 3 en sortie, avec un doublon et un manquant.

---

## 9. Vérification d'exactitude

**Réparer `load_test_questions()`** — lire réellement le JSON. C'est le
prérequis absolu : tant que la fonction renvoie `[]`, la suite de tests passe
au vert sur un ensemble vide et aucune mesure d'avancement n'a de valeur.

**Étendre le jeu de test** — les 8 questions adverses du diagnostic deviennent
des cas de test permanents, avec le verdict attendu (rejet). Elles ne testent
pas la même chose que les 4 questions de référence :

| Jeu | Vérifie |
|---|---|
| 4 questions de référence | l'**exactitude** des réponses |
| 8 questions adverses | la **sûreté** des requêtes |

**Séparer les deux niveaux** — les tests unitaires tournent sur SQLite en
mémoire, sans dépendance externe. La campagne complète, qui appelle le LLM,
reste un script lancé à la demande : un test qui dépend d'un modèle distant
n'est pas reproductible.

**Critère de sortie** — `make test` au vert, campagne à **8/8 bloquées** et
**4/4 exactes**.

---

## 10. Reste à trancher avec le binôme

- Rôle PostgreSQL en lecture seule : on l'ajoute maintenant ou après les
  garde-fous applicatifs ?
- Collecte des deux sources en parallèle : annoncée dans le README, aujourd'hui
  séquentielle. Dans le périmètre ou hors sujet ?
- Le comportement du rollback n'a été mesuré que sur SQLite (cf. note de
  diagnostic §6) — à reconfirmer sur PostgreSQL.
