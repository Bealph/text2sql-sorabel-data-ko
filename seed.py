"""Alimente la base de démonstration Sorabel (tables + données d'exemple).

Usage : ``make seed`` (après ``make up``).
"""

from __future__ import annotations

from datetime import date

from dotenv import load_dotenv

from db import clients, commandes, engine_from_env, lignes_commande, metadata, produits

CLIENTS = [
    {"id": 1, "raison_sociale": "Acme SAS", "ville": "Lyon", "actif": True},
    {"id": 2, "raison_sociale": "Globex SARL", "ville": "Paris", "actif": True},
    {"id": 3, "raison_sociale": "Initech SA", "ville": "Lyon", "actif": False},
]

PRODUITS = [
    {"id": 1, "libelle": "Vis inox M6", "prix_unitaire": 2.0},
    {"id": 2, "libelle": "Boulon M6", "prix_unitaire": 1.5},
]

COMMANDES = [
    {"id": 1, "client_id": 1, "date_commande": date(2024, 1, 10), "montant": 100.0},
    {"id": 2, "client_id": 1, "date_commande": date(2024, 2, 5), "montant": 50.0},
    {"id": 3, "client_id": 2, "date_commande": date(2024, 2, 20), "montant": 200.0},
    {"id": 4, "client_id": 2, "date_commande": date(2024, 3, 1), "montant": 75.0},
]

LIGNES = [
    {"id": 1, "commande_id": 1, "produit_id": 1, "quantite": 30},
    {"id": 2, "commande_id": 1, "produit_id": 2, "quantite": 20},
    {"id": 3, "commande_id": 3, "produit_id": 1, "quantite": 50},
]


def main() -> None:
    load_dotenv()
    engine = engine_from_env("DB_URL")
    metadata.drop_all(engine)
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(clients.insert(), CLIENTS)
        conn.execute(produits.insert(), PRODUITS)
        conn.execute(commandes.insert(), COMMANDES)
        conn.execute(lignes_commande.insert(), LIGNES)
    print("Base de démonstration alimentée.")


if __name__ == "__main__":
    main()
