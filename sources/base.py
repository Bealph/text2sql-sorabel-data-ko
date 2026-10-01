"""Client HTTP et normalisation partagés par les connecteurs de sources.

Le retry sur ``429`` vit ici et non dans chaque connecteur : un quota est une
propriété du transport HTTP, pas de la source interrogée. Même logique pour la
normalisation des horodatages — le format de date fait partie du schéma commun.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

DEFAULT_TIMEOUT = 10.0
MAX_ESSAIS = 4

_log = logging.getLogger(__name__)


def build_client(base_url: str) -> httpx.Client:
    """Construit un client httpx pointant sur ``base_url``."""
    return httpx.Client(base_url=base_url, timeout=DEFAULT_TIMEOUT)


def parse_horodatage(valeur: Any) -> datetime | None:
    """Convertit un horodatage en ``datetime`` **aware UTC**, ou ``None``.

    Ramener toutes les dates au même référentiel est indispensable : comparer
    une date naïve et une date avec fuseau lève ``TypeError`` en Python, ce qui
    ferait échouer le tri par fraîcheur dès qu'une source change de format.

    Convention retenue : une date sans fuseau est **supposée UTC**. Aucune
    information ne permet d'en déduire autre chose ; le choix est arbitraire
    mais prévisible, donc documentable.
    """
    if not valeur:
        return None
    if isinstance(valeur, datetime):
        date = valeur
    else:
        try:
            date = datetime.fromisoformat(str(valeur).strip().replace("Z", "+00:00"))
        except ValueError:
            # Ni deviné, ni avalé en silence : la donnée est conservée en
            # l'état par l'appelant, mais l'anomalie est tracée.
            _log.warning("horodatage illisible, ignoré pour le tri : %r", valeur)
            return None

    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc)


def iso_utc(valeur: Any) -> Any:
    """Horodatage normalisé en ISO 8601 UTC ; valeur d'origine si illisible."""
    date = parse_horodatage(valeur)
    return date.isoformat() if date else valeur


def _est_quota_depasse(exc: BaseException) -> bool:
    """Vrai uniquement pour un ``429`` — les autres erreurs ne sont pas réessayées."""
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code == httpx.codes.TOO_MANY_REQUESTS
    )


@retry(
    retry=retry_if_exception(_est_quota_depasse),
    stop=stop_after_attempt(MAX_ESSAIS),
    wait=wait_exponential(multiplier=0.2, max=2),
    reraise=True,
)
def get_json(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> Any:
    """Récupère et décode une réponse JSON, en réessayant sur ``429``.

    Un ``429`` persistant au-delà de ``MAX_ESSAIS`` est **relevé** : mieux vaut
    une erreur explicite qu'une collecte silencieusement incomplète.
    """
    response = client.get(path, params=params)
    response.raise_for_status()
    return response.json()
