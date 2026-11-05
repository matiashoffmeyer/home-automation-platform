"""The one secrets reader, and the static contract that keeps it the only one.

python3 -m unittest discover -s scripts/tests -p "test_ha_secrets*.py"

All keys and values here are synthetic.
"""

import ast
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ha_secrets  # noqa: E402
import secrets_contract as sc  # noqa: E402


class Parse(unittest.TestCase):
    def test_scalar_forms_read_like_yaml(self):
        got = ha_secrets.parse(
            textwrap.dedent("""\
            # a comment line
            plain: abc123
            plain_comment: abc123 # trailing comment
            plain_hash: http://example.test/#fragment
            url: https://example.test:8443/path?a=b
            double: "two words # not a comment"
            double_escape: "say \\"hi\\" \\\\ bye"
            single: 'it''s # kept'
            number: 52.3731

            key with space: ignored
            no_colon_line
            """)
        )
        self.assertEqual(
            got,
            {
                "plain": "abc123",
                "plain_comment": "abc123",
                "plain_hash": "http://example.test/#fragment",
                "url": "https://example.test:8443/path?a=b",
                "double": "two words # not a comment",
                "double_escape": 'say "hi" \\ bye',
                "single": "it's # kept",
                "number": "52.3731",
            },
        )

    def test_first_occurrence_wins(self):
        self.assertEqual(ha_secrets.parse("k: first\nk: second\n"), {"k": "first"})


class Get(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "s.yaml"
        path.write_text('present: "value-one"\nempty: ""\n', encoding="utf-8")
        self.saved, ha_secrets.SECRETS_FILE = ha_secrets.SECRETS_FILE, path

    def tearDown(self):
        ha_secrets.SECRETS_FILE = self.saved
        self.tmp.cleanup()

    def test_present(self):
        self.assertEqual(ha_secrets.get("present"), "value-one")

    def test_missing_or_empty_raises_without_the_value(self):
        for key in ("absent", "empty"):
            with self.assertRaises(ha_secrets.SecretMissing) as cm:
                ha_secrets.get(key)
            self.assertIn(key, str(cm.exception))
            self.assertNotIn("value-one", str(cm.exception))

    def test_optional_returns_none(self):
        self.assertIsNone(ha_secrets.get("absent", required=False))
        self.assertIsNone(ha_secrets.get("empty", required=False))

    def test_missing_file_is_empty(self):
        ha_secrets.SECRETS_FILE = Path(self.tmp.name) / "nope.yaml"
        self.assertEqual(ha_secrets.load(), {})
        self.assertIsNone(ha_secrets.get("present", required=False))


class Put(unittest.TestCase):
    SECRET = "Syn-th3tic-Value"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "s.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text, mode=0o600):
        self.path.write_text(text, encoding="utf-8")
        os.chmod(self.path, mode)

    def text(self, name="s.yaml"):
        return (self.dir / name).read_bytes().decode("utf-8")

    def test_new_key_is_appended_and_every_other_byte_kept(self):
        self.write("# header\nother: 'x' # note\nno_newline: y")
        self.assertTrue(ha_secrets.put("fresh", "v-1", self.path))
        self.assertEqual(
            self.text(), "# header\nother: 'x' # note\nno_newline: y\nfresh: \"v-1\"\n"
        )

    def test_existing_key_is_replaced_in_place_and_the_old_file_kept(self):
        self.write("a: 1\r\nkey: old # comment\r\nb: 2\r\n", mode=0o640)
        self.assertFalse(ha_secrets.put("key", "new", self.path))
        self.assertEqual(self.text(), 'a: 1\r\nkey: "new"\r\nb: 2\r\n')
        self.assertEqual(self.text("s.yaml.prev"), "a: 1\r\nkey: old # comment\r\nb: 2\r\n")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["s.yaml", "s.yaml.prev"])

    def test_a_missing_file_is_created_private(self):
        self.assertTrue(ha_secrets.put("a", "1", self.path))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_awkward_values_read_back_as_written(self):
        values = ['quo"te', "back\\slash", "ends\\", '\\"', "hash # x", "æøå: 'x'", " lead", "€"]
        for i, value in enumerate(values):
            ha_secrets.put(f"k{i}", value, self.path)
        self.assertEqual(ha_secrets.load(self.path), {f"k{i}": v for i, v in enumerate(values)})

    def test_refuses_what_it_cannot_write_safely_and_never_names_the_value(self):
        before = "multi: |\n  one\nfolded: >\n  x\nnested:\n  inner: 1\ntwice: a\ntwice: b\n"
        self.write(before)
        cases = [
            ("multi", self.SECRET),  # block scalar
            ("folded", self.SECRET),
            ("nested", self.SECRET),  # a mapping under the key
            ("inner", self.SECRET),  # only indented: the new line would not be read first
            ("twice", self.SECRET),
            ("bad key", self.SECRET),
            ("ok", ""),
            ("ok", self.SECRET + "\nsecond line"),
            ("ok", self.SECRET + "\tTab"),
        ]
        for key, value in cases:
            with self.subTest(key=key), self.assertRaises(ValueError) as cm:
                ha_secrets.put(key, value, self.path)
            self.assertNotIn(self.SECRET, str(cm.exception))
        self.assertEqual(self.text(), before)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["s.yaml"])


class Contract(unittest.TestCase):
    LIB = {"HA_API_TOKEN": "ha_api_token"}

    def scan(self, source, rel="scripts/x.py"):
        tree = ast.parse(textwrap.dedent(source))
        keys, errors = {}, []
        sc.python_keys(rel, tree, self.LIB, keys, errors)
        sc.python_paths(rel, tree, errors)
        return keys, errors

    def test_keys_resolve_from_literals_and_constants(self):
        keys, errors = self.scan("""\
            import ha_secrets
            SHEET_KEY = "sheet_id"
            TOKEN_KEY = ha_secrets.HA_API_TOKEN
            ha_secrets.get("literal_key")
            ha_secrets.get(SHEET_KEY, required=False)
            ha_secrets.get(TOKEN_KEY)
            ha_secrets.get(ha_secrets.HA_API_TOKEN)
            """)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(keys), ["ha_api_token", "literal_key", "sheet_id"])
        self.assertEqual(len(keys["ha_api_token"]), 2)

    def test_hidden_keys_are_errors(self):
        _, errors = self.scan("""\
            import ha_secrets
            from ha_secrets import get
            import ha_secrets as hs
            def f(name):
                return ha_secrets.get(name)
            everything = ha_secrets.load()
            """)
        self.assertEqual(len(errors), 4, errors)

    def test_only_the_writer_may_put(self):
        source = "import ha_secrets\nha_secrets.put('k', 'v')\n"
        self.assertEqual(len(self.scan(source)[1]), 1)
        self.assertEqual(self.scan(source, rel="scripts/secret_set.py")[1], [])

    def test_second_path_to_the_file_is_an_error_but_prose_is_not(self):
        _, errors = self.scan('''\
            """Docstrings may say /config/secrets.yaml."""
            HINT = "token missing from secrets.yaml"
            PATH = "/config/secrets.yaml"
            ''')
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(":3:", errors[0])

    def test_yaml_tags_outside_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved, sc.REPO = sc.REPO, Path(tmp)
            try:
                (Path(tmp) / "a.yaml").write_text(
                    "x: !secret real_key\n# y: !secret commented_key\n", encoding="utf-8"
                )
                self.assertEqual(sc.yaml_keys(["a.yaml"]), {"real_key": ["a.yaml:1"]})
            finally:
                sc.REPO = saved


if __name__ == "__main__":
    unittest.main()
