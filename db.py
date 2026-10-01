"""Schéma SQLAlchemy de la base de démonstration Sorabel et fabrique d'engine.

Sorabel est un distributeur B2B. La base expose quatre tables :

- ``clients``         : comptes clients (id, raison sociale, ville, actif)
- ``produits``        : catalogue (id, libellé, prix unitaire)
- ``commandes``       : commandes passées (id, client_id, date, montant)
- ``lignes_commande`` : détail des lignes (commande_id, produit_id, quantite)
"""

from __future__ import annotations

import os

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)

metadata = MetaData()

clients = Table(
    "clients",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("raison_sociale", String(200), nullable=False),
    Column("ville", String(120), nullable=False),
    Column("actif", Boolean, nullable=False, default=True),
)

produits = Table(
    "produits",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("libelle", String(200), nullable=False),
    Column("prix_unitaire", Float, nullable=False),
)

commandes = Table(
    "commandes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("client_id", Integer, ForeignKey("clients.id"), nullable=False),
    Column("date_commande", Date, nullable=False),
    Column("montant", Float, nullable=False),
)

lignes_commande = Table(
    "lignes_commande",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("commande_id", Integer, ForeignKey("commandes.id"), nullable=False),
    Column("produit_id", Integer, ForeignKey("produits.id"), nullable=False),
    Column("quantite", Integer, nullable=False),
)


def engine_from_env(env_var: str = "DB_URL"):
    url = os.environ.get(env_var)
    if not url:
        raise RuntimeError(f"Variable d'environnement {env_var!r} non définie.")
    return create_engine(url, future=True)


def agent_engine():
    """Engine destiné à l'agent : rôle en lecture seule.

    Retombe sur ``DB_URL`` si ``AGENT_DB_URL`` n'est pas défini, pour que le
    projet reste utilisable avant ``make roles`` — au prix de la protection
    moteur. Voir ``roles.py``.
    """
    if os.environ.get("AGENT_DB_URL"):
        return engine_from_env("AGENT_DB_URL")
    return engine_from_env("DB_URL")
