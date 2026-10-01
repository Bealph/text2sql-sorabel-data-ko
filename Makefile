.PHONY: install up down seed roles chat ui test fmt lint typecheck

install:
	uv sync

up:
	docker compose up -d

down:
	docker compose down

seed:
	uv run python seed.py

roles:
	uv run python roles.py

chat:
	uv run python -m agent.chat

ui:
	uv run streamlit run ui/app.py

test:
	uv run pytest -v

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy agent sql sources
