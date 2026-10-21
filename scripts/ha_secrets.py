"""The one reader for the secrets that Home Assistant and the helper scripts share.

``secrets.yaml`` is Home Assistant's own secrets store. It is gitignored, and its
contract (every key, with a harmless placeholder) is the tracked
``secrets.example.yaml``. Home Assistant reads it through ``!secret``; scripts
read it through this module and nothing else.

Why a module instead of the old copy-pasted parsers: ten scripts used to carry
their own line parser for the same file. That is how a key rename gets missed,
and how a credential ends up hard-coded "just for now". With one reader there is
one place to change, one place to test, and one static contract
(``scripts/secrets_contract.py``) that proves every key a script asks for is
documented in the example file.

The parser is deliberately flat and dependency-free. The scripts run both inside
HA Core's container (``shell_command``) and in the SSH add-on, and only the
former is guaranteed to ship PyYAML. ``secrets.yaml`` is flat ``key: value``
pairs by design, and the subset of YAML scalar syntax handled here (plain,
single-quoted and double-quoted values, trailing comments) is the subset that
file uses.

Values are never logged, and never included in exception messages.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, overload

#: Location of the live secrets file. ``HA_SECRETS_FILE`` overrides it for tests
#: and for CI, which points it at ``secrets.example.yaml``.
SECRETS_FILE = Path(os.environ.get("HA_SECRETS_FILE", "/config/secrets.yaml"))

#: Long-lived HA access token shared by every script that calls the REST API from
#: inside HA Core's ``shell_command``. The supervisor proxy refuses that process's
#: SUPERVISOR_TOKEN for ``/core/api`` (see .claude/rules/scripts_api.md).
HA_API_TOKEN = "ha_api_token"


class SecretMissing(RuntimeError):
    """A required key is absent or empty, or the secrets file itself is missing."""


def _unquote(raw: str) -> str:
    """Return the scalar value of the text after ``key:``, as YAML would read it."""
    raw = raw.strip()
    if raw[:1] == '"':
        end = raw.find('"', 1)
        while end > 0 and raw[end - 1] == "\\":
            end = raw.find('"', end + 1)
        if end > 0:
            return raw[1:end].replace('\\"', '"').replace("\\\\", "\\")
    elif raw[:1] == "'":
        i, out = 1, []
        while i < len(raw):
            if raw[i] == "'":
                if raw[i + 1 : i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                return "".join(out)
            out.append(raw[i])
            i += 1
    # Plain scalar: a comment starts at " #", never at a bare "#".
    cut = raw.find(" #")
    return (raw if cut < 0 else raw[:cut]).strip()


def parse(text: str) -> dict[str, str]:
    """Parse flat ``key: value`` YAML. The first occurrence of a key wins."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        key, _, value = s.partition(":")
        key = key.strip()
        if key and " " not in key and key not in out:
            out[key] = _unquote(value)
    return out


def load(path: Path | None = None) -> dict[str, str]:
    """All key/value pairs of the secrets file, or an empty dict if it is missing."""
    try:
        return parse((path or SECRETS_FILE).read_text(encoding="utf-8"))
    except OSError:
        return {}


@overload
def get(key: str, required: Literal[True] = ...) -> str: ...
@overload
def get(key: str, required: bool) -> str | None: ...


def get(key: str, required: bool = True) -> str | None:
    """Return the value of ``key``.

    A missing or empty value raises :class:`SecretMissing` when ``required``,
    and returns ``None`` otherwise. The error names the key and the file, never
    a value.
    """
    value = load().get(key) or None
    if value is None and required:
        raise SecretMissing(f"{key} is missing from {SECRETS_FILE}")
    return value
