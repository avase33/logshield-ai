.PHONY: install dev test lint demo bench serve infra docker clean

install:
	pip install -e .

dev:
	pip install -e ".[serve,dev,bench]"

test:
	pytest --cov=logshield --cov-report=term-missing

lint:
	ruff check logshield scripts

demo:
	python -m logshield demo --count 5000

bench:
	python -m logshield bench --count 50000

serve:
	logshield serve

infra:
	docker compose -f docker-compose.infra.yml up --build

docker:
	docker build -t logshield-ai:latest .

clean:
	rm -f logshield.db *.log
	rm -rf .pytest_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
