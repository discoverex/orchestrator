# Release Gates and Cutover (v1.0.0)

## Mandatory Gates
1. Lint:
   - `uvx ruff check .`
2. Test:
   - `uv run pytest`
3. Local E2E:
   - `./bin/project e2e core`
4. Remote E2E (record-preserving):
   - `./bin/project e2e-remote --prefect-api-url <URL> --prune-mode dry-run`

## Evidence Artifacts
- `artifacts/e2e/<stamp>/summary.json`
- `artifacts/e2e/<stamp>/steps.tsv`
- test logs for failed/flake reruns when applicable

## Cutover Checklist
1. Confirm deployments register successfully (`engine-run/*`).
2. Confirm production worker path used (no temp bootstrap dependency).
3. Confirm storage object verification and flush verification pass.
4. Confirm no unintended prune deletion in default run.

## Regression Watchlist
- Prefect API URL routing mismatch
- Worker queue / pool mismatch
- Storage token/auth errors
- Runtime path mount mismatch

## Exit Criteria
- All gates green on current `dev`.
- Release notes include architecture changes + explorer removal note.
- Tag preparation for `v1.0.0` ready.
