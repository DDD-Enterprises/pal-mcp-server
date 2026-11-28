# Repository Guidelines

See `requirements.txt` and `requirements-dev.txt`

Also read CLAUDE.md and CLAUDE.local.md if available.

## Project Structure & Module Organization
PAL MCP Server centers on `server.py`, which exposes MCP entrypoints and coordinates multi-model workflows. 
Feature-specific tools live in `tools/`, provider integrations in `providers/`, and shared helpers in `utils/`. 
Prompt and system context assets stay in `systemprompts/`, while configuration templates and automation scripts live under `conf/`, `scripts/`, and `docker/`. 
Unit tests sit in `tests/`; simulator-driven scenarios and log utilities are in `simulator_tests/` with the `communication_simulator_test.py` harness. 
Authoritative documentation and samples live in `docs/`, and runtime diagnostics are rotated in `logs/`.

## Build, Test, and Development Commands
- `source .pal_venv/bin/activate` – activate the managed Python environment.
- `./run-server.sh` – install dependencies, refresh `.env`, and launch the MCP server locally.
- `./code_quality_checks.sh` – run Ruff autofix, Black, isort, and the default pytest suite.
- `python communication_simulator_test.py --quick` – smoke-test orchestration across tools and providers.
- `./run_integration_tests.sh [--with-simulator]` – exercise provider-dependent flows against remote or Ollama models.

Run code quality checks:
```bash
.pal_venv/bin/activate && ./code_quality_checks.sh
```

For example, this is how we run an individual / all tests:

```bash
.pal_venv/bin/activate && pytest tests/test_auto_mode_model_listing.py -q
.pal_venv/bin/activate && pytest -q
```

## Coding Style & Naming Conventions
Target Python 3.9+ with Black and isort using a 120-character line limit; Ruff enforces pycodestyle, pyflakes, bugbear, comprehension, and pyupgrade rules. Prefer explicit type hints, snake_case modules, and imperative commit-time docstrings. Extend workflows by defining hook or abstract methods instead of checking `hasattr()`/`getattr()`—inheritance-backed contracts keep behavior discoverable and testable.

## Testing Guidelines
Mirror production modules inside `tests/` and name tests `test_<behavior>` or `Test<Feature>` classes. Run `python -m pytest tests/ -v -m "not integration"` before every commit, adding `--cov=. --cov-report=html` for coverage-sensitive changes. Use `python communication_simulator_test.py --verbose` or `--individual <case>` to validate cross-agent flows, and reserve `./run_integration_tests.sh` for provider or transport modifications. Capture relevant excerpts from `logs/mcp_server.log` or `logs/mcp_activity.log` when documenting failures.

## Commit & Pull Request Guidelines
Follow Conventional Commits: `type(scope): summary`, where `type` is one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, or `chore`. Keep commits focused, referencing issues or simulator cases when helpful. Pull requests should outline intent, list validation commands executed, flag configuration or tool toggles, and attach screenshots or log snippets when user-visible behavior changes.

## GitHub CLI Commands
The GitHub CLI (`gh`) streamlines issue and PR management directly from the terminal.

### Viewing Issues
```bash
# View issue details in current repository
gh issue view <issue-number>

# View issue from specific repository
gh issue view <issue-number> --repo owner/repo-name

# View issue with all comments
gh issue view <issue-number> --comments

# Get issue data as JSON for scripting
gh issue view <issue-number> --json title,body,author,state,labels,comments

# Open issue in web browser
gh issue view <issue-number> --web
```

### Managing Issues
```bash
# List all open issues
gh issue list

# List issues with filters
gh issue list --label bug --state open

# Create a new issue
gh issue create --title "Issue title" --body "Description"

# Close an issue
gh issue close <issue-number>

# Reopen an issue
gh issue reopen <issue-number>
```

### Pull Request Operations
```bash
# View PR details
gh pr view <pr-number>

# List pull requests
gh pr list

# Create a PR from current branch
gh pr create --title "PR title" --body "Description"

# Check out a PR locally
gh pr checkout <pr-number>

# Merge a PR
gh pr merge <pr-number>
```

Install GitHub CLI: `brew install gh` (macOS) or visit https://cli.github.com for other platforms.

## Security & Configuration Tips
Store API keys and provider URLs in `.env` or your MCP client config; never commit secrets or generated log artifacts. Use `run-server.sh` to regenerate environments and verify connectivity after dependency changes. When adding providers or tools, sanitize prompts and responses, document required environment variables in `docs/`, and update `claude_config_example.json` if new capabilities ship by default.

## Cost-aware delegation

- Supervisors and executing models should split suitable independent work when delegation tools support it and the benefit exceeds the extra context and coordination cost. Use the least expensive capable available model and lowest sufficient supported reasoning effort for bounded mechanical work, extraction, routine tests, documentation, and straightforward implementation. Use current repository routing guidance and runner/account availability; do not assume a permanent model or price ranking.
- Keep architecture, ambiguous reasoning, security-sensitive changes, and final synthesis with a sufficiently capable supervisor or specialist. Give each worker narrow context, explicit scope and file ownership, a deliverable, and acceptance checks. Preserve one-writer rules and required independent audits.
- Verify delegated outputs and relevant checks before accepting them. Escalate the unresolved slice on demonstrated complexity, uncertainty, or failed validation, recording the reason within existing call/retry limits. Honor pinned models, runners, providers, effort, session freshness, approval, and no-fallback requirements; no hidden upgrades or retries.
- Do trivial tasks and deterministic checks directly when an agent would add overhead. If the runner lacks subagents or per-agent model selection, state that limitation and perform otherwise authorized work directly; never invent delegation or unsupported controls.
- This policy grants no additional execution, spending, credential, or mutation authority and does not lower safety, permission, quality, or validation requirements. Mark unverified availability, cost, and actual execution identity as `UNKNOWN`; do not claim observed models or savings without evidence.
