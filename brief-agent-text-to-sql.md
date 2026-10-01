# [BR] L'agent qui interroge mal (Text-to-SQL & agrégation multi-sources)

**Assigné**
FR / EA — Elbby Skermine AGWU
créé : 06/07/26

## Référentiels
- [2023] Certification RNCP Développeur.se en intelligence artificielle
- Compétences transversales

## Ressources
- Repository

## Contexte du projet

Chez Sorabel, l'agent renvoie des chiffres faux : ses requêtes SQL générées sont parfois invalides ou dangereuses, et la collecte multi-sources mélange des doublons et des données périmées. Vous réparez le lien entre l'agent et les données.

## Modalités pédagogiques

Travail en binôme. 2 jours

## Travail préliminaire de conception

### 1 - Diagnostiquer les requêtes générées

À partir des questions de test fournies, l'apprenant sera capable de définir le périmètre du problème en identifiant les requêtes générées qui échouent ou sont risquées.

- Relever les requêtes invalides / dangereuses et leur cause.
- Produire une note de diagnostic + un schéma du flux donnée (agent → SQL / sources → réponse).

**Critères d'évaluation**
- Les requêtes problématiques et leurs causes sont identifiées.
- La note et le schéma sont produits et validés.

### 2 - Concevoir les garde-fous SQL et la stratégie de fiabilisation

À partir du diagnostic, l'apprenant sera capable de concevoir les garde-fous SQL (lecture seule, validation, périmètre des tables) et la stratégie de fiabilisation de l'agrégation.

- Définir les garde-fous SQL.
- Localiser l'origine des doublons / données périmées et la stratégie de correction.
- Définir la vérification d'exactitude sur le jeu de test.

**Critères d'évaluation**
- Les garde-fous et la stratégie sont explicites et justifiés.

## Développement

### 3 - Concevoir une génération Text-to-SQL sécurisée

À partir de la base de démonstration, l'apprenant sera capable de concevoir une génération Text-to-SQL valide et sécurisée (lecture seule, validation, périmètre).

- Corriger la génération Text-to-SQL.
- Poser les garde-fous (lecture seule, validation, périmètre des tables).

**Critères d'évaluation**
- Les requêtes générées sont valides et sûres (lecture seule, périmètre respecté).

### 4 - Fiabiliser l'agrégation multi-sources

À partir des sources simulées, l'apprenant sera capable de fiabiliser l'agrégation multi-sources (dédoublonnage, fraîcheur).

- Dédoublonner.
- Garantir la fraîcheur des données.

**Critères d'évaluation**
- L'agrégation ne contient plus de doublons ni de données périmées.

### 5 - Vérifier l'exactitude et documenter

À partir des questions de test fournies, l'apprenant sera capable de vérifier l'exactitude des réponses et de documenter cause et correctifs.

- Vérifier l'exactitude sur le jeu de test.
- Consigner cause et correctifs dans un journal.

**Critères d'évaluation**
- Les réponses chiffrées sont exactes sur le jeu de test.
- Le journal explique cause et correctifs.

## Modalités d'évaluation
- Validation de la note de diagnostic (porte d'entrée).
- Revue de PR + vérification d'exactitude sur le jeu de test.

## Livrables
- Note de diagnostic + schéma.
- PR : Text-to-SQL corrigé et sécurisé, agrégation fiabilisée.
- Journal des corrections.

## Critères de performance
- Les requêtes générées sont valides et sûres (lecture seule, périmètre respecté).
- Les réponses chiffrées sont exactes sur le jeu de test.
- L'agrégation ne contient plus de doublons ni de données périmées.

## Situation professionnelle
Connecter les agents aux données de l'entreprise, de façon sécurisée

## Besoin visé ou problème rencontré
Un agent utile reste coupé des données de l'entreprise : bases SQL, sources multiples, base de connaissances. Il faut le brancher — proprement et sans tout exposer. La mission consiste à connecter l'agent aux données (SQL, multi-sources, RAG avancé) et à l'ouvrir au monde via MCP, de façon sécurisée.

## Compétences visées (18 au total)
- C3. Définir le périmètre d'un problème rencontré en adoptant une démarche inductive (niveau 1 imiter / niveau 2 adapter / niveau 3 transposer)
- C4. Rechercher de façon méthodique une ou des solutions au problème rencontré (niveau 1 imiter / niveau 2 adapter / niveau 3 transposer)
- C1. Automatiser l'extraction de données (niveau 1 imiter / niveau 2 adapter / niveau 3 transposer)
- ... (+ 3 autres compétences affichées sur la page d'origine)
