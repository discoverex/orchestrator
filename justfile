set shell := ["bash", "-cu"]

path := "."
line_limit := "200"

lint p=path:
    uv run ruff check {{p}}

format p=path:
    uv run ruff format {{p}}

type p=path:
    uv run mypy {{p}}

test p="tests":
    uv run pytest {{p}}

check p=path:
    just lint {{p}}
    just type {{p}}
    just test
    just linecheck

tree:
    git ls-files --cached --others --exclude-standard \
      | sed 's#^\./##' \
      | sort

linecheck:
    #!/usr/bin/env bash
    set -euo pipefail

    limit="{{line_limit}}"
    failed=0

    is_target_file() {
        local f="$1"
        local base

        base="$(basename "$f")"

        case "$f" in
            *.py|*.sh)
                return 0
                ;;
        esac

        if [[ "$base" != *.* ]]; then
            return 0
        fi

        return 1
    }

    check_file() {
        local f="$1"
        local lines

        [[ -f "$f" ]] || return 0
        is_target_file "$f" || return 0

        lines="$(wc -l < "$f")"
        if (( lines > limit )); then
            echo "ERROR: $f ($lines lines > $limit)"
            failed=1
        fi
    }

    while IFS= read -r f; do
        check_file "$f"
    done < <(git ls-files --cached)

    while IFS= read -r f; do
        check_file "$f"
    done < <(git ls-files --others --exclude-standard)

    if (( failed )); then
        echo "Line limit exceeded"
        exit 1
    fi