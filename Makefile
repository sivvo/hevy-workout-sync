# Define the default action
.DEFAULT_GOAL := help

.PHONY: help install sync test export clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies and sync environment
	uv sync

test: ## Run tests with coverage
	uv run pytest --cov=. --cov-report=term-missing

export: ## Export clean requirements.txt without hashes or dev tools
	uv export --no-dev --no-hashes --no-annotate --output-file requirements.txt

clean: ## Remove temporary python and test files
	rm -rf .venv .pytest_cache .coverage htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} +