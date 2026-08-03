"""Fabrique du modèle de chat hébergé sur Azure AI Foundry.

Les variables ``AZURE_AI_INFERENCE_*`` sont lues dans l'environnement : c'est
au point d'entrée (``seed.py``, ``agent/chat.py``, ``ui/app.py``) d'avoir
chargé le ``.env`` au préalable, pas à ce module.

Le déploiement expose une route **OpenAI-compatible** (``/openai/v1``) qui
rejette le paramètre ``api-version`` :

    400 BadRequest — "API version not supported"

``AzureAIChatCompletionsModel`` ajoute ce paramètre d'office et ne permet pas
de le retirer (``default_query={}`` reste sans effet). On passe donc par
``ChatOpenAI`` avec ``base_url``, qui parle le même protocole sans ce
paramètre.
"""

from __future__ import annotations

import os


def get_llm():
    """Instancie le client de chat pointant sur le déploiement Azure."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=os.environ["AZURE_AI_INFERENCE_ENDPOINT"],
        api_key=os.environ["AZURE_AI_INFERENCE_API_KEY"],
        model=os.environ.get("AZURE_AI_INFERENCE_MODEL", "gpt-5.4-mini"),
    )
