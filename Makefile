SHELL := /bin/bash

.PHONY: backend frontend dev ui-install ui-test api-test

backend:
	source .venv/bin/activate && python -m uvicorn app.main:app --reload

frontend:
	cd frontend && npm run dev

dev:
	./scripts/dev.sh

ui-install:
	cd frontend && npm install

ui-test:
	cd frontend && npm run test:run

api-test:
	source .venv/bin/activate && pytest -q
