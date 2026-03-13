.PHONY: help stop start-api start-worker restart-api restart-worker clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

stop: ## Stop all services (API and worker)
	@echo "Stopping Comic Identity Engine services..."
	@if pgrep -f "cie-api" > /dev/null; then \
		pkill -f "cie-api" && echo "✓ Stopped API"; \
	else \
		echo "✓ API not running"; \
	fi
	@if pgrep -f "cie-worker" > /dev/null; then \
		pkill -f "cie-worker" && echo "✓ Stopped worker"; \
	else \
		echo "✓ Worker not running"; \
	fi
	@echo "All services stopped"

start-api: ## Start the API server
	@echo "Starting API server..."
	@uv run cie-api &

start-worker: ## Start the worker
	@echo "Starting worker..."
	@uv run cie-worker &

restart-api: stop start-api ## Restart the API server
	@echo "API restarted"

restart-worker: stop start-worker ## Restart the worker
	@echo "Worker restarted"

restart: stop restart-api restart-worker ## Restart all services
	@echo "All services restarted"

clean: ## Remove Python cache and build artifacts
	@echo "Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@rm -rf .pytest_cache .mypy_cache .ruff_cache
	@echo "Cache files cleaned"

status: ## Show status of all services
	@echo "Comic Identity Engine Status:"
	@echo ""
	@if pgrep -f "cie-api" > /dev/null; then \
		echo "✓ API: Running"; \
	else \
		echo "✗ API: Not running"; \
	fi
	@if pgrep -f "cie-worker" > /dev/null; then \
		echo "✓ Worker: Running"; \
	else \
		echo "✗ Worker: Not running"; \
	fi
	@echo ""
	@if docker compose ps postgres-app redis | grep -q "Up"; then \
		echo "✓ Infrastructure: Running (postgres, redis)"; \
	else \
		echo "✗ Infrastructure: Not running"; \
	fi
