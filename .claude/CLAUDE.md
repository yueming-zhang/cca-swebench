# Project Conventions

## Python Environment

Virtual environment is at `.venv`. Always use it for pytest and CLI commands:

```bash
.venv/bin/python -m pytest
.venv/bin/python <script.py>
```

## Testing

### Unit Tests (`my_agents/tests/unit/`)
- Always create unit tests for new code
- Must run locally with zero external dependencies: no AWS, no cloud, no LLM calls
- Mock any external services

### Integration Tests (`my_agents/tests/integration/`)
- Always create integration tests for new code
- No mocking — use real external services (AWS, LLM, cloud)

## Version Control

Use **Sapling** (`sl`), not `git`.
