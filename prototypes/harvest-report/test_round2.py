"""Round 2: ledger after ingest + round-1 responses -> answers inline, state from ledger, new round number."""
import json, pathlib, subprocess, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).parent; OUT = HERE / "out"; SHOTS = HERE / "shots"

def sh(*a):
    r = subprocess.run([sys.executable, str(HERE / "render_report.py"), *a], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip()); return r

import shutil
# the by-hand ingest of round 1 (ingest.md applied to the fixture), kept as a fixture so this test is repeatable
shutil.copy(HERE / "fixture/origin-main.after-round1.md", OUT / "ledger-r1.md")
assert sh("render", str(OUT / "ledger-r1.md"), "--responses", str(OUT / "responses.json"), "-o", str(OUT / "report-r2.html")).returncode == 0
# variant: the ledger was NOT updated, the agent put answers into the responses file instead
r1 = json.load(open(OUT / "responses.json"))
r1["entries"]["F3"]["comments"][0]["answer"] = "(answer carried in the responses file)"
json.dump(r1, open(OUT / "responses-answered.json", "w"))
assert sh("render", str(HERE / "fixture/origin-main.md"), "--responses", str(OUT / "responses-answered.json"), "-o", str(OUT / "report-r2-variant.html")).returncode == 0

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1320, "height": 900}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto((OUT / "report-r2.html").as_uri())
    assert "Round 2" in pg.inner_text("#h-sub")
    assert pg.evaluate("window.__harvest.buildResponses().round") == 2
    assert pg.evaluate("Object.keys(window.__harvest.buildResponses().entries).length") == 0, "fresh page must start from the ledger, with nothing to export"
    assert "4 picked" not in pg.inner_text("#counts") and "7 picked" in pg.inner_text("#counts"), pg.inner_text("#counts")
    assert pg.locator("#row-F3 .tag.aligned", has_text="1 answered").count() == 1
    pg.click("#row-F3 .title")
    t = pg.inner_text("tr.detail")
    assert "Optional in head's code" in t and "Q" in t, t
    assert pg.locator("#row-F5.haswarn").count() == 1, "F5 warning must survive into round 2"
    pg.evaluate("document.getElementById('row-F3').scrollIntoView({block: 'start'}); window.scrollBy(0, -150)")
    pg.screenshot(path=str(SHOTS / "04-round2-answers.png"))
    # follow-up question in round 2 gets an r2 id
    pg.fill('textarea[data-k="c:F3"]', "So F4 and F5 hard-depend on the file being on?")
    pg.click('button[data-act="addc"][data-id="F3"]')
    assert pg.evaluate("window.__harvest.buildResponses().entries.F3.comments[0].id") == "r2.q1"
    with pg.expect_download() as dl: pg.click('button[data-act="export"]')
    dl.value.save_as(OUT / "responses-r2.json")
    # the variant page: answers carried by the responses file
    pg.goto((OUT / "report-r2-variant.html").as_uri()); pg.click("#row-F3 .title")
    assert "(answer carried in the responses file)" in pg.inner_text("tr.detail")
    assert "has not been ingested" in pg.inner_text("#banners")
    print("page errors:", errs); b.close()
r = sh("check", str(OUT / "responses-r2.json"), str(OUT / "ledger-r1.md")); assert r.returncode == 0, r.stdout
r = sh("check", str(OUT / "responses.json"), str(OUT / "ledger-r1.md")); assert r.returncode == 1
print("round 2 ok")
