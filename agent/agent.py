"""Agent Sorabel — LangChain branché sur le LLM Kimi-K2.6 (Azure AI)."""

from __future__ import annotations

from agent.llm import get_llm
from agent.tools import aggregate_clients, run_sql_query

SYSTEM_PROMPT = """Tu es l'assistant interne de Sorabel, distributeur B2B. Tu
réponds aux questions en interrogeant la base via les outils mis à ta
disposition. Réponds en français, de manière sourcée (indique la table ou la
source utilisée). Si une question ne peut pas être satisfaite avec les outils,
dis-le plutôt que d'inventer.
"""


def build_agent():
    """Construit l'agent avec ses outils."""
    from langchain.agents import create_agent

    llm = get_llm()
    tools = [run_sql_query, aggregate_clients]
    return create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
