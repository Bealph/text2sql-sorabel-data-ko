# Journal des corrections

Livrable du brief [brief-agent-text-to-sql.md](brief-agent-text-to-sql.md) :
*« Consigner cause et correctifs dans un journal. »*

Chaque entrée suit le même format : **symptôme observé → cause identifiée →
correctif appliqué → vérification**. Les entrées sont classées par nature, car
elles ne relèvent pas toutes du même chantier : certaines débloquent
l'environnement de travail, d'autres corrigent le code lui-même.

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

## État de la suite de tests

Mesuré avant (`git stash` des modifications) et après :

| | Avant | Après |
|---|---|---|
| Échecs | 13 | 13 |
| Succès | 3 | 3 |
| Ignorés | 1 | 1 |

**Aucune régression.** Les 13 échecs sont les défauts du kit à corriger : ils
constituent la feuille de route des chantiers du brief.

Les deux erreurs `make lint` / `make typecheck` sont également préexistantes et
sans rapport avec les modifications ci-dessus :

- `evaluation.py:5` — `json` importé mais inutilisé, conséquence directe de
  `load_test_questions()` qui renvoie `[]` au lieu de lire le fichier.
- `sql/generator.py:31` — `Item "object" has no attribute "invoke"`.

---

## Reste à faire — chantiers du brief

Aucun de ces trois chantiers n'est entamé à ce stade.

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
