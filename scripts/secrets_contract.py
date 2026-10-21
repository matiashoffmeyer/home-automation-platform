#!/usr/bin/env python3
"""Static contract between the code that reads secrets and ``secrets.example.yaml``.

Decision: every secret the repository reads is listed, with a harmless
placeholder, in the tracked ``secrets.example.yaml``. The real values live only in
the gitignored ``secrets.yaml`` on the host. A new host is set up by copying the
example and filling it in; CI and the offline validator run on the placeholders.

The contract is checked statically, so it needs neither the host nor the network
and runs in pre-commit and CI:

* YAML: every ``!secret <key>`` in a tracked YAML file.
* Python: every ``ha_secrets.get(<key>)``, where ``<key>`` is a string literal,
  a module-level string constant, or a constant of ``ha_secrets`` itself. A key
  that cannot be resolved statically is an error, because then a reader of the
  source cannot see which secret is read either. ``ha_secrets.load()`` and
  ``from ha_secrets import ...`` are refused for the same reason.
* Any language: a second path to the secrets file. In Python that is a path-like
  string literal (``"/config/secrets.yaml"``, ``"secrets.yaml"``); in shell and
  YAML it is ``/secrets.yaml`` outside a comment. Only the modules that own the
  file (``OWNERS``) may name it. Ten copy-pasted parsers were how a key rename
  slipped through before ``ha_secrets`` existed.

It fails on keys the code reads that the example lacks, and on example keys that
nothing reads: a stale contract tells a new host to configure secrets it does not
need.

When the live file exists (on the host), two more checks run:

* no live credential (any value of 8+ characters, except the identifiers in
  ``IDENTIFIERS``) appears verbatim in a tracked or untracked-but-not-ignored
  file. That is a token or password pasted into code or docs;
* ``--live`` additionally requires every key the code reads to be set, which is
  what a deploy needs.

Only key names and file paths are printed, never a value.

Usage::

    python3 scripts/secrets_contract.py          # pre-commit and CI
    python3 scripts/secrets_contract.py --live   # on the host, before a deploy
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections.abc import Collection, Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ha_secrets  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = "secrets.example.yaml"
READER = "scripts/ha_secrets.py"

#: Files that may name the secrets file, and why.
OWNERS = {
    READER: "the reader",
    "scripts/ha_offline.py": "keeps the real file out of its copy and seeds the example",
    "scripts/ha_validate.py": "skips the file when it scans YAML for entity references",
    "scripts/secrets_contract.py": "this check",
}

#: Keys whose values identify rather than authenticate (a name, an address, a
#: user name). They are personal data, not credentials, and short or common
#: enough to occur in ordinary text ("homeassistant"), so the leak check skips
#: them; ``live_leaks(include_identifiers=True)`` checks them for a published copy.
IDENTIFIERS = {
    "home_name",
    "home_latitude",
    "home_longitude",
    "nemlig_user",
    "music_assistant_user",
    "mqtt_gestus_user",
}
MIN_LEAK_LEN = 8  # HA's stock "some_password: welcome" is 7 characters

SECRET_TAG = re.compile(r"^[^#]*?!secret\s+([A-Za-z0-9_]+)")
PY_PATH = re.compile(r"^\S*secrets\.yaml$")
TEXT_PATH = re.compile(r"/secrets\.yaml\b")


def repo_files(*patterns: str) -> list[str]:
    """Tracked plus untracked-but-not-ignored files: what the next commit can contain."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "-co", "--exclude-standard", "--", *patterns],
        capture_output=True,
        check=True,
    ).stdout.decode()
    return sorted({p for p in out.split("\0") if p and (REPO / p).is_file()})


def is_test(rel: str) -> bool:
    """Tests build their own secrets files with synthetic keys."""
    return "/tests/" in f"/{rel}"


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# Collecting the keys the code reads
# --------------------------------------------------------------------------


def yaml_keys(files: list[str]) -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    for rel in files:
        if rel == EXAMPLE:
            continue
        for n, line in enumerate(read(rel).splitlines(), 1):
            m = SECRET_TAG.match(line)
            if m:
                keys.setdefault(m.group(1), []).append(f"{rel}:{n}")
    return keys


def resolve(node: ast.expr | None, consts: dict[str, str], lib: dict[str, str]) -> str | None:
    """The string a key expression evaluates to, if it is visible statically."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "ha_secrets"
    ):
        return lib.get(node.attr)
    return None


def module_constants(tree: ast.Module, lib: dict[str, str]) -> dict[str, str]:
    """Module-level ``NAME = "..."`` and ``NAME = ha_secrets.CONST`` assignments."""
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name):
            resolved = resolve(value, consts, lib)
            if resolved is not None:
                consts[target.id] = resolved
    return consts


def docstring_nodes(tree: ast.Module) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.add(id(body[0].value))
    return out


def python_keys(
    rel: str, tree: ast.Module, lib: dict[str, str], keys: dict[str, list[str]], errors: list[str]
) -> None:
    consts = module_constants(tree, lib)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ha_secrets":
            errors.append(
                f"{rel}:{node.lineno}: use `import ha_secrets` so the contract can see its calls"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "ha_secrets" and alias.asname not in (None, "ha_secrets"):
                    errors.append(f"{rel}:{node.lineno}: import ha_secrets without an alias")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ha_secrets"
        ):
            if node.func.attr == "get":
                arg = (
                    node.args[0]
                    if node.args
                    else next((k.value for k in node.keywords if k.arg == "key"), None)
                )
                key = resolve(arg, consts, lib)
                if key is None:
                    errors.append(
                        f"{rel}:{node.lineno}: ha_secrets.get() key must be a literal "
                        "or a module-level constant"
                    )
                else:
                    keys.setdefault(key, []).append(f"{rel}:{node.lineno}")
            elif node.func.attr == "load" and rel not in OWNERS:
                errors.append(
                    f"{rel}:{node.lineno}: ha_secrets.load() hides which keys are read; "
                    "use ha_secrets.get(<key>)"
                )


def python_paths(rel: str, tree: ast.Module, errors: list[str]) -> None:
    docs = docstring_nodes(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docs
            and PY_PATH.match(node.value.strip())
        ):
            errors.append(
                f"{rel}:{node.lineno}: names the secrets file; read it through ha_secrets.get()"
            )


def text_paths(rel: str, errors: list[str]) -> None:
    for n, line in enumerate(read(rel).splitlines(), 1):
        code = line.strip()
        if code.startswith("#"):
            continue
        code = code.split(" #", 1)[0]
        if TEXT_PATH.search(code):
            errors.append(
                f"{rel}:{n}: names the secrets file; read it through scripts/ha_secrets.py"
            )


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def live_leaks(
    files: Mapping[str, str | bytes],
    include_identifiers: bool = False,
    ignore: Collection[str] = (),
) -> list[str]:
    """``"<path>: contains the live value of <key>"`` for each live value found.

    Only values of ``MIN_LEAK_LEN`` or more characters are looked for, and the
    ``IDENTIFIERS`` only on request: a copy meant for publication must not
    contain the home's name or a user name either. Empty when the live file does
    not exist (CI, a fresh clone). ``ignore`` names keys whose live value is not
    personal (a stock user name such as ``homeassistant``).
    """
    if not ha_secrets.SECRETS_FILE.is_file():
        return []
    live = ha_secrets.load(ha_secrets.SECRETS_FILE)
    values = {
        k: v.encode()
        for k, v in live.items()
        if len(v) >= MIN_LEAK_LEN
        and k not in ignore
        and (include_identifiers or k not in IDENTIFIERS)
    }
    found = []
    for rel, content in files.items():
        data = content.encode() if isinstance(content, str) else content
        found += [f"{rel}: contains the live value of {k}" for k, v in values.items() if v in data]
    return found


def check(live_required: bool) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    keys = yaml_keys(repo_files("*.yaml", "*.yml"))
    lib = module_constants(ast.parse(read(READER)), {})
    for rel in repo_files("*.py"):
        if is_test(rel):
            continue
        try:
            tree = ast.parse(read(rel), filename=rel)
        except SyntaxError as e:
            errors.append(f"{rel}:{e.lineno}: does not parse ({e.msg})")
            continue
        if rel != READER:
            python_keys(rel, tree, lib, keys, errors)
        if rel not in OWNERS:
            python_paths(rel, tree, errors)
    for rel in repo_files("*.sh", "*.yaml", "*.yml"):
        if rel not in OWNERS and rel != EXAMPLE and not is_test(rel):
            text_paths(rel, errors)

    if not (REPO / EXAMPLE).is_file():
        errors.append(f"{EXAMPLE} is missing")
        example: dict[str, str] = {}
    else:
        example = ha_secrets.parse(read(EXAMPLE))
    for key in sorted(set(keys) - set(example)):
        errors.append(f"{key}: read by {', '.join(keys[key])} but missing from {EXAMPLE}")
    for key in sorted(set(example) - set(keys)):
        errors.append(f"{key}: listed in {EXAMPLE} but nothing reads it (remove it)")
    for key in sorted(k for k, v in example.items() if not v):
        errors.append(f"{key}: has no placeholder value in {EXAMPLE}")

    live_file = ha_secrets.SECRETS_FILE
    if live_file.is_file():
        live = ha_secrets.load(live_file)
        unset = sorted(k for k in keys if not live.get(k))
        if unset:
            (errors if live_required else warnings).append(
                f"not set in {live_file}: {', '.join(unset)}"
            )
        files = {}
        for rel in repo_files():
            try:
                files[rel] = (REPO / rel).read_bytes()
            except OSError:
                continue
        errors += live_leaks(files)
        if live_required:  # housekeeping, not news on every commit
            for key in sorted(set(live) - set(keys)):
                warnings.append(f"{key}: set in {live_file} but nothing tracked reads it")
    elif live_required:
        errors.append(f"{live_file} does not exist")

    for msg in warnings:
        print(f"note: {msg}", file=sys.stderr)
    for msg in errors:
        print(f"error: {msg}", file=sys.stderr)
    if errors:
        return 1
    print(f"secrets contract ok: {len(keys)} keys, all in {EXAMPLE}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--live",
        action="store_true",
        help="also require every key to be set in the live secrets file",
    )
    return check(live_required=ap.parse_args().live)


if __name__ == "__main__":
    sys.exit(main())
