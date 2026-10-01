"""REPL minimal pour discuter avec l'agent Sorabel : ``python -m agent.chat``."""

from __future__ import annotations

from dotenv import load_dotenv

from agent.agent import build_agent


def main() -> None:
    load_dotenv()
    agent = build_agent()
    print("Assistant Sorabel — pose ta question (Ctrl-D pour quitter).")
    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            print()
            break
        if not question:
            continue
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
        messages = result.get("messages", [])
        if messages:
            print(getattr(messages[-1], "content", messages[-1]))


if __name__ == "__main__":
    main()
