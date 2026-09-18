#!/usr/bin/env python3
"""PreToolUse hook: enforce a test/inspection-only Bash allowlist for the
test-engineer agent.

Exit 0  -> allow the command.
Exit 2  -> block the command (stderr explains why).

Policy: ALLOWLIST, not a blocklist. Only commands that run tests, run
read-only lint/coverage analysis, or inspect git state (never mutate it)
are allowed. Anything else is blocked. Fail closed.

This validator is a guardrail against the test-engineer agent using Bash to
modify source code or repository state, not a sandbox. Running pytest,
Django tests or coverage can legitimately create normal tool artifacts —
cache directories, a test database, a `.coverage` file, etc. That is
expected and is not what this script guards against; it guards against the
agent deliberately running a command that writes to or mutates the
repository (source files, git history, git config) instead of exercising
it.
"""

import json
import shlex
import sys

REASON_PREFIX = "test-engineer Bash is test/inspection-only: "

# Any of these appearing anywhere in the raw command string turns a
# seemingly read-only invocation into something that can write, chain, or
# execute indirectly (redirection, pipes, command chaining, substitution,
# background jobs, multi-line payloads). Block unconditionally.
FORBIDDEN_SUBSTRINGS = [
    "|", "&", ";", ">", "<", "`", "$(", "\n", "\r",
]

GIT_READONLY_SUBCOMMANDS = {"status", "diff", "show", "log", "rev-parse", "merge-base", "ls-files"}

# git flags that write output to a file, or shell out to an external
# helper/converter, even though the subcommand is otherwise read-only.
GIT_FORBIDDEN_FLAGS = ("--output", "--ext-diff", "--textconv")

RUFF_FORBIDDEN_FLAGS = ("--fix", "--fix-only", "--output-file")

# Known write/state-mutating pytest flags. Not exhaustive (pytest has many
# third-party plugins) — this is a guardrail, not a sandbox.
PYTEST_FORBIDDEN_FLAGS = (
    "--junitxml",
    "--basetemp",
    "--cache-clear",
    "--cov-report",
    "--html",
    "--self-contained-html",
)


# `uv run` options this validator understands. Anything else appearing
# before the wrapped command is blocked (fail closed) rather than passed
# through blindly.
#
# --env-file <path> is required to run the project's official commands
# (`uv run --env-file .env pytest`, etc.) — Django settings read DB/secret
# config from the process environment and `uv run` does not load `.env`
# on its own.
#
# `uv run` performs a project lock+sync before running the wrapped command,
# which can rewrite the tracked `uv.lock` if it is out of date relative to
# `pyproject.toml`. This agent must not mutate the repository outside test
# files, so at least one of --frozen/--locked (which make `uv run` refuse to
# touch `uv.lock`) is mandatory. --no-sync is accepted too but does not by
# itself satisfy that requirement.
UV_RUN_VALUE_FLAGS = {"--env-file"}
UV_RUN_LOCK_SAFE_FLAGS = {"--frozen", "--locked"}
UV_RUN_EXTRA_BOOL_FLAGS = {"--no-sync"}


def block(reason: str) -> None:
    sys.stderr.write(REASON_PREFIX + reason + "\n")
    sys.exit(2)


def allow() -> None:
    sys.exit(0)


def offending_flag(tokens: list, *forbidden_flags: str):
    """Return the first forbidden flag found in `tokens`, or None.

    Matches a flag given as its own token (optionally followed by a
    separate value token) and as `--foo=value`.
    """
    for tok in tokens:
        for flag in forbidden_flags:
            if tok == flag or tok.startswith(flag + "="):
                return flag
    return None


def classify_git(rest: list) -> None:
    if not rest:
        block("bare 'git' with no subcommand is not classifiable as read-only")

    sub = rest[0]
    args = rest[1:]

    if sub == "branch":
        if rest == ["branch", "--show-current"]:
            allow()
        block("only 'git branch --show-current' is allowed, not other 'git branch' forms")

    if sub in GIT_READONLY_SUBCOMMANDS:
        flag = offending_flag(args, *GIT_FORBIDDEN_FLAGS)
        if flag:
            block(f"'git {sub} ... {flag}' writes to a file or shells out to an external "
                  f"helper/converter, which is not read-only")
        allow()

    block(f"'git {sub}' is not in the read-only allowlist "
          f"(allowed: status, diff, show, log, branch --show-current, "
          f"rev-parse, merge-base, ls-files)")


def classify_pytest(args: list) -> None:
    flag = offending_flag(args, *PYTEST_FORBIDDEN_FLAGS)
    if flag:
        block(f"'pytest ... {flag}' writes a report file or mutates persistent test state, "
              f"which is not allowed")
    allow()


def classify_ruff(args: list) -> None:
    if args and args[0] == "check":
        flag = offending_flag(args, *RUFF_FORBIDDEN_FLAGS)
        if flag:
            block(f"'ruff check ... {flag}' modifies files or writes a report file, "
                  f"which is not allowed")
        allow()
    block("only 'ruff check ...' is allowed, not other ruff subcommands (e.g. --fix, format)")


def classify_coverage(rest: list) -> None:
    if not rest:
        block("bare 'coverage' with no subcommand is not classifiable as test/inspection")

    sub = rest[0]
    args = rest[1:]

    if sub == "report":
        allow()

    if sub == "run":
        if len(args) >= 2 and args[0] == "-m" and args[1] == "pytest":
            flag = offending_flag(args[2:], *PYTEST_FORBIDDEN_FLAGS)
            if flag:
                block(f"'coverage run -m pytest ... {flag}' writes a report file or mutates "
                      f"persistent test state, which is not allowed")
            allow()
        block("only 'coverage run -m pytest ...' is allowed, not other 'coverage run' targets")

    block("only 'coverage report ...' and 'coverage run -m pytest ...' are allowed "
          "(not 'coverage html'/'json'/'xml', which write report files/directories)")


def classify_manage_py(sub: str, subargs: list) -> None:
    if sub == "test":
        allow()
    if sub == "check":
        allow()
    block(f"'manage.py {sub}' is not in the allowlist (allowed: test, check)")


def classify_python_module(mod: str, modargs: list) -> None:
    if mod == "pytest":
        classify_pytest(modargs)
    if mod == "coverage":
        classify_coverage(modargs)
    block(f"'python -m {mod}' is not in the allowlist")


def classify_python(rest: list) -> None:
    if not rest:
        block("bare python/python3 invocation with no arguments is not classifiable as "
              "test/inspection")

    if rest[0] == "-m":
        if len(rest) < 2:
            block("'python -m' with no module is not classifiable as test/inspection")
        classify_python_module(rest[1], rest[2:])

    if rest[0] == "manage.py":
        if len(rest) < 2:
            block("'manage.py' with no subcommand is not classifiable as test/inspection")
        classify_manage_py(rest[1], rest[2:])

    block("only 'python[3] -m pytest/coverage' and 'python[3] manage.py test/check' are allowed")


def strip_uv_run_options(tokens: list) -> list:
    """Consume `uv run`'s own options (not the wrapped command's) from the
    front of `tokens`, enforcing the allowlist in UV_RUN_*.

    Blocks (fail closed) on any option it does not recognize, and requires
    --frozen or --locked to be present so `uv run` cannot rewrite the
    tracked `uv.lock` file. Returns the remaining tokens: the wrapped
    command and its own arguments.
    """
    i = 0
    saw_lock_safe_flag = False
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith("-"):
            break

        if "=" in tok:
            flag = tok.split("=", 1)[0]
            if flag in UV_RUN_VALUE_FLAGS:
                i += 1
                continue
            block(f"'uv run {flag}=...' is not an allowed uv run option "
                  f"(allowed: --env-file <path>, --frozen, --locked, --no-sync)")

        if tok in UV_RUN_VALUE_FLAGS:
            if i + 1 >= len(tokens):
                block(f"'uv run {tok}' requires a value")
            i += 2
            continue

        if tok in UV_RUN_LOCK_SAFE_FLAGS:
            saw_lock_safe_flag = True
            i += 1
            continue

        if tok in UV_RUN_EXTRA_BOOL_FLAGS:
            i += 1
            continue

        block(f"'uv run {tok}' is not an allowed uv run option "
              f"(allowed: --env-file <path>, --frozen, --locked, --no-sync)")

    if not saw_lock_safe_flag:
        block("'uv run' must include --frozen or --locked so it cannot rewrite "
              "the tracked uv.lock file")

    return tokens[i:]


def classify(command: str) -> None:
    for token in FORBIDDEN_SUBSTRINGS:
        if token in command:
            block(f"command contains '{token}', which enables chaining, redirection, "
                  f"substitution or background execution")

    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        block(f"command could not be parsed safely ({exc})")

    if not tokens:
        block("empty command")

    if tokens[0] == "uv":
        if len(tokens) < 2 or tokens[1] != "run":
            block("only 'uv run ...' is allowed, not other 'uv' subcommands "
                  "(e.g. uv add, uv sync, uv lock, uv pip)")
        tokens = strip_uv_run_options(tokens[2:])
        if not tokens:
            block("'uv run' with no command is not classifiable as test/inspection")

    prog = tokens[0]
    rest = tokens[1:]

    if prog == "git":
        classify_git(rest)
    elif prog in ("python", "python3"):
        classify_python(rest)
    elif prog == "pytest":
        classify_pytest(rest)
    elif prog == "ruff":
        classify_ruff(rest)
    elif prog == "coverage":
        classify_coverage(rest)
    else:
        block(f"'{prog}' is not in the test/inspection allowlist "
              f"(allowed: pytest, python[3] -m pytest, manage.py test/check, "
              f"git status/diff/show/log/branch --show-current/rev-parse/merge-base/ls-files, "
              f"coverage run -m pytest / coverage report, ruff check; any of these may be "
              f"prefixed with 'uv run' plus --frozen/--locked (required) and "
              f"--env-file/--no-sync)")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        block(f"could not parse hook input as JSON ({exc})")
        return

    command = payload.get("tool_input", {}).get("command")
    if not isinstance(command, str) or not command.strip():
        block("no usable 'command' string in tool_input")
        return

    classify(command.strip())


if __name__ == "__main__":
    main()
