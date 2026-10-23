# MudaleTunnel — development shortcuts.

.PHONY: dev test lint build up down migrate shell logs clean

dev:  ## Start dev backing services (Postgres + Redis) for local development
	docker compose -f docker-compose.dev.yml up -d

test:  ## Run backend tests and frontend type-check
	cd backend && uv run pytest -q
	cd frontend && npx tsc --noEmit

lint:  ## Lint backend (ruff) and frontend (tsc)
	cd backend && uv run ruff check .
	cd frontend && npx tsc --noEmit

build:  ## Build docker images
	docker compose build

up:  ## Build and start all services in the background
	docker compose up -d --build

down:  ## Stop all services
	docker compose down

migrate:  ## Run Django migrations inside the web container
	docker compose exec web python manage.py migrate

shell:  ## Open a Django shell inside the web container
	docker compose exec web python manage.py shell

logs:  ## Tail logs from all services
	docker compose logs -f

clean:  ## Stop all services and remove volumes (DESTROYS DATA)
	docker compose down -v
