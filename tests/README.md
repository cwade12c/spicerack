# Tests

Development-only tests, one folder per item. Nothing here ships with a skill: install tools never copy this folder.

## harvest

- `harvest/test_report_parse.py`: the ledger-format rules `scripts/report.py` relies on. Standard library only.
- `harvest/test_report_page.py`: the review page end to end in a real browser, driven by Playwright. It covers a keyboard-driven round 1, protocol parity, focus handling, round 2, a cut recorded in the ledger, a phone viewport, and a 40-entry ledger.
- `harvest/fixtures/`: a synthetic ledger before and after round 1, and `v1-responses-r1.json`, the responses file the round-1 prototype exported. The parity check needs the page to export that exact file from the same decisions. The file records the ledger's SHA-256, so keep `origin-main.md` byte-for-byte.

```bash
python3 -m unittest discover -s tests/harvest -p 'test_report_parse.py'
uv run --no-project --with playwright python tests/harvest/test_report_page.py --browser all   # Chromium, then Firefox
```

The page test needs Playwright's browsers (`playwright install chromium firefox`). It writes the rendered pages, the exported files and screenshots to `harvest/out/<browser>/`, which git ignores. Look at the screenshots after a template change.
