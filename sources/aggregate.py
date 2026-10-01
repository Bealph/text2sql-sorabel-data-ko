"""Agrégation des enregistrements multi-sources en un référentiel unique.

Plusieurs sources décrivent les mêmes clients. L'agrégation produit un
enregistrement unique par client, en :

- regroupant sur ``external_id`` (insensible à la casse et aux espaces),
- conservant la version la plus **fraîche** (champ ``ingested_at``),
- **fusionnant** les champs : une valeur renseignée prime sur une valeur vide.

Fraîcheur et fusion sont deux règles distinctes. La fraîcheur ne départage que
lorsque les deux valeurs sont renseignées : un enregistrement récent dont un
champ est vide ne doit pas effacer la valeur d'un enregistrement plus ancien.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sources.base import parse_horodatage

# Rang attribué aux enregistrements sans horodatage exploitable : ils passent
# en dernier, mais ne sont jamais écartés. Aware UTC, comme tout le reste —
# comparer une date naïve à une date avec fuseau lèverait ``TypeError``.
_PLUS_ANCIEN = datetime.min.replace(tzinfo=timezone.utc)


def normalize_key(external_id: str) -> str:
    """Clé d'agrégation normalisée.

    ``" fr-001 "`` et ``"FR-001"`` désignent le même client.
    """
    return str(external_id).strip().lower()


def _fraicheur(record: dict[str, Any]) -> datetime:
    """Date d'ingestion comparable, ou ``_PLUS_ANCIEN`` si illisible."""
    return parse_horodatage(record.get("ingested_at")) or _PLUS_ANCIEN


def _est_renseigne(valeur: Any) -> bool:
    """Une chaîne vide ou blanche compte comme non renseignée."""
    if valeur is None:
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    return True


def _fusionner(groupe: list[dict[str, Any]]) -> dict[str, Any]:
    """Fond les versions d'un même client en un enregistrement unique."""
    # Du plus frais au plus ancien : la première valeur renseignée l'emporte.
    ordonnes = sorted(groupe, key=_fraicheur, reverse=True)

    fusion: dict[str, Any] = {}
    for record in ordonnes:
        for champ, valeur in record.items():
            if _est_renseigne(valeur) and not _est_renseigne(fusion.get(champ)):
                fusion[champ] = valeur

    # La clé normalisée fait foi : le référentiel consolidé ne conserve pas les
    # variantes d'écriture propres à chaque source.
    fusion["external_id"] = normalize_key(ordonnes[0]["external_id"])
    # Traçabilité : d'où vient l'enregistrement consolidé.
    fusion["sources"] = sorted({r["source"] for r in groupe if r.get("source")})
    return fusion


def aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fusionne les enregistrements multi-sources en une liste dédoublonnée."""
    groupes: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groupes.setdefault(normalize_key(record["external_id"]), []).append(record)

    # Ordre de sortie stable, pour que deux exécutions soient comparables.
    return [_fusionner(groupes[cle]) for cle in sorted(groupes)]
