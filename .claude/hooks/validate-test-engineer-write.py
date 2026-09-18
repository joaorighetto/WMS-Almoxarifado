#!/usr/bin/env python3
"""PreToolUse hook: restrict test-engineer's Edit/Write to test files only.

Exit 0  -> allow the write.
Exit 2  -> block the write (stderr explains why).

Policy: ALLOWLIST, not a blocklist. A path is allowed only if it is
structurally recognizable as a test file or as something that lives inside
a `tests/` directory. Anything else — including a path we simply cannot
resolve or classify with confidence — is blocked. Fail closed.

This is a guardrail against the test-engineer agent editing production code,
config, or docs by mistake or overreach. It is not a general filesystem
sandbox.
"""

import json
import os
import sys
from pathlib import Path

REASON_PREFIX = "test-engineer may only edit test files: "

# Frontend test file suffixes (checked against the basename).
FRONTEND_TEST_SUFFIXES = (".test.js", ".test.ts", ".spec.js", ".spec.ts")


def block(reason: str) -> None:
    sys.stderr.write(REASON_PREFIX + reason + "\n")
    sys.exit(2)


def allow() -> None:
    sys.exit(0)


def is_test_path(rel: Path) -> bool:
    """Structural (not substring) classification of a project-relative path."""
    dir_parts = rel.parts[:-1]
    if "tests" in dir_parts:
        # Anything living inside a `tests/` directory at any depth: test
        # modules, fixtures, factories, test-only config/helpers.
        return True

    basename = rel.name

    if basename in ("tests.py", "conftest.py"):
        return True

    if basename.startswith("test_") and basename.endswith(".py"):
        return True

    if basename.endswith("_test.py"):
        return True

    if basename.endswith(FRONTEND_TEST_SUFFIXES):
        return True

    return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        block(f"could not parse hook input as JSON ({exc})")
        return

    file_path = payload.get("tool_input", {}).get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        block("no usable 'file_path' in tool_input")
        return

    project_dir_raw = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_dir_raw:
        block("CLAUDE_PROJECT_DIR is not set; cannot safely determine the project root")
        return

    try:
        project_root = Path(project_dir_raw).resolve(strict=False)
        target = Path(file_path).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        block(f"could not resolve path ({exc})")
        return

    try:
        rel = target.relative_to(project_root)
    except ValueError:
        block(f"'{file_path}' resolves outside the project root ({project_root})")
        return

    if is_test_path(rel):
        allow()
    else:
        block(
            f"'{rel}' is not a recognized test file "
            f"(allowed: anything under a 'tests/' directory, 'tests.py', 'conftest.py', "
            f"'test_*.py', '*_test.py', '*.test.js', '*.test.ts', '*.spec.js', '*.spec.ts'). "
            f"If production code, config or docs need to change, report that to the caller "
            f"instead of editing it."
        )


if __name__ == "__main__":
    main()
