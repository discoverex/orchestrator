# Repository Guidelines

- `src` 레이아웃: `flows`(Prefect 실행), `runner`(repo checkout+entrypoint 실행), `storage`(아티팩트 API·저장), `deployments`(배포 등록).
- `cli` 사용: `cli e2e local [core|mlflow]`, `cli local up|down|ps|logs`, `cli storage up|down|ps|logs`, `cli register run|build`, `cli prefect <action> [--remote]`.
- Git 규칙: `.context/git-conventions.md` 준수(커밋 prefix, 브랜치 네이밍, one concern per commit).
- 문서 구조와 범위 기준: `docs/documentation-guide.md` 참조.
