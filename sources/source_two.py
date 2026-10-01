"""Connecteur source 2 — référentiel clients hérité (legacy).

L'API est paginée : chaque réponse a la forme
``{"items": [...], "next_cursor": "<curseur ou null>"}``.
Les enregistrements bruts utilisent d'autres noms de champs que la source 1 :
``{"ref", "label", "town", "ts"}``.
"""

from __future__ import annotations

from typing import Any

import httpx

from sources.base import get_json, iso_utc


MAX_PAGES = 100


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Projette un enregistrement brut vers le schéma commun."""
    return {
        "external_id": str(raw["ref"]),
        "raison_sociale": raw["label"],
        "ville": raw["town"],
        "ingested_at": iso_utc(raw["ts"]),
        "source": "source_two",
    }


def fetch_all(client: httpx.Client) -> list[dict[str, Any]]:
    """Récupère **tous** les enregistrements, en suivant la pagination.

    Le curseur est suivi jusqu'à ``next_cursor`` nul. Deux bornes évitent la
    boucle infinie si l'API renvoie un curseur incohérent : les curseurs déjà
    visités et un plafond de pages.
    """
    enregistrements: list[dict[str, Any]] = []
    curseur = ""
    vus: set[str] = {curseur}

    for _ in range(MAX_PAGES):
        payload = get_json(client, "/clients", params={"cursor": curseur})
        enregistrements.extend(normalize(item) for item in payload["items"])

        suivant = payload.get("next_cursor")
        if not suivant or suivant in vus:
            break
        vus.add(suivant)
        curseur = suivant

    return enregistrements
