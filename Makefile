.PHONY: help up down logs migrate seed shell backend-test agent-test cli-test test lint fmt build

help:
	@echo "NodePilot -- common development targets:"
	@echo "  make up             Start the docker-compose dev stack"
	@echo "  make down           Stop the dev stack"
	@echo "  make logs           Tail logs from the dev stack"
	@echo "  make migrate        Run Django migrations inside the web container"
	@echo "  make seed           Seed the RBAC permission catalog"
	@echo "  make shell          Open a Django shell inside the web container"
	@echo "  make backend-test   Run backend/ pytest suite (host Python, sqlite)"
	@echo "  make agent-test     Run agent/ pytest suite"
	@echo "  make cli-test       Run cli/ pytest suite"
	@echo "  make test           Run all three test suites"

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec nodepilot-web python manage.py migrate

seed:
	docker compose exec nodepilot-web python manage.py seed_rbac

shell:
	docker compose exec nodepilot-web python manage.py shell

backend-test:
	cd backend && DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest

agent-test:
	cd agent && python -m pytest

cli-test:
	cd cli && python -m pytest

test: backend-test agent-test cli-test
