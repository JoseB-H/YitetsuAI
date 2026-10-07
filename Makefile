.PHONY: install dev up down logs pull-model db-shell

install:
	python -m venv .venv
	. .venv/bin/activate; pip install -r requirements.txt

dev:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

up:
	docker-compose up -d --build

down:
	docker-compose down -v

logs:
	docker-compose logs -f

pull-model:
	docker exec yitetsuai_ollama ollama pull llama2

db-shell:
	docker exec -it yitetsuai_postgres psql -U yitetsu -d yitetsuai
