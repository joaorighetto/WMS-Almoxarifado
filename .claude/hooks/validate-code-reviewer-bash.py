#!/usr/bin/env python3
"""PreToolUse hook: enforce a read-only Bash allowlist for the code-reviewer agent.

Exit 0  -> allow the command.
Exit 2  -> block the command (stderr explains why).

Policy: ALLOWLIST, not a blocklist. Anything not explicitly recognized as a
read-only git/test/lint invocation is blocked. Fail closed.

This validator is a guardrail against an LLM-driven agent accidentally or
carelessly running a write/execute-capable command, not a sandbox or a
security boundary against a determined adversary crafting shell input by
hand. It knows about the specific flags listed below and nothing else; a
flag it has never heard of is not, by itself, a reason to allow a command —
the command is only allowed if the subcommand/program is recognized AND no
known-dangerous flag is present.
"""

import json
import shlex
import sys

REASON_PREFIX = "code-reviewer is read-only: "

# Any of these appearing anywhere in the raw command string turns a
# seemingly read-only invocation into something that can write, chain, or
# execute indirectly (redirection, pipes, command chaining, substitution,
# background jobs, multi-line payloads). Block unconditionally.
FORBIDDEN_SUBSTRINGS = [
    "|", "&", ";", ">", "<", "`", "$(", "\n", "\r",
]

GIT_READONLY_SUBCOMMANDS = {"status", "diff", "show", "log", "rev-parse", "merge-base", "ls-files"}

# git flags that write output to a file, or shell out to an external
# helper/converter, even though the subcommand is otherwise read-only
# (e.g. `git diff --output=foo`, `git show --ext-diff`).
GIT_FORBIDDEN_FLAGS = ("--output", "--ext-diff", "--textconv")

RUFF_FORBIDDEN_FLAGS = ("--fix", "--fix-only", "--output-file")

# Known write/state-mutating pytest flags. Not exhaustive (pytest has many
# third-party plugins) — see module docstring.
PYTEST_FORBIDDEN_FLAGS = (
    "--junitxml",
    "--basetemp",
    "--cache-clear",
    "--cov-report",
    "--html",
    "--self-contained-html",
)

# Known report/install-generating mypy flags. Not exhaustive.
MYPY_FORBIDDEN_FLAGS = (
    "--html-report",
    "--xml-report",
    "--txt-report",
    "--xslt-html-report",
    "--xslt-txt-report",
    "--linecount-report",
    "--lineprecision-report",
    "--linecoverage-report",
    "--any-exprs-report",
    "--cobertura-xml-report",
    "--junit-xml",
    "--install-types",
)

PYRIGHT_FORBIDDEN_FLAGS = ("--createstub",)

# `uv run` options this validator understands. Anything else appearing
# before the wrapped command is blocked (fail closed) rather than passed
# through blindly.
#
# --env-file <path> is required to run the project's official commands
# (`uv run --env-file .env pytest`, etc.) — Django settings read DB/secret
# config from the process environment and `uv run` does not load `.env`
# on its own.
#
# `uv run` performs a project lock+sync before running the wrapped command:
# it can rewrite the tracked `uv.lock` if it is out of date relative to
# `pyproject.toml`, AND it can install/upgrade packages into the local
# `.venv`. This agent must stay read-only, so both are mandatory:
# --frozen or --locked (refuse to touch `uv.lock`) AND --no-sync (refuse to
# touch the `.venv`).
UV_RUN_VALUE_FLAGS = {"--env-file"}
UV_RUN_LOCK_SAFE_FLAGS = {"--frozen", "--locked"}
UV_RUN_NO_SYNC_FLAGS = {"--no-sync"}


def block(reason: str) -> None:
    sys.stderr.write(REASON_PREFIX + reason + "\n")
    sys.exit(2)


def allow() -> None:
    sys.exit(0)


def offending_flag(tokens: list, *forbidden_flags: str):
    """Return the first forbidden flag found in `tokens`, or None.

    Matches a flag given as its own token (`--foo`, optionally followed by
    a separate value token — the value itself is irrelevant, only the flag
    token matters) and as `--foo=value`. Does not attempt to parse a full
    CLI grammar; it only needs to recognize the flag spellings above.
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
              f"which is not read-only")
    allow()


def classify_ruff(args: list) -> None:
    if args and args[0] == "check":
        flag = offending_flag(args, *RUFF_FORBIDDEN_FLAGS)
        if flag:
            block(f"'ruff check ... {flag}' modifies files or writes a report file, "
                  f"which is not read-only")
        allow()
    block("only 'ruff check ...' is allowed, not other ruff subcommands (e.g. format)")


def classify_mypy(args: list) -> None:
    flag = offending_flag(args, *MYPY_FORBIDDEN_FLAGS)
    if flag:
        block(f"'mypy ... {flag}' writes a report file or installs dependencies, "
              f"which is not read-only")
    allow()


def classify_pyright(args: list) -> None:
    flag = offending_flag(args, *PYRIGHT_FORBIDDEN_FLAGS)
    if flag:
        block(f"'pyright ... {flag}' creates artifacts in the project, which is not read-only")
    allow()


def classify_python_module(mod: str, modargs: list) -> None:
    if mod == "pytest":
        classify_pytest(modargs)
    if mod == "ruff":
        classify_ruff(modargs)
    block(f"'python -m {mod}' is not in the allowlist")


def classify_manage_py(sub: str, subargs: list) -> None:
    if sub == "test":
        allow()
    if sub == "check":
        allow()
    if sub == "makemigrations":
        if "--check" in subargs and "--dry-run" in subargs:
            allow()
        block("'manage.py makemigrations' is only allowed with both --check and --dry-run "
              "(otherwise it writes migration files)")
    block(f"'manage.py {sub}' is not in the allowlist (allowed: test, check, "
          f"makemigrations --check --dry-run)")


def classify_python(rest: list) -> None:
    if not rest:
        block("bare python/python3 invocation with no arguments is not classifiable as read-only")

    if rest[0] == "-m":
        if len(rest) < 2:
            block("'python -m' with no module is not classifiable as read-only")
        classify_python_module(rest[1], rest[2:])

    if rest[0] == "manage.py":
        if len(rest) < 2:
            block("'manage.py' with no subcommand is not classifiable as read-only")
        classify_manage_py(rest[1], rest[2:])

    block("only 'python[3] -m pytest/ruff' and 'python[3] manage.py test/check/makemigrations' "
          "are allowed")


def classify_black(rest: list) -> None:
    if offending_flag(rest, "--check") == "--check":
        allow()
    block("'black' is only allowed with --check (otherwise it reformats files in place)")


def strip_uv_run_options(tokens: list) -> list:
    """Consume `uv run`'s own options (not the wrapped command's) from the
    front of `tokens`, enforcing the allowlist in UV_RUN_*.

    Blocks (fail closed) on any option it does not recognize, and requires
    both --frozen/--locked (so `uv run` cannot rewrite the tracked
    `uv.lock` file) and --no-sync (so it cannot install/upgrade packages
    into the local `.venv`) to be present. Returns the remaining tokens:
    the wrapped command and its own arguments.
    """
    i = 0
    saw_lock_safe_flag = False
    saw_no_sync_flag = False
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

        if tok in UV_RUN_NO_SYNC_FLAGS:
            saw_no_sync_flag = True
            i += 1
            continue

        block(f"'uv run {tok}' is not an allowed uv run option "
              f"(allowed: --env-file <path>, --frozen, --locked, --no-sync)")

    if not saw_lock_safe_flag:
        block("'uv run' must include --frozen or --locked so it cannot rewrite "
              "the tracked uv.lock file")
    if not saw_no_sync_flag:
        block("'uv run' must include --no-sync so it cannot install or modify "
              "the local .venv (code-reviewer must stay read-only)")

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
            block("'uv run' with no command is not classifiable as read-only")

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
    elif prog == "black":
        classify_black(rest)
    elif prog == "mypy":
        classify_mypy(rest)
    elif prog == "pyright":
        classify_pyright(rest)
    else:
        block(f"'{prog}' is not in the read-only review allowlist "
              f"(allowed: git status/diff/show/log/branch --show-current/rev-parse/"
              f"merge-base/ls-files, pytest, python[3] -m pytest/ruff check, "
              f"manage.py test/check/makemigrations --check --dry-run, "
              f"ruff check, black --check, mypy, pyright; any of these may be prefixed "
              f"with 'uv run' plus --frozen/--locked and --no-sync (both required) and "
              f"--env-file (optional))")


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
