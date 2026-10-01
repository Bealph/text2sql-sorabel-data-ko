"""Connecteur source 1 — CRM produits (référentiel clients côté commercial).

Renvoie une liste simple d'enregistrements clients au format :
``{"external_id", "raison_sociale", "ville", "maj"}``.
"""

from __future__ import annotations

from typing import Any

import httpx

from sources.base import get_json, iso_utc

COMMON_KEYS = {"external_id", "raison_sociale", "ville", "ingested_at", "source"}


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Projette un enregistrement brut vers le schéma commun."""
    return {
        "external_id": str(raw["external_id"]),
        "raison_sociale": raw["raison_sociale"],
        "ville": raw["ville"],
        "ingested_at": iso_utc(raw["maj"]),
        "source": "source_one",
    }


def fetch_all(client: httpx.Client) -> list[dict[str, Any]]:
    """Récupère tous les enregistrements de la source 1."""
    rows = get_json(client, "/clients")
    return [normalize(row) for row in rows]
