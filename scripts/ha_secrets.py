"""The one reader (and writer) for the secrets that Home Assistant and the scripts share.

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

``put`` is the one writer, for values nobody types or sees: ``scripts/secret_set.py``
generates one, or takes it from the user's phone, and hands it over here.
"""

from __future__ import annotations

import json
import os
import re
import shutil
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
        i, out = 1, []
        while i < len(raw):
            pair = raw[i : i + 2]
            if pair in ('\\"', "\\\\"):  # the only escapes put() writes
                out.append(pair[1])
                i += 2
                continue
            if raw[i] == '"':
                return "".join(out)
            out.append(raw[i])
            i += 1
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


KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def put(key: str, value: str, path: Path | None = None) -> bool:
    """Set ``key`` to ``value`` in the secrets file. True when the key is new.

    Only a one-line printable value is written, double-quoted. Every other line is
    kept as it was; a comment on the key's own line goes. The new text must read
    back to the same value before it replaces the file atomically, with the old
    mode, and the previous file stays as ``<name>.prev``. Errors name the key,
    never the value.
    """
    if not KEY.fullmatch(key):
        raise ValueError(f"invalid key name {key!r}")
    if not value or not value.isprintable():
        raise ValueError(f"{key}: the value must be one non-empty line of printable text")
    p = path or SECRETS_FILE
    try:
        text = p.read_bytes().decode("utf-8")  # bytes: keep the file's own line ends
    except FileNotFoundError:
        text = ""
    lines = text.splitlines(keepends=True)
    hits = [i for i, s in enumerate(lines) if re.match(rf"{re.escape(key)}[ \t]*:", s)]
    if len(hits) > 1:
        raise ValueError(f"{key} appears {len(hits)} times in {p}")
    new_line = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    if hits:
        i = hits[0]
        rest = lines[i].partition(":")[2].strip()
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if rest[:1] in ("|", ">") or (nxt[:1] in (" ", "\t") and nxt.strip()):
            raise ValueError(f"{key} holds a multi-line value in {p}: change it by hand")
        lines[i] = new_line + lines[i][len(lines[i].rstrip("\r\n")) :]
    else:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(new_line + "\n")
    out = "".join(lines)
    if parse(out).get(key) != value or not _yaml_agrees(text, out, key, value):
        raise ValueError(f"{key}: the new line does not read back; {p} is unchanged")
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
            f.flush()
            os.fsync(f.fileno())
        if p.exists():
            st = p.stat()
            os.chmod(tmp, st.st_mode & 0o7777)
            try:
                os.chown(tmp, st.st_uid, st.st_gid)
            except PermissionError:
                pass
            shutil.copy2(p, p.with_name(p.name + ".prev"))
        os.replace(tmp, p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return not hits


def _yaml_agrees(old: str, new: str, key: str, value: str) -> bool:
    """A second opinion from PyYAML where it is installed (HA Core always has it).

    A file PyYAML could not read before is not held against the new one, and a
    parse error is never re-raised: its message quotes the line, i.e. a value.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return True
    try:
        yaml.safe_load(old)
    except yaml.YAMLError:
        return True
    try:
        return (yaml.safe_load(new) or {}).get(key) == value
    except yaml.YAMLError:
        return False
