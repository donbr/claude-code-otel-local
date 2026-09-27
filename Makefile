.PHONY: init preflight up down logs verify verify-settings verify-claude

init:
	bash scripts/init-env.sh

# Skip the port check when this project's containers are already running (they hold the ports).
preflight:
	@if [ -n "$$(docker compose ps -q --status running 2>/dev/null)" ]; then \
	  python3 scripts/preflight.py --skip-ports; else python3 scripts/preflight.py; fi

up: preflight
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f otel-collector
verify:
	uv run pytest tests/offline tests/smoke -v

verify-settings:
	uv run pytest tests/settings -v

verify-claude:
	RUN_CLAUDE_CLI=1 uv run pytest tests/claude -v
