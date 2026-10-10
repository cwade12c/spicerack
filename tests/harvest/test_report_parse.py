"""The ledger-format rules skills/harvest/scripts/report.py depends on. Standard library only.

    python3 -m unittest discover -s tests/harvest -p 'test_report_parse.py'
"""
import argparse
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "skills/harvest/scripts"))
import report  # noqa: E402

HEADER = """# Harvest ledger: origin/main → upstream/main

Base: upstream/main @ 4be19e2
Head: origin/main @ 8c1d2e0
Merge-base: 3f2a91c
Updated: 2026-10-02 16:40
"""


def entry(eid, depends="none", status="open", title="A feature", extra=""):
    return f"""
### {eid}. {title}

Does a thing.
Why: unstated.

- Size: +1 / -0 across 1 file
- Commits: abc1234
- Files: 1 (0 shared). Source: a.py
- Depends on: {depends}
- Fit: aligned. Fine.
- Status: {status}
{extra}"""


def parse(*entries, header=HEADER):
    h, es, warns = report.parse_ledger(header + "".join(entries))
    return h, {e["id"]: e for e in es}, warns


class Header(unittest.TestCase):
    def test_key_value_lines(self):
        h, _, warns = parse(entry("F1"))
        self.assertEqual((h["base"], h["base_sha"], h["head"], h["head_sha"]), ("upstream/main", "4be19e2", "origin/main", "8c1d2e0"))
        self.assertEqual(warns, [])

    def test_backticks_and_bullets_are_tolerated(self):
        hdr = "# L\n\n- Base: `upstream/main` @ `bde999b37c92`\n- Head: `curry` @ `45e5e40e80f4`\n- Merge-base: `0748ff9`\n- Updated: now\n"
        h, _, warns = parse(entry("F1"), header=hdr)
        self.assertEqual((h["base"], h["base_sha"], h["head_sha"], h["merge_base"]), ("upstream/main", "bde999b37c92", "45e5e40e80f4", "0748ff9"))
        self.assertEqual(warns, [])

    def test_report_line_sets_the_ingested_round(self):
        h, _, _ = parse(entry("F1"), header=HEADER + "Report: round 2 ingested 2026-10-09\n")
        self.assertEqual(h["ingested_round"], 2)

    def test_set_aside_bullets_outside_entries_are_reported(self):
        _, _, warns = parse(entry("F1"), header=HEADER + "\n- `landed: already on base` — PR #1\n")
        self.assertTrue(any("set-aside item(s) listed outside" in w for w in warns), warns)


class DependsOn(unittest.TestCase):
    def test_ids_with_reasons(self):
        _, e, _ = parse(entry("F1"), entry("F2"), entry("F3", "F1 (reads its table), F2"))
        self.assertEqual(e["F3"]["depends"], ["F1", "F2"])

    def test_ids_in_parentheses_and_after_the_semicolon_are_prose(self):
        _, e, _ = parse(entry("F1"), entry("F2"), entry("F5"), entry("F9"), entry("F3", "F2 (not F5); unlike F9, no hook"))
        self.assertEqual(e["F3"]["depends"], ["F2"])

    def test_a_range_is_expanded_with_a_warning(self):
        _, e, warns = parse(entry("F1"), entry("F2"), entry("F3"), entry("F4", "F1-F3 (builds them all)"))
        self.assertEqual(e["F4"]["depends"], ["F1", "F2", "F3"])
        self.assertIn("F4: Depends on names the range F1-F3; name each id", warns)

    def test_cuts(self):
        _, e, warns = parse(entry("F3"), entry("F4"), entry("F5", "F4 (hooks it), F3; cut F4: land with a manual hook; then F3's table; cut F3: stub it"))
        self.assertEqual(e["F5"]["depends"], ["F4", "F3"])
        self.assertEqual(e["F5"]["cuts"], {"F4": "land with a manual hook; then F3's table", "F3": "stub it"})
        self.assertEqual(warns, [])

    def test_a_cut_must_name_a_listed_dependency(self):
        _, e, warns = parse(entry("F3"), entry("F4"), entry("F5", "F4; cut: whatever"), entry("F6", "F4; cut F3: no"))
        self.assertEqual((e["F5"]["cuts"], e["F6"]["cuts"]), ({}, {}))
        self.assertTrue(any(w.startswith("F5: a cut must name") for w in warns), warns)
        self.assertIn("F6: cuts F3, which is not in its Depends on ids", warns)


    def test_a_dependency_cut_twice_warns_and_keeps_the_last(self):
        _, e, warns = parse(entry("F4"), entry("F5", "F4; cut F4: first; cut F4: second"))
        self.assertEqual(e["F5"]["cuts"], {"F4": "second"})
        self.assertIn("F5: cuts F4 twice; keep one clause (the last one is read)", warns)


class StaleCuts(unittest.TestCase):
    """check reports a cut whose dependency is picked or landed once the file is applied."""

    def check(self, f4_status="open", f4_mode=None):
        led = HEADER + entry("F4", status=f4_status) + entry("F5", "F4 (hooks it); cut F4: a manual hook", status="picked: rebuild")
        entries = {"F4": {"title": "A feature", "status": f4_status, "mode": f4_mode}} if f4_mode else {}
        resp = {"schema": "harvest-responses/1", "round": 1, "created": "2026-10-09T00:00:00Z", "general_notes": "",
                "ledger": {"name": "x.md", "sha256": report.sha256(led), "head": "origin/main", "head_sha": "8c1d2e0",
                           "base": "upstream/main", "base_sha": "4be19e2", "updated": "2026-10-02 16:40"},
                "entries": entries}
        with tempfile.TemporaryDirectory() as d:
            lp, rp = pathlib.Path(d, "x.md"), pathlib.Path(d, "r.json")
            lp.write_text(led)
            rp.write_text(json.dumps(resp))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = report.cmd_check(argparse.Namespace(responses=str(rp), ledger=str(lp)))
        return code, buf.getvalue()

    def test_reported_when_the_file_picks_the_dependency(self):
        code, out = self.check(f4_mode="cherry-pick")
        self.assertIn("STALE CUT F5→F4: F4 is picked; drop the cut", out)
        self.assertEqual(code, 0)

    def test_reported_when_the_ledger_has_the_dependency_landed(self):
        code, out = self.check(f4_status="landed: harvest/retries")
        self.assertIn("STALE CUT F5→F4: F4 is landed; drop the cut", out)
        self.assertEqual(code, 0)

    def test_not_reported_while_the_dependency_is_unpicked(self):
        code, out = self.check(f4_mode="left")
        self.assertNotIn("STALE CUT", out)
        self.assertNotIn("DEPENDENCY", out)
        self.assertEqual(code, 0)


class Entries(unittest.TestCase):
    def test_kinds_and_order(self):
        _, e, warns = parse(entry("F2", "F1"), entry("F1"), entry("Plumbing", title="Bumps"), entry("S1", status="landed: already on base"))
        self.assertEqual([x["kind"] for x in sorted(e.values(), key=lambda x: x["order"])], ["feature", "feature", "plumbing", "setaside"])
        self.assertLess(e["F1"]["order"], e["F2"]["order"])
        self.assertEqual(warns, [])

    def test_heading_without_title(self):
        _, _, warns = parse("\n### Plumbing\n" + entry("F1").split("\n", 2)[2])
        self.assertIn("Plumbing: heading has no title; write '### Plumbing. <title>'", warns)

    def test_fit_must_lead_with_its_word(self):
        _, e, warns = parse(entry("F1").replace("Fit: aligned", "Fit: mostly aligned"))
        self.assertEqual(e["F1"]["fit"], "?")
        self.assertTrue(any(w.startswith("F1: Fit does not start") for w in warns), warns)

    def test_notes(self):
        notes = ("- Notes:\n  - 2026-10-09 Q (r1.q2): Shared retention? A: No, `deadletter.py:31`.\n"
                 "  - 2026-10-09 Note (r1.q3): Manual hook is fine.\n  - 2026-10-07 Q: Thread? A: Only the timer.\n  - Evidence: on base.\n")
        _, e, _ = parse(entry("F1", extra=notes))
        n = e["F1"]["notes"]
        self.assertEqual([(x["kind"], x.get("qid")) for x in n], [("question", "r1.q2"), ("note", "r1.q3"), ("question", None), ("plain", None)])
        self.assertEqual((n[0]["text"], n[0]["answer"]), ("Shared retention?", "No, `deadletter.py:31`."))

    def test_a_section_after_the_last_entry_is_not_its_body(self):
        _, e, warns = parse(entry("F1"), "\n## Appendix\n\nSome closing words.\n")
        self.assertEqual(warns, [])
        self.assertNotIn("closing", e["F1"]["raw"])


if __name__ == "__main__":
    unittest.main()
