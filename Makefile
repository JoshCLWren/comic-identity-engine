.PHONY: help stop start-api start-worker restart-api restart-worker clean queue-clear queue-status queue-flush fresh

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

stop: ## Stop all services (API and worker)
	@echo "Stopping Comic Identity Engine services..."
	@docker compose stop api worker >/dev/null 2>&1 || true
	@-pkill -9 -f "cie-api" >/dev/null 2>&1 || true
	@-pkill -9 -f "cie-worker" >/dev/null 2>&1 || true
	@sleep 1
	@killall -9 cie-api >/dev/null 2>&1 || true
	@killall -9 cie-worker >/dev/null 2>&1 || true
	@sleep 1
	@echo "✓ All services stopped"

start-api: ## Start the API server
	@if lsof -ti:8000 > /dev/null 2>&1; then \
		echo "✗ Port 8000 already in use. Run 'make stop' first."; \
		exit 1; \
	fi
	@echo "Starting API server..."
	@nohup uv run cie-api > logs/api.log 2>&1 &
	@sleep 2
	@if pgrep -f "cie-api" > /dev/null; then \
		echo "✓ API started (http://localhost:8000)"; \
	else \
		echo "✗ API failed to start - check logs/api.log"; \
		exit 1; \
	fi

start-worker: ## Start the worker
	@if pgrep -f "cie-worker" > /dev/null; then \
		echo "✗ Worker already running. Run 'make stop' first."; \
		exit 1; \
	fi
	@echo "Starting worker..."
	@nohup uv run cie-worker > logs/worker.log 2>&1 &
	@sleep 2
	@if pgrep -f "cie-worker" > /dev/null; then \
		echo "✓ Worker started"; \
	else \
		echo "✗ Worker failed to start - check logs/worker.log"; \
		exit 1; \
	fi

restart-api: stop start-api ## Restart the API server
	@echo "✓ API restarted"

restart-worker: stop start-worker ## Restart the worker
	@echo "✓ Worker restarted"

restart: stop restart-api restart-worker ## Restart all services
	@echo "✓ All services restarted"

clean: ## Remove Python cache and build artifacts
	@echo "Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@rm -rf .pytest_cache .mypy_cache .ruff_cache
	@echo "✓ Cache files cleaned"

status: ## Show status of all services
	@echo "Comic Identity Engine Status:"
	@echo ""
	@if pgrep -f "cie-api" > /dev/null; then \
		echo "✓ API: Running (http://localhost:8000)"; \
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
	@echo ""
	@if lsof -ti:8000 > /dev/null 2>&1; then \
		echo "✓ Port 8000: In use"; \
	else \
		echo "✗ Port 8000: Available"; \
	fi

queue-status: ## Show job queue status
	@echo "Job Queue Status:"
	@echo ""
	@if docker compose ps redis | grep -q "Up"; then \
		queue_count=$$(docker compose exec -T redis redis-cli -n 0 LLEN "cie:local:queue" 2>/dev/null || echo "0"); \
		echo "Jobs in queue: $$queue_count"; \
		if [ "$$queue_count" != "0" ]; then \
			echo ""; \
			echo "Next 10 jobs:"; \
			docker compose exec -T redis redis-cli -n 0 LRANGE "cie:local:queue" 0 9 2>/dev/null || echo "Unable to fetch jobs"; \
		fi; \
	else \
		echo "✗ Redis not running - cannot check queue"; \
	fi

queue-clear: ## Clear all jobs from the worker queue
	@echo "Clearing job queue..."
	@if docker compose ps redis | grep -q "Up"; then \
		queue_count=$$(docker compose exec -T redis redis-cli -n 0 LLEN "cie:local:queue" 2>/dev/null || echo "0"); \
		if [ "$$queue_count" != "0" ]; then \
			echo "Found $$queue_count jobs in queue"; \
			read -p "Clear all jobs? [y/N] " confirm; \
			if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
				docker compose exec -T redis redis-cli -n 0 DEL "cie:local:queue" > /dev/null 2>&1; \
				docker compose exec -T redis redis-cli -n 0 DEL "arq:queue:cie:local:queue" > /dev/null 2>&1; \
				echo "✓ Queue cleared"; \
			else \
				echo "Cancelled"; \
			fi; \
		else \
			echo "✓ Queue is already empty"; \
		fi; \
	else \
		echo "✗ Redis not running - cannot clear queue"; \
		exit 1; \
	fi

queue-flush: ## Force flush all ARQ keys from Redis (use if queue-clear doesn't work)
	@echo "Flushing all ARQ data from Redis..."
	@if docker compose ps redis | grep -q "Up"; then \
		echo "This will delete ALL job queue data and results"; \
		read -p "Continue? [y/N] " confirm; \
		if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
			docker compose exec -T redis redis-cli -n 0 KEYS "arq:*" | xargs docker compose exec -T redis redis-cli -n 0 DEL 2>/dev/null; \
			docker compose exec -T redis redis-cli -n 0 DEL "cie:local:queue" > /dev/null 2>&1; \
			echo "✓ All ARQ data flushed"; \
		else \
			echo "Cancelled"; \
		fi; \
	else \
		echo "✗ Redis not running"; \
		exit 1; \
	fi

fresh: queue-clear stop ## Clear queue and stop services for fresh start
	@echo "Ready for fresh start - use 'make start-api' and 'make start-worker'"
