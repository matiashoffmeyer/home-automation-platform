"""The git hooks, the Makefile, CI and the pinned tool versions agree.

ADR: the platform runs its checks three ways. The production host commits
through git hooks (scripts/pre-commit-hook.sh, scripts/pre-push-hook.sh), a
developer runs Makefile targets, and CI runs those same targets in the public
repository. A check that lives in only one of them silently stops running in
the others, and a tool pinned to two different versions formats the same file
two ways. These tests turn both kinds of drift into a failing commit.

Each hook check is identified by its script, its subcommand and its --check
value, e.g. ``ha_validate.py --check dups``. A hook check that CI cannot run is
listed in NOT_IN_CI, with the reason.
"""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ("scripts/pre-commit-hook.sh", "scripts/pre-push-hook.sh")

NOT_IN_CI = {
    "backlog_ids.py": "checks the private backlog, which is not published",
    "roster_drift.py": "advisory, and only meaningful on a staged diff",
    "ha_validate.py --check hazards": "advisory: the hook lists hazards and never blocks",
    "ha_validate.py --check jinja": (
        "advisory and line-based; Home Assistant's own check (ha_offline.py) compiles"
        " every template"
    ),
    "ha_validate.py --check refs": "needs the running Home Assistant's entity registry",
    "ha_validate.py --check stale_whitelist": "needs the running Home Assistant",
}

_INVOCATION = re.compile(r"\bpython3\s+(?:\S*/)?scripts/(\w+\.py)((?:[ \t]+[^\s|;&)]+)*)")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _checks(path: Path) -> set[str]:
    """The script checks a shell file or Makefile runs (comments and messages skipped)."""
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.strip()
        if code.startswith(("#", "echo")):
            continue
        for script, rest in _INVOCATION.findall(code):
            args = rest.split()
            name = script
            if args and re.fullmatch(r"[a-z][a-z_-]*", args[0]):
                name += f" {args[0]}"
            check = re.search(r"--check\s+(\w+)", rest)
            if check:
                name += f" --check {check.group(1)}"
            found.add(name)
    return found


def _make_targets() -> dict[str, str]:
    """Target name -> its recipe, from the Makefile."""
    targets: dict[str, str] = {}
    current = None
    for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
        head = re.match(r"^([a-z][a-z-]*):", line)
        if head:
            current = head.group(1)
            targets[current] = line
        elif line.startswith("\t") and current:
            targets[current] += "\n" + line
    return targets


def _requirement_pins() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==(\S+)", line)
        if m:
            pins[m.group(1).lower()] = m.group(2)
    return pins


def _ci() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


class HookChecksRunInCI(unittest.TestCase):
    def test_every_hook_check_is_a_make_target_or_excused(self) -> None:
        hooks = set().union(*(_checks(ROOT / h) for h in HOOKS))
        make = _checks(ROOT / "Makefile")
        missing = sorted(hooks - make - NOT_IN_CI.keys())
        self.assertEqual(missing, [], "hook checks that neither the Makefile nor NOT_IN_CI covers")

    def test_excuses_are_current(self) -> None:
        hooks = set().union(*(_checks(ROOT / h) for h in HOOKS))
        stale = sorted(NOT_IN_CI.keys() - hooks)
        self.assertEqual(stale, [], "NOT_IN_CI entries no hook runs any more")

    def test_parser_sees_the_known_checks(self) -> None:
        # Guards the regex: if it stopped matching, the tests above would pass empty.
        hooks = set().union(*(_checks(ROOT / h) for h in HOOKS))
        for known in ("secrets_contract.py", "ha_offline.py check", "ha_validate.py --check dups"):
            self.assertIn(known, hooks)

    def test_hook_tools_are_in_make_lint(self) -> None:
        hook = (ROOT / "scripts/pre-commit-hook.sh").read_text(encoding="utf-8")
        lint = _make_targets()["lint"]
        for tool in ("ruff", "yamllint"):
            self.assertIn(f"dev_tool {tool}", hook)
            self.assertIn(f"\t{tool} ", lint)

    def test_hook_unit_tests_are_collected_by_pytest(self) -> None:
        hook = (ROOT / "scripts/pre-commit-hook.sh").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for test_dir in set(re.findall(r"unittest discover .*?-s (\S+)", hook)):
            self.assertRegex(pyproject, rf'testpaths = \[[^]]*"{re.escape(test_dir)}"')
        self.assertIn("\tpytest", _make_targets()["test"])


class CIRunsTheMakeTargets(unittest.TestCase):
    def test_ci_target_lists_every_job(self) -> None:
        targets = _make_targets()
        ci_deps = targets["ci"].split("\n")[0].split(":", 1)[1].split("##")[0].split()
        jobs = _ci()["jobs"]
        run_targets = []
        for name, job in jobs.items():
            runs = [s["run"] for s in job["steps"] if "run" in s]
            self.assertEqual(len(runs), 1, f"job {name} should run exactly one make target")
            m = re.fullmatch(r"make ([a-z-]+)", runs[0].strip())
            self.assertIsNotNone(m, f"job {name} runs {runs[0]!r}, not a make target")
            assert m is not None
            self.assertIn(m.group(1), targets)
            run_targets.append(m.group(1))
        self.assertEqual(sorted(run_targets), sorted(ci_deps))

    def test_jobs_run_in_public_repositories_only(self) -> None:
        for name, job in _ci()["jobs"].items():
            self.assertEqual(job.get("if"), "github.event.repository.private == false", name)

    def test_ci_token_is_read_only(self) -> None:
        self.assertEqual(_ci()["permissions"], {"contents": "read"})

    def test_actions_are_pinned_to_commit_shas(self) -> None:
        for name, job in _ci()["jobs"].items():
            for step in job["steps"]:
                if "uses" in step:
                    ref = step["uses"].rsplit("@", 1)[1]
                    self.assertRegex(ref, _FULL_SHA, f"{name}: {step['uses']}")


class PinnedVersionsAgree(unittest.TestCase):
    def setUp(self) -> None:
        cfg = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
        text = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        self.frozen = dict(
            re.findall(r"github\.com/[\w-]+/([\w-]+)\n\s+rev: [0-9a-f]{40} # frozen: v(\S+)", text)
        )
        self.repos = [r for r in cfg["repos"] if r["repo"] != "local"]

    def test_hook_revisions_are_frozen_shas(self) -> None:
        for repo in self.repos:
            self.assertRegex(repo["rev"], _FULL_SHA, repo["repo"])
        self.assertEqual(len(self.frozen), len(self.repos), "every rev needs a '# frozen: vX' tag")

    def test_python_tools_match_requirements(self) -> None:
        pins = _requirement_pins()
        self.assertEqual(self.frozen["ruff-pre-commit"], pins["ruff"])
        self.assertEqual(self.frozen["yamllint"], pins["yamllint"])

    def test_gitleaks_matches_dev_setup(self) -> None:
        setup = (ROOT / "scripts/dev_setup.sh").read_text(encoding="utf-8")
        version = re.search(r"^GITLEAKS_VERSION=(\S+)$", setup, re.M)
        assert version is not None
        self.assertEqual(self.frozen["gitleaks"], version.group(1))


if __name__ == "__main__":
    unittest.main()
