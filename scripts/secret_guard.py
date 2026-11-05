#!/usr/bin/env python3
"""PreToolUse hook: keep secret values out of the transcript.

Everything the agent reads or prints is stored in ~/.claude/projects and sent
to Anthropic. Two live credentials got there before this hook: on 2026-11-02
`bash -x` printed the supervisor token from a curl header, and on 2026-11-04 an
API key was pasted into the chat. This hook rejects the accidental ways a value
reaches the transcript, with exit 2 and the reason on stderr:

1. Reading a credential store: secrets.yaml, the .storage files that hold
   tokens, SSH private keys, Claude's own login, the add-on options, the s6
   container environment, /proc/*/environ. Covers the Read, Write, Edit and
   Grep tools; readers (cat, grep, jq, sed, ...) and senders (curl -F @file,
   scp) in Bash; and recursive searches that would reach those files.
2. Dumping the environment: bare env, printenv, set, export and declare -p;
   echo of a variable named like a secret; docker inspect without --format;
   add-on info from the supervisor (its options hold passwords).
3. Output that expands a secret: bash -x and set -x, curl -v with an auth
   header, gitleaks without --redact, ot-ctl printing the Thread network key.

Allowed: metadata (ls, stat, wc, sha256sum, git, test -f), greps that only
count or list (-c, -l, -q), `env | cut -d= -f1`, and scripts or inline Python
that print the fields they name. Inline Python that names secrets.yaml is
rejected: the secrets contract says only scripts/ha_secrets.py reads it.

Not a sandbox: a deliberate script can still print anything, so
scripts/secret_leak_scan.py checks the transcripts when a session ends and
pushes "roter X" on a hit. Fails open (exit 0) on any error, like the other
guards (docs/adr/0006-agent-guardrails-as-hooks.md).
"""

import fnmatch
import functools
import glob
import json
import os
import re
import shlex
import sys

HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Rødderne der søges efter kendte credential-filer (testene peger dem på en tmp-mappe).
REPO_ROOTS = [REPO, "/homeassistant", "/config"]
SSH_DIRS = ["/data/.ssh", os.path.join(HOME, ".ssh")]
S6_DIRS = ["/run/s6/container_environment", "/var/run/s6/container_environment"]

# --- Hvad er et credential-lager? ----------------------------------------------
# .storage-filerne med tokens, password-hashes, OAuth-klienter, backup-nøglen,
# HomeKit-parringsnøgler og Thread-netværksnøglen (også kopier: auth.bak).
# Resten af .storage (registre, dashboards) er frit.
STORAGE_EXACT = ("auth", "application_credentials", "backup", "cloud", "thread.datasets")
STORAGE_PREFIX = ("auth_provider.", "auth_module.", "core.config_entries", "homekit.")
STORAGE_EXACT_DOT = tuple(x + "." for x in STORAGE_EXACT)
SSH_PUBLIC = {"config", "known_hosts", "known_hosts.old", "authorized_keys"}
EXACT = {
    os.path.join(HOME, ".claude", ".credentials.json"),
    "/share/claude-token.env",
    "/data/options.json",
}
SECRET_DIRS = {".aws", ".azure", ".gnupg", ".cloud"}
BASENAME = re.compile(
    r"secrets\.yaml(\.(?!example$|sample$)[^/]+)?"
    r"|\..+\.local\.ya?ml"  # git-ignored tool config: keys + personal values
    r"|\.env(\.(?!example$|sample$)[^/]+)?"
    r"|\.netrc|\.git-credentials|\.pgpass"
    r"|id_(rsa|dsa|ecdsa|ed25519)"
    r"|.+\.(key|p12|pfx|jks|keystore)"
    r"|(privkey|.*private).*\.pem"
)
PROC_ENVIRON = re.compile(r"/proc/[^/]+(/task/[^/]+)?/environ")
PROC_RAW = re.compile(r"/proc/(\$\([^)]*\)|`[^`]*`)/environ\b")
S6_ENV = "/s6/container_environment"
# PASS/PIN/KEY kun med store bogstaver: `for key in …; echo "$key"` er ikke en hemmelighed.
SECRETISH = re.compile(
    r"(?i:TOKEN|SECRET|PASSW|API_?KEY|APIKEY|PRIVATE|CREDENTIAL|COOKIE)"
    r"|(^|_)(PASS|PIN|KEY)($|_)"
)


def protected(path):
    """A short label if `path` is a credential store, else None."""
    p = os.path.normpath(path)
    parts = p.split("/")
    base = parts[-1]
    if p in EXACT or p.endswith(("/.docker/config.json", "/gh/hosts.yml")):
        return p
    if BASENAME.fullmatch(base):
        return base
    if len(parts) > 1 and parts[-2] == ".storage":
        if base in STORAGE_EXACT or base.startswith(STORAGE_PREFIX + STORAGE_EXACT_DOT):
            return ".storage/" + base
    if ".ssh" in parts[:-1] and not (base.endswith(".pub") or base in SSH_PUBLIC):
        return ".ssh/" + base
    if SECRET_DIRS.intersection(parts[:-1]):
        return p
    if PROC_ENVIRON.fullmatch(p):
        return "/proc/…/environ"
    if S6_ENV in p:
        return "s6-miljøet (container_environment)"
    return None


@functools.lru_cache(maxsize=8)
def secret_files(cwd):
    """Known credential files as (path, anchor).

    The anchor is the git-ignored entry that hides the file from the house
    shell's grep and rg (both skip git-ignored files, the probe of 2026-11-05);
    None for files outside a repository."""
    out, seen = [], set()

    def put(p, anchor):
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            out.append((p, anchor))

    for root in dict.fromkeys([*REPO_ROOTS, cwd]):
        if not root or not os.path.isdir(root):
            continue
        for p in (
            glob.glob(os.path.join(root, "secrets.yaml*"))
            + glob.glob(os.path.join(root, ".env*"))
            + glob.glob(os.path.join(root, ".*.local.y*ml"))
        ):
            if os.path.exists(p) and protected(p):
                put(p, p)
        st = os.path.join(root, ".storage")
        for p in glob.glob(os.path.join(st, "*")):
            if protected(p):
                put(p, st)
    for p in sorted(EXACT):
        put(p, None)
    for d in SSH_DIRS:
        for p in glob.glob(os.path.join(d, "*")):
            if protected(p):
                put(p, None)
    for d in S6_DIRS:
        if os.path.isdir(d):
            put(d, None)
    return tuple(out)


def matches(globs, base, rel):
    return any(fnmatch.fnmatch(base, g) or fnmatch.fnmatch(rel, g) for g in globs)


def reached(root, cwd, aware, hidden_ok, includes=(), excludes=(), exclude_dirs=(), names=()):
    """Labels of the credential files a recursive read of `root` would open."""
    hits = []
    for p, anchor in secret_files(cwd):
        forms = (
            (os.path.normpath(root), p, anchor),
            (os.path.realpath(root), os.path.realpath(p), anchor and os.path.realpath(anchor)),
        )
        hit = next(
            (f for f in forms if f[1] == f[0] or f[1].startswith(f[0].rstrip("/") + "/")), None
        )
        if not hit:
            continue
        r, q, a = hit
        rel = os.path.relpath(q, r)
        segs = [] if rel == "." else rel.split("/")
        if aware and a and a != r and not r.startswith(a.rstrip("/") + "/"):
            continue  # git-ignoreret og roden ligger over det: springes over
        if not hidden_ok and any(x.startswith(".") for x in segs):
            continue
        base = os.path.basename(q)
        if includes and not matches(includes, base, rel):
            continue
        if matches(excludes, base, rel) or any(
            fnmatch.fnmatch(d, g) for d in segs[:-1] for g in exclude_dirs
        ):
            continue
        if names and not any(fnmatch.fnmatch(base.lower(), g.lower()) for g in names):
            continue
        hits.append(protected(q) or protected(p) or q)
    return hits


def braces(t):
    m = re.search(r"\{([^{}]*,[^{}]*)\}", t)
    if not m:
        return [t]
    return [t[: m.start()] + x + t[m.end() :] for x in m.group(1).split(",")]


def candidates(tok, cwd):
    """The paths a word may name: --opt=PATH, @PATH, if=PATH, globs, braces."""
    t = tok.strip()
    if not t or re.search(r"\s", t) or "://" in t:
        return []
    if t.startswith("-"):
        if "=" not in t:
            return []
        t = t.split("=", 1)[1]
    if "=@" in t:
        t = t.split("=@", 1)[1]
    elif t.startswith("@"):
        t = t[1:]
    elif re.match(r"(if|of|file|path|src|input)=", t):
        t = t.split("=", 1)[1]
    t = t.split(";")[0]
    for h in ("${HOME}", "$HOME"):
        if t.startswith(h):
            t = HOME + t[len(h) :]
    out = []
    for x in braces(os.path.expanduser(t)):
        p = os.path.normpath(x if os.path.isabs(x) else os.path.join(cwd, x))
        if any(ch in x for ch in "*?["):
            out += glob.glob(p)[:500] or [p]
        else:
            out.append(p)
    return out


# --- Shell-parsing ----------------------------------------------------------------
PUNCT = "();<>|&\n"
HEREDOC = re.compile(r"(?<!<)<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash"}
INTERP = re.compile(r"python|python3(\.\d+)?|pypy3?|node|perl|ruby|php|deno|bun")
PYTHON = re.compile(r"python|python3(\.\d+)?|pypy3?")
# navn: (flag der tager et argument, positionelle før kommandoen)
WRAP = {
    "sudo": ({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"}, 0),
    "doas": ({"-u"}, 0),
    "nohup": ((), 0),
    "time": ((), 0),
    "command": ((), 0),
    "builtin": ((), 0),
    "exec": ((), 0),
    "nice": ({"-n"}, 0),
    "ionice": ({"-c", "-n", "-p"}, 0),
    "stdbuf": ((), 0),
    "setsid": ((), 0),
    "unbuffer": ((), 0),
    "chronic": ((), 0),
    "with-contenv": ((), 0),
    "timeout": ({"-s", "--signal", "-k", "--kill-after"}, 1),
    "flock": ({"-w", "--timeout", "-E", "--conflict-exit-code"}, 1),
    "watch": ({"-n", "--interval"}, 0),
    "xargs": ({"-I", "-n", "-P", "-d", "-E", "-L", "-s", "-a", "--delimiter"}, 0),
    "taskset": ((), 1),
    "chrt": ((), 1),
}
SSH_ARG = {"-b", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J", "-L", "-l", "-m", "-O", "-o"}
SSH_ARG |= {"-p", "-Q", "-R", "-S", "-W", "-w", "-B"}


def name(t):
    return os.path.basename(t).lstrip("\\")


def skip_opts(w, with_arg=()):
    i = 0
    while i < len(w) and w[i].startswith("-") and w[i] != "-":
        if w[i] == "--":
            return w[i + 1 :]
        i += 2 if w[i] in with_arg else 1
    return w[i:]


def split_heredocs(cmd):
    """Remove here-document bodies: (command, [(owner, body)]).

    A body is data for the command that owns it (a commit message, a file being
    written), unless the owner is a shell or Python."""
    lines, keep, bodies, i = cmd.split("\n"), [], [], 0
    while i < len(lines):
        line = lines[i]
        keep.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            body = []
            while i < len(lines) and lines[i].strip() != m.group(2):
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append((owner(line[: m.start()]), "\n".join(body)))
    return "\n".join(keep), bodies


def owner(prefix):
    seg = re.split(r"&&|\|\||[;|(]", prefix)[-1]
    try:
        words = shlex.split(seg)
    except ValueError:
        words = seg.split()
    words = unwrap(words)[0]
    return name(words[0]) if words else ""


def substitutions(cmd):
    """Bodies of $(...) and `...`: they run even inside double quotes."""
    out, i = [], 0
    while (j := cmd.find("$(", i)) >= 0:
        depth, k = 1, j + 2
        while k < len(cmd) and depth:
            depth += {"(": 1, ")": -1}.get(cmd[k], 0)
            k += 1
        out.append(cmd[j + 2 : k - 1])
        i = j + 2
    return out + re.findall(r"`([^`]+)`", cmd)


def classify(t):
    if not t or t.strip(PUNCT):
        return "word"
    if any(ch in t for ch in ";\n()") or "&&" in t or "||" in t:
        return "break"
    if "<" in t or ">" in t:
        return "redir"
    if t.startswith("|"):
        return "pipe"
    return "break"


def pipelines(cmd):
    """[[(words, redirects), ...], ...]: the pipelines of simple commands."""
    try:
        lx = shlex.shlex(cmd, posix=True, punctuation_chars=PUNCT)
        lx.whitespace = " \t\r"
        lx.whitespace_split = True
        toks = list(lx)
    except ValueError:  # uafsluttet citat: grov opdeling i stedet for at give op
        toks = re.findall(r"\|\||&&|[;|&()\n]|[<>]+|[^\s;|&()<>]+", cmd)
    out, pipe, words, redirs, target = [], [], [], [], None
    for t in toks:
        kind = classify(t)
        if target is not None and kind == "word":
            redirs.append((target, t))
            target = None
            continue
        target = None
        if kind == "word":
            words.append(t)
        elif kind == "redir":
            target = t
            if words and words[-1].isdigit():
                target = words.pop() + t  # 2>/dev/null: fd'en hører til operatoren
        else:
            pipe.append((words, redirs))
            words, redirs = [], []
            if kind == "break":
                out.append(pipe)
                pipe = []
    pipe.append((words, redirs))
    out.append(pipe)
    return [[s for s in p if s[0] or s[1]] for p in out]


def dash_c(args, su=False):
    """The command string after -c, or None (a script file, an interactive shell)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-o", "+o", "-O", "+O"):
            i += 2
            continue
        if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a):
            return args[i + 1] if i + 1 < len(args) else None
        if (a == "--" or not a.startswith(("-", "+"))) and not su:
            return None
        i += 1
    return None


def xtrace_flags(args):
    """-x in an option cluster, or -o xtrace, before the script or command."""
    for i, a in enumerate(args):
        if a == "-o" and args[i + 1 : i + 2] == ["xtrace"]:
            return True
        if re.fullmatch(r"-[A-Za-z]*x[A-Za-z]*", a):
            return True
        if a == "--" or not a.startswith(("-", "+")):
            return False
    return False


def unwrap(words):
    """Strip wrappers (sudo, timeout, docker exec, bash -c, ...).

    Returns (words, nested command strings, notes). The note "binary" means the
    command runs as a program, without the shell's grep/rg functions."""
    w, nested, notes = list(words), [], set()
    for _ in range(16):
        if not w:
            break
        t, b = w[0], name(w[0])
        if ASSIGN.match(t):
            w = w[1:]
        elif b in WRAP:
            opts, npos = WRAP[b]
            if b != "time":
                notes.add("binary")
            if b == "xargs":
                notes.add("xargs")
            w = skip_opts(w[1:], opts)[npos:]
        elif b == "env":
            rest = skip_opts(w[1:], {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"})
            while rest and ASSIGN.match(rest[0]):
                rest = rest[1:]
            if not rest:
                return ["env"], nested, notes  # bart env printer hele miljøet
            notes.add("binary")
            w = rest
        elif b == "docker" and (w[1:2] == ["exec"] or w[1:3] == ["container", "exec"]):
            opts = {"-u", "--user", "-e", "--env", "-w", "--workdir", "--env-file"}
            w = skip_opts(w[2 if w[1] == "exec" else 3 :], opts)[1:]
            notes |= {"binary", "docker"}
        elif b in SHELLS or b == "su":
            code = dash_c(w[1:], su=b == "su")
            if code is None:
                break
            if b in SHELLS and xtrace_flags(w[1:]):
                notes.add("xtrace")
            nested.append(code)
            return [], nested, notes
        elif b == "eval":
            nested.append(" ".join(w[1:]))
            return [], nested, notes
        else:
            if b == "ssh":
                rest = skip_opts(w[1:], SSH_ARG)
                if len(rest) > 1:
                    nested.append(" ".join(rest[1:]))
            break
    return w, nested, notes


# --- Kommando-klasser ---------------------------------------------------------------
GREPS = {"grep", "egrep", "fgrep", "zgrep", "rg", "ag", "ack", "ugrep", "ug"}
RGLIKE = {"rg", "ag", "ack"}
GREP_ARG = {"-e", "--regexp", "-f", "--file", "-m", "--max-count", "-A", "-B", "-C", "-d", "-D"}
GREP_ARG |= {"--context", "--after-context", "--before-context", "--directories", "--label"}
GREP_ARG |= {"--include", "--exclude", "--exclude-dir", "--exclude-from", "--color"}
RG_ARG = {"-e", "--regexp", "-f", "--file", "-g", "--glob", "--iglob", "-t", "--type", "-T"}
RG_ARG |= {"--type-not", "-m", "--max-count", "-A", "-B", "-C", "--context", "-M", "-j", "-d"}
RG_ARG |= {"--max-depth", "-r", "--replace", "--pre", "--ignore-file", "-E", "--encoding"}
RG_ARG |= {"--sort", "--sortr", "--type-add", "--colors", "--color", "-G", "--ignore"}
NAMES_ONLY = {"--files-with-matches", "--files-without-match", "--count", "--quiet", "--silent"}
NAMES_ONLY |= {"--files", "--count-matches"}
RG_TYPES = {"yaml": ["*.yaml", "*.yml"], "py": ["*.py"], "json": ["*.json"], "md": ["*.md"]}
RG_TYPES |= {"sh": ["*.sh"], "js": ["*.js"], "toml": ["*.toml"], "txt": ["*.txt"]}
HASHES = {"md5sum", "sha1sum", "sha224sum", "sha256sum", "sha384sum", "sha512sum", "b2sum"}
HASHES |= {"cksum"}
SAFE = {"ls", "ll", "stat", "file", "test", "[", "[[", "wc", "du", "df", "chmod", "chown"}
SAFE |= {"chgrp", "chattr", "lsattr", "touch", "rm", "rmdir", "mv", "cp", "ln", "install"}
SAFE |= {"mkdir", "cd", "pushd", "popd", "realpath", "readlink", "dirname", "basename"}
SAFE |= {"echo", "printf", "print", "true", "false", "exit", "sleep", "source", ".", "which"}
SAFE |= {"type", "tee", "shred", "truncate", "getfacl", "setfacl", "namei", "lsof", "fuser"}
SAFE |= {"ssh-keygen", "ssh-add", "git", "find", "tar", "zip", "locate", "mktemp", "export"}
SAFE |= {"unset", "local", "read", "ssh", "inotifywait"}
SAFE |= HASHES
STDIN_OK = HASHES | {"wc", "read", "cmp"}
TRANSMIT = {"curl", "wget", "scp", "sftp", "rsync", "nc", "ncat", "netcat", "socat", "ftp"}
TRANSMIT |= {"lftp", "rclone", "mail", "mailx", "sendmail", "mutt", "http", "https", "xh"}
# Flag hvis argument ikke sendes: output-filen, TLS-klientnøglen, ssh-identiteten.
TRANSMIT_KEEP = {
    "curl": {"-o", "--output", "-E", "--cert", "--key", "--cacert", "--capath", "-K", "--config"},
    "wget": {"-O", "--output-document", "-o", "--output-file", "--certificate", "--private-key"},
}
SSH_KEEP = {"-i", "-F", "-o", "-e", "--rsh", "-S", "-J"}
REMOTE = re.compile(r"[\w.@-]+:")
SINKS = HASHES | {"wc", "curl", "wget", "docker", "gh", "python", "python3"}
DUMP_MODULES = {"json.tool", "base64", "uu", "quopri", "pickletools", "tokenize"}
SENSITIVE = re.compile(r"pass|key|token|secret|options|user|login|auth|cred", re.I)
AUTH = re.compile(r"authorization|bearer|x-api-key|api[-_]?key|cookie", re.I)
SECRET_VAR = re.compile(r"\$(\{)?(?!#)([A-Za-z_][A-Za-z0-9_]*)(:?\+)?")
ADDON_URL = re.compile(r"/(addons|apps)/[^/\s]+/(info|options)\b|/node/dataset/(active|pending)")


def parse_args(a, arg_opts, arg2=()):
    """(positionals, {option: [values]}, flags)."""
    pos, opts, flags, i = [], {}, [], 0
    while i < len(a):
        x = a[i]
        if x == "--":
            pos += a[i + 1 :]
            break
        if x.startswith("--") and "=" in x:
            k, v = x.split("=", 1)
            opts.setdefault(k, []).append(v)
        elif x in arg2:
            opts.setdefault(x, []).extend(a[i + 1 : i + 3])
            i += 2
        elif x in arg_opts:
            opts.setdefault(x, []).append(a[i + 1] if i + 1 < len(a) else "")
            i += 1
        elif x.startswith("-") and x != "-":
            flags.append(x)
        else:
            pos.append(x)
        i += 1
    return pos, opts, flags


def short_flags(flags):
    return "".join(f[1:] for f in flags if f.startswith("-") and not f.startswith("--"))


def grep_names_only(c, a):
    """Only file names, counts or an exit code (-l, -c, -q)? In rg, -L is --follow."""
    _pos, _opts, flags = parse_args(a, RG_ARG if c in RGLIKE else GREP_ARG)
    quiet = "lcq" if c == "rg" else "lLcq"
    return bool(set(short_flags(flags)) & set(quiet) or set(flags) & NAMES_ONLY)


def secret_var(text):
    """A $VAR with a secret name; ${VAR:+x} and ${#VAR} print no value."""
    for m in SECRET_VAR.finditer(text):
        if not (m.group(1) and m.group(3)) and SECRETISH.search(m.group(2)):
            return True
    return False


def names_only(rest):
    """Does a later stage reduce `NAME=value` lines to names or a count?"""
    for w in rest:
        if not w:
            continue
        c, s = name(w[0]), " ".join(w[1:])
        if c == "cut" and re.search(r"-f\s*1\b", s) and re.search(r"-d\s*=", s):
            return True
        if c in ("awk", "gawk", "mawk") and "=" in s and re.search(r"print \$1\b", s):
            if not re.search(r"\$([2-9]|0|NF)", s):
                return True
        if c == "sed" and "s/=.*//" in s:
            return True
        if c == "wc" or (c in GREPS and grep_names_only(c, w[1:])):
            return True
    return False


def redacted(rest):
    return any(
        w and name(w[0]) in ("sed", "perl") and re.search(r"bearer|redact", " ".join(w), re.I)
        for w in rest
    )


def selective(rest):
    """Does the next stage pick fields out of add-on info instead of dumping it?"""
    if not rest or not rest[0]:
        return False
    c, a = name(rest[0][0]), rest[0][1:]
    if PYTHON.fullmatch(c):
        return True
    if c in ("jq", "gojq", "yq"):
        f = next((x for x in a if not x.startswith("-")), ".")
        return f.strip() not in (".", ".data") and "options" not in f
    if c in GREPS:
        pos, opts, flags = parse_args(a, GREP_ARG)
        pat = " ".join(opts.get("-e", []) + pos[:1])
        return "v" not in short_flags(flags) and bool(pat) and not SENSITIVE.search(pat)
    return False


def ot_filtered(rest):
    for w in rest:
        if w and name(w[0]) in GREPS:
            pos, opts, flags = parse_args(w[1:], GREP_ARG)
            pat = " ".join(opts.get("-e", []) + pos[:1]).lower()
            if "v" in short_flags(flags):
                if "key" in pat:
                    return True
            elif pat and "key" not in pat and "pskc" not in pat:
                return True
    return False


def env_dump(c, a):
    if c == "env":
        return True
    names = [x for x in a if not x.startswith(("-", "+"))]
    flags = short_flags([x for x in a if x.startswith("-")])
    if c == "printenv":
        return not names or any(SECRETISH.search(n) for n in names)
    if c == "export":
        return not names
    if c in ("declare", "typeset"):
        if not names:
            return not flags or bool(set(flags) & set("px"))
        return "p" in flags and any(SECRETISH.search(n) for n in names)
    if c == "set":
        return not a
    return False


def verbose_auth(c, a):
    auth = any(AUTH.search(x) or secret_var(x) for x in a)
    if c == "curl":
        verbose = any(
            x == "--verbose" or x.startswith("--trace") or re.fullmatch(r"-[A-Za-z]*v[A-Za-z]*", x)
            for x in a
        )
        auth = auth or any(
            x in ("-u", "--user", "--oauth2-bearer") or x.startswith(("--user=", "--oauth2"))
            for x in a
        )
    elif c == "wget":
        verbose = any(x in ("-d", "--debug") for x in a)
        auth = auth or any(x.startswith(("--password", "--http-password")) for x in a)
    elif c in ("http", "https", "xh"):
        verbose = any(x in ("-v", "--verbose", "-p") or x.startswith("--print") for x in a)
        auth = auth or any(x in ("-a", "--auth") or x.startswith("--auth=") for x in a)
    else:
        return False
    return verbose and auth


def recursive_copy(c, a):
    """rsync -a / scp -r with a remote end: copies whole trees off the NUC."""
    if not any(REMOTE.match(x) for x in a if not x.startswith("-")):
        return False
    short = set(short_flags(a))
    if c == "scp":
        return "r" in short
    return bool(short & set("ar") or {"--archive", "--recursive"} & set(a))


def parse_find(a):
    """(roots, -name patterns, the -exec command or None)."""
    roots, names, exe, i = [], [], None, 0
    while i < len(a) and not a[i].startswith(("-", "(", "!", ")")):
        roots.append(a[i])
        i += 1
    while i < len(a):
        if a[i] in ("-name", "-iname") and i + 1 < len(a):
            names.append(a[i + 1])
            i += 1
        elif a[i] in ("-exec", "-execdir", "-ok", "-okdir"):
            exe = [x for x in a[i + 1 :] if x not in (";", "+", "{}")]
            break
        i += 1
    return roots or ["."], names, exe


# --- Beskeder -----------------------------------------------------------------------
WHY = "Alt hvad Claude læser eller printer, gemmes i transskriptet og sendes til Anthropic."
META = (
    "Brug ls/stat/wc/sha256sum til metadata, `grep -c`/`grep -q` for at se om en nøgle findes, "
    "og Python der kun printer de felter du navngiver (ha_secrets.get(nøgle), navn eller længde)."
)
USER = (
    "Skal værdien ændres: `python3 scripts/secret_set.py generate <nøgle> --replace` "
    '(maskine-kode) eller `ask <nøgle> "<hvad>" --replace` (user indsætter på telefonen).'
)


def block(what, how):
    return f"Blokeret af scripts/secret_guard.py: {what}. {WHY} {how}"


def file_msg(c, label):
    return block(f"`{c}` ville vise indholdet af {label}", f"{META} {USER}")


def recursive_msg(c, label):
    return block(
        f"en rekursiv søgning med `{c}` ville nå {label}",
        "Søg i de mapper du mener (automations/ packages/ scripts/ …), brug husets grep/rg "
        "direkte (de springer git-ignorerede filer over), eller tilføj --exclude/--exclude-dir. "
        "Kun filnavne (-l) eller antal (-c) er tilladt.",
    )


def write_msg(label):
    return block(
        f"{label} er et credential-lager, og værdien ville stå i kaldet",
        "Brugeren lægger selv hemmeligheder ind (secrets.yaml eller HA's UI); Claude læser dem "
        "med ha_secrets.get(nøgle).",
    )


def send_msg(c, label):
    return block(
        f"`{c}` ville sende {label} ud af huset",
        "Credential-filer forlader aldrig NUC'en via Claude. Er det en bevidst backup: spørg brugeren.",
    )


ENV_MSG = block(
    "kommandoen printer miljøet, og det rummer SUPERVISOR_TOKEN m.fl.",
    'Kun navne: `env | cut -d= -f1`. Én variabel: `[ -n "$X" ] && echo sat` eller længden `${#X}`.',
)
ECHO_MSG = block(
    "kommandoen printer en variabel med et hemmeligt navn",
    'Tjek den med `[ -n "$X" ]` eller længden `${#X}`, og giv den direkte til curl.',
)
XTRACE_MSG = block(
    "xtrace (bash -x / set -x) printer hver kommando udfoldet, også Authorization-headeren "
    "med tokenet (det skete 2/11)",
    "Print kun URL'en, eller pipe gennem `sed -E 's/Bearer [^\" ]+/Bearer <redacted>/'`.",
)
CURLV_MSG = block(
    "verbose-mode med en auth-header printer tokenet",
    "Drop -v; brug `-w '%{http_code}'` eller `-i` (kun svar-headers).",
)
DOCKER_MSG = block(
    "`docker inspect` uden et udvalgt --format viser containerens miljø med tokens",
    "Vælg felter: `docker inspect -f '{{.State.Status}}' <container>`.",
)
ADDON_MSG = block(
    "add-on-info fra supervisoren rummer options med passwords (OTBR's dataset: netværksnøglen)",
    "Pipe til python3 eller jq og vælg felterne, fx `.data.version` og `.data.state`.",
)
OT_MSG = block(
    "`ot-ctl` ville printe Thread-netværksnøglen",
    "Vælg felter (`ot-ctl channel`, `ot-ctl panid`) eller filtrér: `| grep -vi -e key -e pskc`.",
)
GITLEAKS_MSG = block(
    "gitleaks uden --redact printer fundne hemmeligheder i klartekst", "Tilføj --redact."
)
PROC_MSG = block(
    "kommandoen læser en proces' miljø (/proc/…/environ), og det rummer tokens",
    "Brug ps/pgrep til processen; et variabelnavn kan brugeren slå op.",
)
PY_RULES = (
    (
        re.compile(r"secrets\.yaml(?!\.example)"),
        "Python der selv åbner secrets.yaml bryder secrets-kontrakten (kun scripts/ha_secrets.py "
        "læser den)",
        "Brug ha_secrets.get(nøgle) eller ha_secrets.load(), og print kun navne eller længder.",
    ),
    (
        re.compile(
            r"\b(?:print|pprint|pp|dumps?)\s*\(\s*(?:dict\s*\(\s*)?os\.environ\b(?!\s*[\[.])"
        ),
        "koden printer hele miljøet (os.environ)",
        "Print kun navnene: sorted(os.environ).",
    ),
    (
        re.compile(r"\bfor\s+\w+\s*,\s*\w+\s+in\s+os\.environ\.items\s*\(\s*\)"),
        "koden løber hele miljøet igennem med værdier",
        "Brug sorted(os.environ) til navnene.",
    ),
)
PY_ENV_PRINT = re.compile(
    r"\bprint\s*\([^\n]*(?:environ\s*(?:\[|\.get\s*\()|getenv\s*\()\s*['\"](\w+)['\"]"
)
PY_SECRET_PRINT = re.compile(r"\b(?:print|pprint|pp)\s*\([^\n]*\bha_secrets\.(?:get|load)\s*\(")
# len(), bool(), sorted() og list() af en værdi eller et dict viser ingen værdi.
PY_HARMLESS = re.compile(
    r"\b(?:len|bool|sorted|list)\s*\(\s*(?:os\.|ha_secrets\.)|\bif\s+(?:not\s+)?os\."
)


def check_python(code):
    for rx, what, how in PY_RULES:
        if rx.search(code):
            return block(what, how)
    for m in PY_SECRET_PRINT.finditer(code):
        if not PY_HARMLESS.search(m.group(0)):
            return block("koden printer en værdi fra ha_secrets", "Print navnet eller len(...).")
    for m in PY_ENV_PRINT.finditer(code):
        if SECRETISH.search(m.group(1)) and not PY_HARMLESS.search(m.group(0)):
            return block("koden printer en hemmelig miljøvariabel", "Print len(...) i stedet.")
    return None


# --- Kontrollen -----------------------------------------------------------------------
def check_bash(cmd, cwd, depth=0):
    """The reason to block `cmd`, or None."""
    if depth > 4 or not isinstance(cmd, str):
        return None
    cmd, bodies = split_heredocs(cmd)
    for who, body in bodies:
        if PYTHON.fullmatch(who):
            r = check_python(body)
        elif who in SHELLS or who == "ssh":
            r = check_bash(body, cwd, depth + 1)
        else:
            r = None  # data: en commit-besked, en fil der skrives
        if r:
            return r
    for sub in substitutions(cmd):
        r = check_bash(sub, cwd, depth + 1)
        if r:
            return r
    if PROC_RAW.search(cmd):  # /proc/$(pidof x)/environ: ordene alene ser det ikke
        return PROC_MSG
    state = {"cwd": cwd}
    for pipe in pipelines(cmd):
        for i, seg in enumerate(pipe):
            r = check_segment(seg, pipe, i, state, depth)
            if r:
                return r
    return None


def check_segment(seg, pipe, i, state, depth):
    words, redirs = seg
    w, nested, notes = unwrap(words)
    cwd = state["cwd"]
    for code in nested:
        r = check_bash(code, cwd, depth + 1)
        if r:
            return r
    rest = [unwrap(s[0])[0] for s in pipe[i + 1 :]]
    if "xtrace" in notes and not redacted(rest):
        return XTRACE_MSG
    c, a = (name(w[0]), w[1:]) if w else ("", [])
    if c in ("cd", "pushd") and a and a[-1] != "-":
        state["cwd"] = os.path.normpath(os.path.join(cwd, os.path.expanduser(a[-1])))
        return None
    if (c in SHELLS and xtrace_flags(a)) or (c == "set" and xtrace_flags(a)):
        if not redacted(rest):
            return XTRACE_MSG
    if c == "setopt" and any(x.lower().replace("_", "") == "xtrace" for x in a):
        return XTRACE_MSG
    if env_dump(c, a) and not names_only(rest):
        return ENV_MSG
    to_file = any(  # stdout til en fil (2>/dev/null tæller ikke)
        op.lstrip("1&") in (">", ">>", ">|") and t not in ("/dev/stdout", "/dev/stderr", "/dev/tty")
        for op, t in redirs
    )
    sink = bool(rest and rest[0] and name(rest[0][0]) in SINKS)
    if c in ("echo", "printf", "print") and any(secret_var(x) for x in a) and not (to_file or sink):
        return ECHO_MSG
    if any(op == "<<<" and secret_var(t) for op, t in redirs) and c not in SINKS:
        return ECHO_MSG
    if verbose_auth(c, a):
        return CURLV_MSG
    if c == "docker":
        sub = [x for x in a if not x.startswith("-")]
        if sub[:1] == ["inspect"] or sub[:2] == ["container", "inspect"]:
            _pos, opts, _flags = parse_args(a, {"-f", "--format", "--type"})
            fmt = (opts.get("-f") or opts.get("--format") or [""])[0]
            if not fmt or re.search(r"Env|\{\{\s*(json\s+)?\.\s*\}\}|\.Config\s*\}\}", fmt):
                return DOCKER_MSG
    addon = (c == "curl" and any(ADDON_URL.search(x) for x in a)) or (
        c == "ha" and a[:1] and a[0] in ("addons", "apps", "addon", "app") and a[1:2] == ["info"]
    )
    if addon and not (selective(rest) or to_file or "-o" in a or "--output" in a):
        return ADDON_MSG
    if c == "ot-ctl" and a and not ot_filtered(rest):
        if a[0] in ("networkkey", "pskc") or (
            a[0] == "dataset"
            and a[1:2]
            and a[1] in ("active", "pending", "networkkey", "pskc", "tlvs")
        ):
            return OT_MSG
    if c == "gitleaks" and not any(x.startswith("--redact") for x in a):
        if not any(x in ("version", "help", "--version", "-h", "--help") for x in a):
            return GITLEAKS_MSG
    interp = bool(INTERP.fullmatch(c)) or c in SHELLS
    module = None
    if PYTHON.fullmatch(c):
        pos, opts, _flags = parse_args(a, {"-c", "-m", "-W", "-X"})
        for code in opts.get("-c", []):
            r = check_python(code)
            if r:
                return r
        module = (opts.get("-m") or [None])[0]
        if module in DUMP_MODULES:
            interp = False  # json.tool & co. er bare en anden `cat`
            a = pos
    # omdirigeringer: < credential-fil og > credential-fil
    for op, t in redirs:
        if op.startswith("<<"):
            continue
        for p in candidates(t, cwd):
            lab = protected(p)
            if lab and "<" in op and not (c in STDIN_OK or (interp and module is None)):
                return file_msg(c or "<", lab)
            if lab and ">" in op:
                return write_msg(lab)
    if not w or (interp and module not in DUMP_MODULES):
        return None
    if c in TRANSMIT:
        skip, keep, k = TRANSMIT_KEEP.get(c, SSH_KEEP), [], 0
        while k < len(a):
            if a[k] in skip:
                k += 2
                continue
            keep.append(a[k])
            k += 1
        hits = [lab for t in keep for p in candidates(t, cwd) if (lab := protected(p))]
        if hits:
            return send_msg(c, hits[0])
        if c in ("rsync", "scp") and recursive_copy(c, keep):
            for t in keep:
                if t.startswith("-") or REMOTE.match(t):
                    continue
                for p in candidates(t, cwd):
                    hits = os.path.isdir(p) and reached(p, cwd, aware=False, hidden_ok=True)
                    if hits:
                        return send_msg(c, hits[0])
        return None
    if c == "git":
        sub = [x for x in a if not x.startswith("-")]
        if sub[:1] == ["add"] and ({"-f", "--force"} & set(a)):
            hits = [lab for t in sub[1:] for p in candidates(t, cwd) if (lab := protected(p))]
            if hits:
                return write_msg(hits[0])
        if sub[:1] == ["diff"] and "--no-index" in a:
            hits = [lab for t in sub[1:] for p in candidates(t, cwd) if (lab := protected(p))]
            if hits:
                return file_msg("git diff --no-index", hits[0])
        return None
    if c == "find":
        roots, names, exe = parse_find(a)
        if not exe:
            return None
        ew = unwrap(exe)[0]
        ec = name(ew[0]) if ew else ""
        if (
            not ec
            or ec in SAFE
            or INTERP.fullmatch(ec)
            or (ec in GREPS and grep_names_only(ec, ew[1:]))
        ):
            return None
        for root in roots:
            for p in candidates(root, cwd):
                hits = reached(p, cwd, aware=False, hidden_ok=True, names=names)
                if hits:
                    return recursive_msg(f"find -exec {ec}", hits[0])
        return file_hits(ec, ew[1:], cwd, {"aware": False, "first": False})
    if c == "tee":
        hits = [lab for t in a for p in candidates(t, cwd) if (lab := protected(p))]
        return write_msg(hits[0]) if hits else None
    if c == "tar":
        bundled = bool(a) and not a[0].startswith("-") and "O" in a[0]  # tar xOf x.tar
        if not ("--to-stdout" in a or "O" in short_flags(a) or bundled):
            return None
    elif c in SAFE:
        return None
    if "xargs" in notes and not (c in GREPS and grep_names_only(c, a)):
        for up in pipe[:i]:
            uw = unwrap(up[0])[0]
            if uw and name(uw[0]) == "find":
                roots, names, _exe = parse_find(uw[1:])
                for root in roots:
                    for p in candidates(root, cwd):
                        hits = reached(p, cwd, aware=False, hidden_ok=True, names=names)
                        if hits:
                            return recursive_msg(f"find | xargs {c}", hits[0])
    aware = depth == 0 and "binary" not in notes and "/" not in w[0] and not w[0].startswith("\\")
    return file_hits(c, a, cwd, {"aware": aware, "first": i == 0 and not redirs})


def file_hits(c, a, cwd, ctx):
    """Block a reader whose arguments, or recursion, reach a credential file."""
    rec = None
    if c in GREPS:
        rg = c in RGLIKE
        pos, opts, flags = parse_args(a, RG_ARG if rg else GREP_ARG)
        short, longs = short_flags(flags), set(flags)
        if grep_names_only(c, a):
            return None
        glued = any(re.fullmatch(r"-[A-Za-z]*[ef].+", f) for f in flags)  # -epattern
        if not (glued or any(k in opts for k in ("-e", "--regexp", "-f", "--file"))):
            pos = pos[1:]
        paths = pos + opts.get("-f", []) + opts.get("--file", [])
        directories = opts.get("-d", []) + opts.get("--directories", [])
        recursive = rg or c == "ack" or "recurse" in directories
        recursive = (
            recursive
            or bool(set(short) & set("rR"))
            or bool(longs & {"--recursive", "--dereference-recursive"})
        )
        if recursive:
            unrestricted = "u" in short or longs & {
                "--no-ignore",
                "--no-ignore-vcs",
                "--unrestricted",
            }
            hidden_ok = not rg or "." in short or short.count("u") >= 2 or "--hidden" in longs
            if rg:
                globs = opts.get("-g", []) + opts.get("--glob", []) + opts.get("--iglob", [])
                includes = [g for g in globs if not g.startswith("!")]
                for t in opts.get("-t", []) + opts.get("--type", []):
                    includes += RG_TYPES.get(t, [f"*.{t}"])
                excludes = [g[1:] for g in globs if g.startswith("!")]
                xdirs = excludes
            else:
                includes, excludes = opts.get("--include", []), opts.get("--exclude", [])
                xdirs = opts.get("--exclude-dir", [])
            roots = [p for t in pos for p in candidates(t, cwd) if os.path.isdir(p)]
            if not pos and ctx["first"]:
                roots = [cwd]
            rec = (roots, ctx["aware"] and not unrestricted, hidden_ok, includes, excludes, xdirs)
    elif c == "sed":
        pos, opts, _flags = parse_args(a, {"-e", "--expression", "-f", "--file", "-l"})
        if not any(k in opts for k in ("-e", "--expression", "-f", "--file")):
            pos = pos[1:]
        paths = pos + opts.get("-f", []) + opts.get("--file", [])
    elif c in ("awk", "gawk", "mawk", "nawk"):
        pos, opts, _flags = parse_args(
            a, {"-F", "-v", "-f", "--field-separator", "--assign", "--file"}
        )
        if not any(k in opts for k in ("-f", "--file")):
            pos = pos[1:]
        paths = pos + opts.get("-f", []) + opts.get("--file", [])
    elif c in ("jq", "yq", "gojq", "jaq"):
        two = {"--arg", "--argjson", "--slurpfile", "--rawfile"}
        pos, opts, _flags = parse_args(a, {"--indent", "-f", "--from-file", "-L"}, two)
        if not any(k in opts for k in ("-f", "--from-file")):
            pos = pos[1:]
        paths = pos + opts.get("-f", []) + opts.get("--from-file", [])
        paths += opts.get("--slurpfile", [])[1::2] + opts.get("--rawfile", [])[1::2]
    else:
        paths = list(a)  # tal og flag rammer aldrig et lager
    for t in paths:
        for p in candidates(t, cwd):
            lab = protected(p)
            if lab:
                return file_msg(c, lab)
    if rec:
        roots, aware, hidden_ok, includes, excludes, xdirs = rec
        for root in roots:
            hits = reached(root, cwd, aware, hidden_ok, includes, excludes, xdirs)
            if hits:
                return recursive_msg(c, hits[0])
    return None


def check(data):
    """The reason to block this tool call, or None."""
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if tool == "Bash":
        return check_bash(ti.get("command", ""), cwd)
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        lab = protected(os.path.join(cwd, os.path.expanduser(p))) if p else None
        if lab:
            return file_msg("Read", lab) if tool == "Read" else write_msg(lab)
    if tool == "Grep" and ti.get("output_mode") == "content":  # andre modes: kun navne/antal
        p = os.path.normpath(os.path.join(cwd, os.path.expanduser(ti.get("path") or cwd)))
        lab = protected(p)
        if lab:
            return file_msg("Grep", lab)
        if os.path.isdir(p):
            g, t = ti.get("glob"), ti.get("type")
            includes = braces(g) if g else RG_TYPES.get(t, [f"*.{t}"]) if t else ()
            hits = reached(p, cwd, aware=True, hidden_ok=True, includes=includes)
            if hits:
                return recursive_msg("Grep", hits[0])
    return None


def main():
    try:
        reason = check(json.load(sys.stdin))
    except Exception:
        return 0
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
