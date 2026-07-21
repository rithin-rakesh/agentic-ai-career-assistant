.PHONY: help dev test build up down logs backup migrate clean

help:
	@echo "Agentic AI Job Search Assistant - Command Interface"
	@echo "----------------------------------------------------"
	@echo "make dev       : Run local development server"
	@echo "make test      : Execute unit & integration test suite"
	@echo "make build     : Build Docker container images"
	@echo "make up        : Start all 8 services using Docker Compose"
	@echo "make down      : Stop and remove Docker Compose containers"
	@echo "make logs      : Tail logs across container cluster"
	@echo "make backup    : Generate database & memory backup archive"
	@echo "make migrate   : Run Alembic database migrations"
	@echo "make clean     : Remove temporary pycache and build artifacts"

dev:
	python app/main.py

test:
	pytest tests/ -v

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f --tail=100

backup:
	bash scripts/backup.sh

migrate:
	alembic upgrade head

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
