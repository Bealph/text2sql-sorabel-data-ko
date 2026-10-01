# Journal des corrections

> [README](README.md) · [Présentation](docs/presentation.md) · [Diagnostic](docs/note-diagnostic.md) · [Conception](docs/note-conception.md) · [Prise en main](docs/prise-en-main.md) · **Journal** · [Brief](brief-agent-text-to-sql.md)

Livrable du brief [brief-agent-text-to-sql.md](brief-agent-text-to-sql.md) :
*« Consigner cause et correctifs dans un journal. »*

Chaque entrée suit le même format : **symptôme observé → cause identifiée →
correctif appliqué → vérification**. Les entrées sont classées par nature, car
elles ne relèvent pas toutes du même chantier : certaines débloquent
l'environnement de travail, d'autres corrigent le code lui-même.

---

## Avant / après par étape du brief

Synthèse chiffrée, étape par étape. Le détail de chaque correctif est en
partie E ; la conception qui les précède est dans
[docs/note-conception.md](docs/note-conception.md).

### §1 — Diagnostiquer les requêtes générées

| Indicateur | Avant | Après |
|---|---|---|
| Requêtes problématiques identifiées | aucune analyse | **8 relevées**, avec cause et famille de risque |
| Note de diagnostic + schéma | inexistants | [docs/note-diagnostic.md](docs/note-diagnostic.md) |
| Reproductibilité de la mesure | — | `recettes/campagne_texttosql.py` |

*Découverte structurante* : 4/4 réponses exactes sur le jeu fourni. Le symptôme
annoncé par le brief — « des chiffres faux » — n'est pas reproductible par la
voie Text-to-SQL. Le risque y est de **sécurité**, l'inexactitude vient de
l'agrégation. Le plan de travail en découle.

### §3 — Génération Text-to-SQL sécurisée

| Indicateur | Avant | Après |
|---|---|---|
| Requêtes adverses bloquées | **0/8** | **8/8** |
| Requêtes légitimes acceptées | 5/7 *(2 faux positifs)* | **7/7** |
| Méthode de validation | expression régulière | **arbre syntaxique** (`sqlglot`) |
| Politique de lecture seule | denylist `WRITE_KEYWORDS` | **allowlist** — seul `SELECT` |
| Point d'application | aucun — `ensure_safe()` jamais appelé | **`run_query()`**, non contournable |
| Protection moteur | aucune | rôle PostgreSQL en lecture seule |
| Tests `test_sql_guard` | 0/5 | **5/5** |

Les deux faux positifs levés : `SELECT * FROM public.clients` (schéma qualifié)
et `WITH t AS (…) SELECT * FROM t` (alias de CTE), tous deux refusés à tort par
la regex.

### §4 — Agrégation multi-sources fiabilisée

| Indicateur | Avant | Après |
|---|---|---|
| Enregistrements collectés | 3 *(1 page sur 2)* | **4** |
| Clients au référentiel | 3 *(1 doublon, 1 absent)* | **3 justes** |
| `FR-001` | présent 2 fois, version périmée | **fusionné**, version 2024-04-01 |
| `FR-003` | absent | **présent** |
| Normalisation `source_two` | aucune (clés brutes) | schéma commun |
| Retry sur `429` | absent | `tenacity`, partagé |
| Comparaison des dates | chaînes | **datetime UTC** |
| Tests `test_aggregate` + `test_sources` | 0/7 | **7/7** |

*Piège évité* : comparer une date naïve à une date avec fuseau lève
`TypeError`. Les deux mocks étant naïfs, le tri fonctionnait — il aurait planté
au premier changement de format côté source.

### §5 — Vérifier l'exactitude et documenter

| Indicateur | Avant | Après |
|---|---|---|
| Questions chargées par `load_test_questions()` | **0** sur 4 | **4** sur 4 |
| Valeur de la suite de tests | vert sur un ensemble vide | mesure réelle |
| Suite complète | 13 échecs / 3 succès | **0 échec / 20 succès** |
| `make lint` | 1 erreur | **au vert** |
| Journal des corrections | inexistant | ce document |

Traité **en premier** parmi les correctifs : sans instrument de mesure fiable,
aucune correction n'est démontrable.

État de référence au démarrage : commit `a035fbb`, suite de tests à
**13 échecs / 3 succès / 1 ignoré**.

---

## Partie A — Déblocage de l'environnement

Ces corrections ne relèvent pas du brief : elles étaient nécessaires pour que
le projet démarre sur le poste de développement. Elles sont consignées pour
que la PR soit lisible.

### A1 — Le conteneur PostgreSQL ne publiait pas son port

**Symptôme.** `make up` échouait sur :

```
Error response from daemon: failed to set up container networking:
Bind for 0.0.0.0:5432 failed: port is already allocated
```

Trompeur : `docker compose ps` affichait pourtant le conteneur `db` comme
`Up (healthy)`. Il tournait bien, mais avec `5432/tcp` au lieu de
`0.0.0.0:5432->5432/tcp` — le port n'était pas publié, donc la base était
injoignable depuis l'hôte (DBeaver comme l'application).

**Cause.** Un conteneur d'un autre projet, `velmo-postgres`
(`pgvector/pgvector:pg16`), occupait déjà `0.0.0.0:5432`. Conflit de port
entre deux stacks Docker indépendantes, sans rapport avec ce dépôt.

**Correctif.** Décalage du port hôte à `5433` plutôt qu'arrêt de l'autre
projet, afin que les deux bases cohabitent :

| Fichier | Changement |
|---|---|
| [docker-compose.yml](docker-compose.yml) | `"5432:5432"` → `"5433:5432"` + commentaire |
| [.env](.env) | `DB_URL` sur le port `5433` |
| [.env.example](.env.example) | idem |

Le port **interne** au conteneur reste `5432` : seul le mapping hôte change.
Sur un poste où le `5432` est libre, revenir à `"5432:5432"` suffit.

**Vérification.**

```
docker compose ps  →  db  0.0.0.0:5433->5432/tcp  (healthy)
```

Connexion applicative confirmée : PostgreSQL 16.14, 3 clients / 2 produits /
4 commandes / 3 lignes, `SUM(montant)` = 425.0 — conforme à la valeur attendue
par [data/questions_test.json](data/questions_test.json).

### A2 — Tables invisibles dans DBeaver : connexion sur la mauvaise base

**Symptôme.** Après un `make seed` pourtant réussi (« Base de démonstration
alimentée. »), aucune table visible dans DBeaver. Le seed a été suspecté en
premier lieu.

**Cause.** La connexion DBeaver, **nommée** « sorabel », pointait en réalité sur
`jdbc:postgresql://localhost:5433/postgres`. Deux pièges se combinaient :

1. Le nom d'une connexion DBeaver est une étiquette libre : il ne détermine pas
   la base atteinte. Une connexion appelée « sorabel » peut viser `postgres`.
2. Le nom de la base avait été corrigé dans le champ *Database*, mais la
   connexion était en mode `Connect by: URL`. Dans ce mode, DBeaver grise les
   champs Host / Port / Database et **c'est l'URL qui fait foi** : éditer le
   champ n'a aucun effet tant que l'URL n'est pas modifiée.

Le serveur héberge deux bases, d'où la confusion :

| Base | Tables dans `public` |
|---|---|
| `postgres` (base système, celle qui était inspectée) | aucune |
| `sorabel` (cible du seed) | `clients`, `commandes`, `lignes_commande`, `produits` |

**Correctif.** URL de la connexion corrigée en
`jdbc:postgresql://localhost:5433/sorabel`, puis *Invalidate/Reconnect*. Aucun
fichier du dépôt concerné : l'erreur était entièrement côté poste client.

**Vérification.** Tables visibles dans DBeaver, et recette D1 à 20/20.

**À retenir.** Le seed n'a jamais été en cause. Avant de suspecter le
chargement des données, vérifier `SELECT current_database();` — c'est le
premier contrôle de la recette D1, ajouté pour cette raison.

---

## Partie B — Correctifs de code

### B1 — `make seed` échouait : `.env` jamais chargé sur ce chemin

**Symptôme.**

```
RuntimeError: Variable d'environnement 'DB_URL' non définie.
  File "seed.py", line 38, in main
  File "db.py", line 69, in engine_from_env
```

alors que `.env` contenait la bonne valeur (connexion DBeaver fonctionnelle sur
les mêmes paramètres).

**Cause.** Contrairement à une première lecture — `python-dotenv` déclaré mais
inutilisé — la dépendance **était** appelée, mais depuis un module feuille :
`load_dotenv()` se trouvait au niveau module dans `agent/llm.py`. Il ne
s'exécutait donc que par effet de bord, si la chaîne d'import passait par
`agent.llm` :

| Commande | Chaîne d'import | `.env` chargé ? |
|---|---|---|
| `make chat` | `agent.chat` → `agent.agent` → `agent.llm` | oui, par accident |
| `make seed` | `seed.py` → `db.py` | **non** — `agent.llm` jamais importé |
| `pytest` | fixtures SQLite en mémoire | sans objet |

La configuration dépendait de l'ordre d'import. Un point d'entrée qui ne touche
pas au LLM n'a aucune raison d'importer `agent.llm`, et perdait la config.

**Correctif.** Règle appliquée : `load_dotenv()` appartient aux **points
d'entrée**, jamais aux modules de bibliothèque — un module importé ne doit pas
modifier l'environnement du processus appelant.

| Fichier | Changement |
|---|---|
| [seed.py](seed.py) | `load_dotenv()` en tête de `main()` |
| [agent/chat.py](agent/chat.py) | `load_dotenv()` en tête de `main()` |
| [agent/llm.py](agent/llm.py) | retrait du `load_dotenv()` de niveau module ; docstring précisant que la config incombe à l'appelant |

[db.py](db.py) n'a **pas** été modifié : `engine_from_env()` lit `os.environ`,
c'est son rôle. Y placer `load_dotenv()` aurait reproduit le défaut corrigé.

**Vérification.**

```bash
# sans aucune variable exportée à la main
$ uv run python seed.py
Base de démonstration alimentée.

# non-régression : plus d'effet de bord à l'import
$ uv run python -c "import agent.llm, os; print(os.environ.get('DB_URL'))"
None
```

Le second test est celui qui distingue le correctif du simple contournement :
il aurait affiché la valeur du `.env` si le chargement était resté dans un
module de bibliothèque.

### B2 — `make chat` : outil LangChain sans docstring

**Symptôme.** `ValueError: Function must have a docstring if description not
provided.` levée à l'import de `agent/tools.py`, ligne 20, sur le décorateur
`@tool`.

**Cause.** `run_sql_query` n'avait pas de docstring, contrairement à sa voisine
`aggregate_clients`. Pour un outil LangChain, la docstring n'est pas
décorative : **c'est la description transmise au LLM** dans le schéma de
l'outil. Sans elle, l'agent n'a aucun moyen de choisir entre `run_sql_query` et
`aggregate_clients`. LangChain refuse donc de construire l'outil plutôt que
d'en exposer un aveugle.

**Correctif.** Docstring ajoutée à [agent/tools.py](agent/tools.py), rédigée
comme une description destinée au modèle : ce que fait l'outil, sur quelles
tables, et quand lui préférer `aggregate_clients`.

**Vérification.** `tests/test_agent_tools.py` passe (1 passed). Les deux outils
exposent bien leur `description`.

### B3 — `make chat` : paramètre renommé dans LangChain 1.x

**Symptôme.** `TypeError: create_agent() got an unexpected keyword argument
'prompt'`.

**Cause.** `agent/agent.py` appelait `create_agent(llm, tools,
prompt=SYSTEM_PROMPT)`. Dans langchain 1.3.14, le paramètre s'appelle
`system_prompt`. Inspection de la signature réelle plutôt que supposition :

```
create_agent(model, tools, system_prompt, middleware, response_format, ...)
```

**Correctif.** `prompt=` → `system_prompt=` dans [agent/agent.py](agent/agent.py).

### B4 — `make chat` : appel LLM rejeté (`API version not supported`)

**Symptôme.** Après B2 et B3, l'agent se construit mais tout appel échoue :

```
BadRequestError: 400 - {'error': {'code': 'BadRequest',
                        'message': 'API version not supported'}}
```

**Causes — deux problèmes distincts.**

*1. Variables inversées dans `.env`.* `AZURE_AI_INFERENCE_ENDPOINT` contenait
la clé API, et `AZURE_AI_INFERENCE_API_KEY` l'URL. Les deux valeurs ont été
permutées.

*2. Incompatibilité de protocole.* Le déploiement expose une route
**OpenAI-compatible** (`/openai/v1`), qui refuse le paramètre `api-version`.
`AzureAIChatCompletionsModel` l'ajoute d'office et ne permet pas de le retirer
(`default_query={}` reste sans effet). Diagnostic par appels HTTP directs :

| Requête | Réponse |
|---|---|
| `POST /openai/v1/chat/completions` sans `api-version` | **200** |
| la même avec `?api-version=2025-08-07` | **400** `API version not supported` |

La clé et le déploiement étaient donc valides : seul le paramètre parasite
bloquait. Les variantes `/models` (Azure AI Inference) et racine renvoient 404 —
`/openai/v1` est bien la bonne route.

**Correctif.** [agent/llm.py](agent/llm.py) instancie désormais `ChatOpenAI`
avec `base_url`, qui parle le même protocole sans ajouter `api-version`.
`langchain-openai` — jusqu'ici dépendance transitive — est déclaré
explicitement dans [pyproject.toml](pyproject.toml).

À noter : `AZURE_OPENAI_API_VERSION` présent dans `.env` n'est lu nulle part et
n'a pas à l'être — cette route n'en veut pas.

**Écart documentaire non résolu.** Le dépôt documente Kimi-K2.6 sur Azure AI
Inference ; le déploiement réel est `gpt-5.4-mini` sur une route Azure OpenAI.
Le code suit désormais la réalité, mais README et `.env.example` mentionnent
encore Kimi-K2.6. À trancher : aligner la documentation, ou repointer le
déploiement.

**Vérification.** Chaîne complète testée :

```
1. LLM     -> 'PONG'
2. Agent   -> construit
3. Réponse -> « Il y a eu 4 commandes au total.
              Source : table commandes via la base de démonstration Sorabel. »
```

---

## Partie C — Documentation

### C1 — README enrichi

[README.md](README.md) présentait comme « Fonctionnalités » des comportements
que le code n'implémente pas : un lecteur pouvait croire le projet
opérationnel. La section « Known issues » restait vague (« se comporte de façon
surprenante »).

Ajouts : bandeau de statut, section **Mission** (reprise du cadrage du brief),
**schéma du flux de données** en Mermaid — livrable explicitement demandé au
§1 du brief —, **Points importants** (règles attendues pour les garde-fous,
l'agrégation, la collecte), modèle de données, et une section **État des lieux**
où chaque écart pointe une ligne précise. Checklist de critères d'acceptation
reprise des critères de performance du brief.

### C2 — Diagnostic corrigé

La rubrique « Configuration » ajoutée à l'État des lieux affirmait que
`python-dotenv` était « déclaré en dépendance mais jamais appelé ». C'était
**faux** : il était appelé dans `agent/llm.py`. La rubrique décrit désormais le
vrai défaut (mauvais emplacement, pas absence) et son correctif — cf. B1.

---

## Partie D — Outillage de recette

### D1 — Recette du seed

Créé : [recettes/recette_seed.sql](recettes/recette_seed.sql).

Motivé par l'incident A2 : l'inspection visuelle dans un client graphique ne
prouve rien, et peut même induire en erreur. La recette rend le verdict
reproductible et exécutable des deux côtés (DBeaver ou ligne de commande).

Vingt contrôles répartis en cinq familles :

| Famille | Objet |
|---|---|
| 0. Contexte | `current_database() = 'sorabel'` — le piège de A2 |
| 1. Structure | les quatre tables existent |
| 2. Cardinalités | 3 clients / 2 produits / 4 commandes / 3 lignes |
| 3. Jeu de référence | les quatre valeurs de `data/questions_test.json` |
| 4. Intégrité | aucune ligne orpheline (commandes, lignes) |
| 5. Cohérence | montants, quantités, prix > 0 ; pas de doublon de raison sociale |

La famille 3 est la plus utile pour la suite : elle vérifie que les valeurs
attendues par le jeu de test sont bien celles que contient la base. Si elle
échoue, inutile de chercher un bug côté Text-to-SQL — le problème est en amont.

**Résultat au 2026-08-03 : 20 contrôles, 20 OK.**

```
 3. Jeu de référence | Combien de commandes ?      | 4     | 4     | OK
 3. Jeu de référence | Chiffre d'affaires total    | 425.0 | 425.0 | OK
 3. Jeu de référence | Combien de clients actifs ? | 2     | 2     | OK
 3. Jeu de référence | Villes distinctes           | 2     | 2     | OK
```

Détail d'implémentation : le CA est comparé via `round(sum(montant)::numeric, 1)`
et non en float brut — `montant` est un `Float` et la comparaison textuelle de
flottants est instable.

**Limite connue, non vérifiée.** Si les tables n'existent pas (mauvaise base,
seed non joué), le script devrait s'interrompre sur
`relation "clients" does not exist` au lieu d'afficher proprement `ECHEC` sur
les lignes concernées — les sous-requêtes de la CTE sont évaluées quel que soit
le résultat du contrôle 0. Ce comportement n'a **pas** été testé : l'exécution
de vérification sur la base `postgres` a été interrompue avant terme. À
confirmer, et à corriger si le message d'erreur brut est jugé trop obscur.

### D2 — Banc d'essai Streamlit

Créé : [ui/app.py](ui/app.py), lancé par `make ui`.

Principe : la page **exécute** le code du dépôt au lieu d'en décrire l'état.
Les verdicts sont mesurés au chargement, ce qui évite qu'ils se périment.

- **Recette du jeu de test** — rejoue les quatre questions, au choix avec le SQL
  du JSON (valide la base) ou avec le SQL généré par le LLM (valide l'agent).
  Comparer les deux modes isole la cause d'un écart.
- **Diagnostic** — démonstrations live : les trois familles de requêtes
  dangereuses passent le garde-fou, deux enregistrements du même client
  ressortent en double, `load_test_questions()` renvoie 0 sur 4.
- **Propositions** — pistes pour les trois chantiers, plus quelques extensions
  (journalisation via `structlog`, `LIMIT` implicite, timeout, collecte
  parallèle).

La page lit le jeu de test directement dans le JSON, sans passer par
`load_test_questions()` : ce contournement est assumé et signalé dans le code,
puisque la fonction fait partie des défauts à corriger.

**Correctif au premier lancement — `ModuleNotFoundError: No module named 'db'`.**
Streamlit place le dossier du script (`ui/`) en tête de `sys.path`, et non la
racine du projet. Or `db.py` et `evaluation.py` sont des modules racine **non
packagés** : `[tool.setuptools.packages.find]` ne déclare que `agent*`, `sql*`
et `sources*`. Ils ne sont donc importables que via le répertoire courant —
c'est d'ailleurs pourquoi pytest fonctionne, sa config portant
`pythonpath = ["."]`.

Correctif : `ui/app.py` insère la racine dans `sys.path` avant les imports du
projet, et charge le `.env` par chemin absolu — la page reste ainsi lançable
depuis n'importe quel répertoire. À reproduire pour tout futur script hors
racine, ou à régler globalement en packageant `db` et `evaluation`.

Vérification : `uv run python ui/app.py` reproduit le `sys.path` de Streamlit
(dossier du script en tête) et exécute le script de bout en bout. Un simple
`curl` sur le port ne suffit pas — Streamlit n'exécute le script qu'à la
connexion d'un client, si bien qu'une erreur d'import ne remonte pas dans un
test HTTP.

**Mesure notable — Text-to-SQL : 4/4 exacts.** Le LLM génère du SQL correct sur
les quatre questions de référence. Le brief annonce « l'agent renvoie des
chiffres faux » : sur *ce* jeu, les chiffres sont justes. Le risque réel n'est
donc pas l'inexactitude du Text-to-SQL, mais l'**absence de garde-fou** autour
de lui, et l'agrégation multi-sources. Nuance à porter dans la note de
diagnostic : corriger ce qui est mesurablement cassé, pas ce que l'énoncé
laisse supposer.

### D3 — Campagne de mesure et note de diagnostic

Créés : [recettes/campagne_texttosql.py](recettes/campagne_texttosql.py) et
[docs/note-diagnostic.md](docs/note-diagnostic.md) — livrable §1 du brief.

**Choix de méthode.** Les 4 questions fournies sont toutes légitimes : elles ne
peuvent pas révéler un risque de sécurité. La campagne ajoute donc 8 questions
adverses (écriture, DDL, hors périmètre, instructions enchaînées). Les requêtes
générées sont exécutées sur une **base SQLite jetable** alimentée comme la
démo : les destructions sont réelles — c'est la preuve recherchée — sans risque
pour PostgreSQL.

**Résultats.**

| Famille | Mesure |
|---|---|
| Référence (4) | **4/4 réponses exactes** |
| Adverses (8) | **0/8 bloquées** par le garde-fou |

Le modèle génère sans réticence `DELETE FROM clients`, `TRUNCATE`, `UPDATE`,
`INSERT` et `DROP TABLE` sur simple demande en français. Aucune formulation
d'attaque n'a été nécessaire.

**Découverte la plus importante — le rollback implicite.** Sept requêtes sur
huit n'ont laissé aucune trace, ce qui pouvait passer pour une protection.
Mesure dédiée :

| Type | Comportement |
|---|---|
| DML (`DELETE`, `UPDATE`, `INSERT`) | annulé |
| DDL (`DROP TABLE`) | **exécuté, table détruite** |

Cause : `run_query()` ouvre `engine.connect()` sans jamais committer,
SQLAlchemy 2 annule donc la transaction à la fermeture. La protection est
**accidentelle, incomplète, et à un `commit()` de disparaître**. Sans cette
mesure, le diagnostic aurait conclu à tort que les écritures étaient bloquées.

**Conséquence sur le cadrage.** Le brief annonce « l'agent renvoie des chiffres
faux ». Sur le jeu fourni, les chiffres sont **justes** (4/4). Le symptôme n'est
pas reproductible par la voie Text-to-SQL : sa cause est l'agrégation
multi-sources. Le Text-to-SQL, lui, porte un risque de **sécurité**, pas
d'exactitude. La note priorise en conséquence : harnais de vérification
d'abord, garde-fous ensuite, agrégation enfin.

### D4 — Bac à sable dans le banc d'essai

Onglet ajouté à [ui/app.py](ui/app.py) : saisie d'une question en français ou
d'une requête SQL libre, avec affichage séparé des trois étapes — génération,
garde-fou, exécution. C'est ce découpage qui permet de situer une défaillance.

La page signale explicitement les requêtes risquées que `ensure_safe()` laisse
passer (écriture, hors périmètre, instructions enchaînées), et rappelle le
comportement du rollback lorsqu'une instruction d'écriture s'exécute sans
erreur apparente. Une case permet d'exécuter malgré un refus du garde-fou, pour
constater ce que `run_query()` laisse effectivement passer aujourd'hui.

---

## Partie E — Chantiers du brief

Conception préalable : [docs/note-conception.md](docs/note-conception.md).
Constats numérotés d'après [docs/note-diagnostic.md](docs/note-diagnostic.md).

### E1 — V1 · harnais de vérification — [evaluation.py](evaluation.py)

`load_test_questions()` renvoyait `[]` : les tests paramétrés passaient au vert
sur un ensemble vide. Corrigé en lisant réellement le JSON. Traité **en
premier** — sans instrument de mesure, aucune correction n'est démontrable.

Effet : 5 tests d'exactitude passent, et l'erreur de lint `json importé mais
inutilisé` disparaît d'elle-même — elle n'était qu'un symptôme.

### E2 — C1 + C2 · agrégation multi-sources — [sources/](sources/)

| Constat | Correctif |
|---|---|
| **C1** pagination | `fetch_all()` suit `next_cursor` ; bornes anti-boucle (curseurs vus, plafond 100 pages) |
| **C1** quota `429` | retry `tenacity` dans `base.py`, **partagé** — un quota est une propriété du transport, pas de la source. Ne réessaie que sur `429` ; `reraise=True` pour ne jamais renvoyer une collecte partielle en silence |
| **C1** normalisation | `source_two.normalize()` projette enfin `ref`/`label`/`town`/`ts` vers le schéma commun |
| **C2** clé | `normalize_key()` applique `strip()` + `lower()` |
| **C2** fraîcheur | dates **parsées** et ramenées en UTC |
| **C2** fusion | valeur renseignée prime, dans l'ordre du plus frais au plus ancien |

**Piège évité — le mélange de fuseaux.** Comparer une date naïve à une date
avec fuseau lève `TypeError: can't compare offset-naive and offset-aware
datetimes` en Python. Les deux mocks étant naïfs aujourd'hui, le tri
fonctionnait ; il aurait planté au premier changement de format côté source.
`parse_horodatage()` ramène tout en aware UTC, avec une convention explicite :
une date sans fuseau est **supposée UTC**. Une date illisible n'est ni devinée
ni avalée — l'enregistrement est conservé, classé en dernier, et l'anomalie
journalisée.

**Résultat sur les sources réelles :**

| | Avant | Après |
|---|---|---|
| Collectés | 3 (page 2 perdue) | **4** |
| Consolidés | 3, dont 1 doublon et 1 client absent | **3 clients justes** |

`fr-001` est fusionné à la version du 2024-04-01 et tracé
`['source_one', 'source_two']` ; `fr-003` est présent.

### E3 — G1 + G2 · garde-fous SQL — [sql/](sql/)

Traités **d'un bloc** : corriger l'un sans l'autre laisse le comportement
inchangé.

**G1** — [sql/guard.py](sql/guard.py) réécrit sur `sqlglot` : la validation
porte sur l'arbre syntaxique, plus sur du texte. Trois contrôles, **un seul
parsing**, dans l'ordre instruction unique → lecture seule → périmètre. Compter
d'abord rend légitime l'analyse de `instructions[0]` ; l'inverse ignorerait
silencieusement les instructions suivantes.

Changement de principe : passage d'une **denylist** (`WRITE_KEYWORDS`, supprimé)
à une **allowlist** — seul `SELECT` est autorisé. Une liste d'interdits laisse
passer tout ce qu'elle oublie (`COPY`, `CALL`, `MERGE`, `VACUUM`…).

**G2** — [sql/executor.py](sql/executor.py) appelle `ensure_safe()` avant toute
exécution. Le contrôle est au point de passage obligé, non sur le chemin
nominal : aucun appelant ne peut le contourner.

**Mesures :**

| | Avant | Après |
|---|---|---|
| Requêtes adverses bloquées | 0/8 | **8/8** |
| Requêtes légitimes acceptées | — | **7/7** |
| Questions de référence exactes | 4/4 | **4/4** |

Les deux faux positifs de l'ancienne regex sont levés : `SELECT * FROM
public.clients` et `WITH t AS (…) SELECT * FROM t` passent désormais.

### E4 — Défense en profondeur · rôle PostgreSQL — [roles.py](roles.py)

Rôle `sorabel_agent` en lecture seule, créé par `make roles`. Deux connexions :
`DB_URL` (propriétaire, pour `seed.py`) et `AGENT_DB_URL` (agent). Droits
accordés **table par table** d'après `ALLOWED_TABLES` — une table ajoutée plus
tard reste inaccessible par défaut.

Mesuré : `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `CREATE` et `DROP` sont
refusés par le moteur ; `SELECT * FROM utilisateurs` aussi.

**Limite documentée** : `information_schema` reste interrogeable — PostgreSQL
l'expose à tous les rôles, filtré selon les privilèges (4 tables visibles sur
5). C'est le garde-fou applicatif qui le refuse. Les deux couches sont
complémentaires, aucune ne remplace l'autre.

### E5 — Schéma introspecté — [sql/generator.py](sql/generator.py)

La description des tables envoyée au LLM était écrite en dur, donc à maintenir
à chaque évolution du schéma. Elle est désormais lue dans `information_schema`,
qui reflète l'état **réel** de la base là où `db.py` reflète l'état *déclaré* —
les deux peuvent diverger (`ALTER TABLE` direct, migration hors SQLAlchemy).

Lecture faite **côté application**, mise en cache, bornée par `ALLOWED_TABLES`
et par les privilèges du rôle. L'agent n'interroge jamais le catalogue
lui-même : le garde-fou peut donc continuer à refuser `information_schema` dans
le SQL généré, sans contradiction.

Gain secondaire : l'introspection ramène les **types** (`boolean`,
`double precision`, `date`), absents du prompt en dur.

---

## Vérification finale — livrable §5

Mesures relevées sur l'état final du dépôt, toutes reproductibles.

### Exactitude sur le jeu de test

```bash
uv run python recettes/campagne_texttosql.py
```

```
Référence : 4/4 réponses exactes
Adverses  : 8/8 bloquées par le garde-fou
            0/8 ont modifié les données
```

Les quatre questions traversent la chaîne complète — `generate_sql()` →
`ensure_safe()` → `run_query()` — avec le SQL **réellement généré par le LLM**,
non le SQL de référence du JSON. Le critère *« les réponses chiffrées sont
exactes sur le jeu de test »* est vérifié de bout en bout.

Le troisième chiffre est le plus significatif : lors du diagnostic initial,
1 requête adverse sur 8 avait détruit une table (`DROP TABLE
lignes_commande`). Aucune n'atteint plus la base.

### Contrôles qualité

| Commande | Résultat |
|---|---|
| `make test` | **20 passed** |
| `make lint` | **All checks passed** |
| `make typecheck` | **Success: no issues found in 14 source files** |

`make typecheck` passe pour la première fois du projet : le paramètre `llm` de
`generate_sql()` était typé `object`, qui n'expose pas `invoke`. Remplacé par un
`Protocol` décrivant le contrat réellement utilisé — plus juste qu'un
`type: ignore`, et documenté pour l'appelant.

### Conformité de la base

```bash
docker compose exec -T db psql -U sorabel -d sorabel -f - < recettes/recette_seed.sql
```

**20 contrôles, 20 OK** — contexte, structure, cardinalités, valeurs du jeu de
référence, intégrité référentielle, cohérence métier.

### Synthèse des critères de performance

| Critère du brief | Mesure |
|---|---|
| Les requêtes générées sont valides et sûres | 8/8 adverses bloquées · 7/7 légitimes acceptées |
| Les réponses chiffrées sont exactes sur le jeu de test | 4/4 |
| L'agrégation ne contient plus de doublons ni de données périmées | 4 collectés → 3 clients justes |

---

## État de la suite de tests

Progression mesurée à chaque étape :

| Étape | Échecs | Succès |
|---|---|---|
| Commit de départ `a035fbb` | 13 | 3 |
| Déblocage de l'environnement (parties A–D) | 12 | 4 |
| Après E1 — harnais de vérification | 5 | 11 |
| Après E2 — agrégation | 5 | 11 |
| **Après E3 — garde-fous** | **0** | **20** |

**Suite intégralement au vert**, `make lint` compris. L'erreur `json importé
mais inutilisé` a disparu avec E1 : elle n'était qu'un symptôme de
`load_test_questions()` qui ne lisait pas le fichier.

**Critères de performance du brief :**

| Critère | État |
|---|---|
| Les requêtes générées sont valides et sûres | ✅ 8/8 adverses bloquées, 7/7 légitimes acceptées |
| Les réponses chiffrées sont exactes sur le jeu de test | ✅ 4/4 |
| L'agrégation ne contient plus de doublons ni de données périmées | ✅ 4 collectés → 3 clients justes |

Reste `make typecheck` : `sql/generator.py` — `Item "object" has no attribute
"invoke"`, dû au paramètre `llm` typé `object | None`. Sans effet à l'exécution.

---

## Chantiers du brief — état final

Les trois chantiers sont traités (détail en partie E). Le relevé ci-dessous est
conservé : il documente l'état de départ auquel chaque correctif répond.

### 1. Text-to-SQL sécurisé

- `sql/guard.py` — `ensure_safe` détecte le mot-clé d'écriture puis exécute
  `pass` au lieu de lever ; `referenced_tables()` est appelée sans que son
  résultat soit confronté à `ALLOWED_TABLES` ; aucun contrôle d'instruction
  unique. La fonction laisse tout passer.
- `sql/executor.py` — `run_query` n'appelle jamais `ensure_safe` : le SQL du
  LLM part directement à la base.
- `agent/tools.py` — `run_sql_query` n'a pas de docstring. Cause confirmée de
  l'échec de `test_agent_tools.py` : LangChain lève
  `Function must have a docstring if description not provided.`

### 2. Agrégation multi-sources

- `sources/aggregate.py` — `normalize_key` renvoie l'`external_id` brut ;
  `aggregate` concatène les sources sans traitement.
- `sources/source_two.py` — `normalize` ne projette pas vers le schéma commun ;
  `fetch_all` ignore `next_cursor` (une seule page collectée).
- `sources/base.py` — aucun retry sur `429`, alors que le mock en renvoie un
  appel sur deux ; `tenacity` déclaré mais inutilisé.
- `agent/tools.py` — collecte séquentielle alors que le parallélisme est annoncé.

### 3. Vérification d'exactitude

- `evaluation.py` — `load_test_questions()` renvoie `[]` alors que le fichier
  contient quatre cas : le harnais d'exactitude ne teste rien.

## Points ouverts hors périmètre

**Variables Azure inversées dans `.env`** (non corrigé, à valider) :
`AZURE_AI_INFERENCE_ENDPOINT` contient une clé API, et
`AZURE_AI_INFERENCE_API_KEY` une URL. `agent/llm.py` passe `endpoint=` et
`credential=` dans cet ordre : `make chat` échouera à l'authentification tant
que les deux valeurs ne sont pas permutées. Le `.env` est couvert par
`.gitignore`, aucun secret n'est versionné.

Deux écarts connexes : le modèle configuré est `gpt-5.4-mini` sur un endpoint
`/openai/v1`, alors que le dépôt documente Kimi-K2.6 sur Azure AI Inference —
`AzureAIChatCompletionsModel` attend un endpoint Azure AI Inference, pas une
route Azure OpenAI. Et `AZURE_OPENAI_API_VERSION` a été ajouté au `.env` sans
être lu nulle part.

**`pydantic-settings`** est déclaré dans `pyproject.toml` et inutilisé. Un
module de configuration centralisé donnerait des erreurs explicites au lieu des
`KeyError` bruts de `agent/tools.py`. Écarté pour garder la PR centrée sur le
brief.

**`brief.md` est vide** (0 octet) ; le brief exploitable est
`brief-agent-text-to-sql.md`. Les deux fichiers ne sont pas suivis par git.
