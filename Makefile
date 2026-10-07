.PHONY: install dev up down logs pull-model db-shell

install:
	python -m venv .venv
	. .venv/bin/activate; pip install -r requirements.txt

dev:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

pull-model:
	docker exec -e OLLAMA_HOST=http://127.0.0.1:11434 yitetsuai_ollama ollama pull qwen2.5:0.5b
	docker exec -e OLLAMA_HOST=http://127.0.0.1:11434 yitetsuai_ollama ollama pull moondream

db-shell:
	docker exec -it yitetsuai_postgres psql -U yitetsu -d yitetsuai

test:
	ATTACHMENT_DIR=/tmp/yitetsuai-test-attachments .venv/bin/python -m unittest discover -s tests -v
