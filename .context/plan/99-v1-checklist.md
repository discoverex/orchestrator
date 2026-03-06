# v1.0.0 Master Checklist

## Phase Status
- [ ] Phase 1 - src hexagonal refactor complete
- [ ] Phase 2 - scripts/bin modularization complete
- [ ] Phase 3 - pytest reorganization complete
- [ ] Phase 4 - docs refresh complete
- [ ] Phase 5 - release gates complete

## Functional Invariants
- [ ] `bin/project` CLI contract preserved
- [ ] `bin/remote` CLI contract preserved
- [ ] Prefect register/run flow operational
- [ ] Storage verification operational

## Architecture Invariants
- [ ] Domain/application/ports/adapters boundaries enforced
- [ ] Explorer package/routes/env removed
- [ ] No unapproved large mixed-responsibility files remain

## Test & Validation
- [ ] `uvx ruff check .`
- [ ] `uv run pytest`
- [ ] `./bin/project e2e core`
- [ ] `./bin/project e2e-remote --prefect-api-url <URL> --prune-mode dry-run`

## Release Readiness
- [ ] Docs updated and path-accurate
- [ ] Ops runbooks validated with current commands
- [ ] Merge to `dev` completed with `--no-ff`
- [ ] v1.0.0 tag checklist ready
