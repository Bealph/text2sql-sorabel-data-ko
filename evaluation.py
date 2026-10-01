"""Chargement du jeu de questions de référence (Q + SQL attendu + valeur)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUESTIONS_PATH = Path(__file__).parent / "data" / "questions_test.json"


def load_test_questions() -> list[dict[str, Any]]:
    """Renvoie la liste des questions de référence à vérifier."""
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
