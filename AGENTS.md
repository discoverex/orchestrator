# Repository Guidelines

- `src` 레이아웃: `flows`(Prefect 실행), `runner`(repo checkout+entrypoint 실행), `storage`/`storage_gateway`(아티팩트 API·저장), `deployments`(배포 등록).
- `project` 사용: `project e2e [core|mlflow|full]`, `project local up|down|ps|logs`, `project storage up|down|ps|logs`, `project register run|build`.
- Git 규칙: `.context/git-conventions.md` 준수(커밋 prefix, 브랜치 네이밍, one concern per commit).
