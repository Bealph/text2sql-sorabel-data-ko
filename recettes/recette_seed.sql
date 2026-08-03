-- Recette du seed — base de démonstration Sorabel
--
-- Usage : ouvrir dans DBeaver sur la connexion pointant la base « sorabel »
-- (jdbc:postgresql://localhost:5433/sorabel) puis exécuter le script entier
-- (Alt+X). Une ligne par contrôle, avec verdict OK / ECHEC.
--
-- Équivalent en ligne de commande :
--   docker compose exec -T db psql -U sorabel -d sorabel -f - < recettes/recette_seed.sql
--
-- Référence des valeurs attendues : seed.py et data/questions_test.json.

WITH controles AS (

    -- ---------------------------------------------------------------
    -- 0. Contexte — le piège classique : être connecté à la base
    --    « postgres » au lieu de « sorabel ». Tout le reste échoue
    --    en cascade si ce contrôle échoue.
    -- ---------------------------------------------------------------
    SELECT 1 AS ordre,
           '0. Contexte' AS famille,
           'base courante' AS controle,
           'sorabel' AS attendu,
           current_database() AS obtenu

    -- ---------------------------------------------------------------
    -- 1. Structure — les quatre tables existent
    -- ---------------------------------------------------------------
    UNION ALL SELECT 2, '1. Structure', 'table clients', 'présente',
           CASE WHEN to_regclass('public.clients') IS NULL THEN 'absente' ELSE 'présente' END
    UNION ALL SELECT 3, '1. Structure', 'table produits', 'présente',
           CASE WHEN to_regclass('public.produits') IS NULL THEN 'absente' ELSE 'présente' END
    UNION ALL SELECT 4, '1. Structure', 'table commandes', 'présente',
           CASE WHEN to_regclass('public.commandes') IS NULL THEN 'absente' ELSE 'présente' END
    UNION ALL SELECT 5, '1. Structure', 'table lignes_commande', 'présente',
           CASE WHEN to_regclass('public.lignes_commande') IS NULL THEN 'absente' ELSE 'présente' END

    -- ---------------------------------------------------------------
    -- 2. Cardinalités — volumes chargés par seed.py
    -- ---------------------------------------------------------------
    UNION ALL SELECT 6, '2. Cardinalités', 'nb clients', '3',
           (SELECT count(*)::text FROM clients)
    UNION ALL SELECT 7, '2. Cardinalités', 'nb produits', '2',
           (SELECT count(*)::text FROM produits)
    UNION ALL SELECT 8, '2. Cardinalités', 'nb commandes', '4',
           (SELECT count(*)::text FROM commandes)
    UNION ALL SELECT 9, '2. Cardinalités', 'nb lignes_commande', '3',
           (SELECT count(*)::text FROM lignes_commande)

    -- ---------------------------------------------------------------
    -- 3. Jeu de référence — les quatre valeurs attendues par
    --    data/questions_test.json. Ce sont elles que l'agent devra
    --    retrouver : si la recette échoue ici, inutile de chercher
    --    le bug côté Text-to-SQL.
    -- ---------------------------------------------------------------
    UNION ALL SELECT 10, '3. Jeu de référence', 'Combien de commandes ?', '4',
           (SELECT count(*)::text FROM commandes)
    UNION ALL SELECT 11, '3. Jeu de référence', 'Chiffre d''affaires total', '425.0',
           -- cast en numeric : comparer des float en texte est instable
           (SELECT round(sum(montant)::numeric, 1)::text FROM commandes)
    UNION ALL SELECT 12, '3. Jeu de référence', 'Combien de clients actifs ?', '2',
           (SELECT count(*)::text FROM clients WHERE actif)
    UNION ALL SELECT 13, '3. Jeu de référence', 'Villes distinctes', '2',
           (SELECT count(DISTINCT ville)::text FROM clients)

    -- ---------------------------------------------------------------
    -- 4. Intégrité référentielle — aucune ligne orpheline.
    --    Les FK sont déclarées dans db.py, mais un seed partiel ou
    --    rejoué à moitié peut laisser des incohérences.
    -- ---------------------------------------------------------------
    UNION ALL SELECT 14, '4. Intégrité', 'commandes sans client', '0',
           (SELECT count(*)::text FROM commandes c
             LEFT JOIN clients cl ON cl.id = c.client_id
            WHERE cl.id IS NULL)
    UNION ALL SELECT 15, '4. Intégrité', 'lignes sans commande', '0',
           (SELECT count(*)::text FROM lignes_commande l
             LEFT JOIN commandes c ON c.id = l.commande_id
            WHERE c.id IS NULL)
    UNION ALL SELECT 16, '4. Intégrité', 'lignes sans produit', '0',
           (SELECT count(*)::text FROM lignes_commande l
             LEFT JOIN produits p ON p.id = l.produit_id
            WHERE p.id IS NULL)

    -- ---------------------------------------------------------------
    -- 5. Cohérence métier — valeurs aberrantes
    -- ---------------------------------------------------------------
    UNION ALL SELECT 17, '5. Cohérence', 'montants négatifs ou nuls', '0',
           (SELECT count(*)::text FROM commandes WHERE montant <= 0)
    UNION ALL SELECT 18, '5. Cohérence', 'quantités négatives ou nulles', '0',
           (SELECT count(*)::text FROM lignes_commande WHERE quantite <= 0)
    UNION ALL SELECT 19, '5. Cohérence', 'prix unitaires négatifs ou nuls', '0',
           (SELECT count(*)::text FROM produits WHERE prix_unitaire <= 0)
    UNION ALL SELECT 20, '5. Cohérence', 'raisons sociales en double', '0',
           (SELECT count(*)::text FROM (
                SELECT raison_sociale FROM clients
                 GROUP BY raison_sociale HAVING count(*) > 1
            ) d)
)
SELECT famille,
       controle,
       attendu,
       obtenu,
       CASE WHEN obtenu = attendu THEN 'OK' ELSE '>>> ECHEC' END AS verdict
  FROM controles
 ORDER BY ordre;


-- ===================================================================
-- Verdict global — une seule ligne, pour un coup d'œil rapide.
-- Décommenter et exécuter séparément si besoin.
-- ===================================================================
-- SELECT CASE
--          WHEN current_database() <> 'sorabel'
--            THEN '>>> ECHEC — mauvaise base : ' || current_database()
--          WHEN (SELECT count(*) FROM clients) = 3
--           AND (SELECT count(*) FROM produits) = 2
--           AND (SELECT count(*) FROM commandes) = 4
--           AND (SELECT count(*) FROM lignes_commande) = 3
--           AND (SELECT round(sum(montant)::numeric, 1) FROM commandes) = 425.0
--            THEN 'OK — seed conforme'
--          ELSE '>>> ECHEC — voir le détail ci-dessus'
--        END AS verdict_global;
