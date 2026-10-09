"""Round 1 end to end with Playwright: render, mark up, reload, restart browser, export, copy, FSA, validate."""
import json, pathlib, shutil, subprocess, sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE / "out"; SHOTS = HERE / "shots"
shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir(); SHOTS.mkdir(exist_ok=True)
PROFILE = OUT / "profile"

def sh(*a):
    r = subprocess.run([sys.executable, str(HERE / "render_report.py"), *a], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip()); return r

assert sh("render", str(HERE / "fixture/origin-main.md"), "-o", str(OUT / "report.html")).returncode == 0
URL = (OUT / "report.html").as_uri()

def mark(page, eid, mode):
    page.click(f'#row-{eid} button[data-m="{mode}"]')

def expand(page, eid):
    if not page.locator(f"#row-{eid}.open").count():
        page.click(f"#row-{eid} .title")

def ask(page, eid, text, kind="question"):
    expand(page, eid)
    page.locator(f'tr.detail:has(textarea[data-k="c:{eid}"]) input[value="{kind}"]').check()
    page.fill(f'textarea[data-k="c:{eid}"]', text)
    page.click(f'tr.detail button[data-act="addc"][data-id="{eid}"]')

def snapshot(page):
    return page.evaluate("JSON.parse(JSON.stringify(window.__harvest.buildResponses()))")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=True, viewport={"width": 1320, "height": 900},
                                               accept_downloads=True, permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e))); page.on("console", lambda m: m.type == "error" and errs.append(m.text))
    page.goto(URL)
    assert page.locator("tr.main").count() == 21, page.locator("tr.main").count()
    # order: features in dependency order, then Plumbing, Head-only, set-aside
    ids = page.eval_on_selector_all("tr.main", "r => r.map(x => x.id.slice(4))")
    assert ids[-4:] == ["Plumbing", "Head-only", "S1", "S2"], ids
    pos = {i: n for n, i in enumerate(ids)}
    for e, deps in {"F4": ["F3", "F1"], "F5": ["F4", "F3"], "F12": ["F11", "F10"], "F17": ["F3", "F2", "F7"]}.items():
        assert all(pos[d] < pos[e] for d in deps), (e, deps)
    page.screenshot(path=str(SHOTS / "00-initial.png"))

    # marks
    mark(page, "F2", "cherry-pick"); page.fill('input[data-k="batch:F2"]', "config")
    mark(page, "F3", "rework");      page.fill('input[data-k="batch:F3"]', "storage")
    mark(page, "F6", "rework");      page.fill('input[data-k="batch:F6"]', "storage")
    mark(page, "F4", "left")
    mark(page, "F5", "rebuild")          # depends on F4 (left) -> warning
    mark(page, "F9", "cherry-pick")      # depends on F1 (landed) -> no warning
    mark(page, "F12", "left")
    mark(page, "F10", "rework")          # depends on F9 (picked) -> fine
    # F8 stays as the ledger had it (picked: cherry-pick, shutdown); F14 stays left
    assert page.locator("#row-F5.haswarn").count() == 1
    assert page.locator("#row-F9.haswarn").count() == 0
    assert page.locator("#row-F4.haswarn").count() == 1, "F4 is left but a picked entry needs it"
    assert "1 dependency warning" in page.inner_text("#counts")

    # questions and notes
    ask(page, "F3", "ADR-002 says job state is in memory. Is the SQLite file optional, or always on?")
    ask(page, "F5", "Does the dead-letter table share the job table's retention policy?")
    ask(page, "F5", "If F4 stays left, can F5 still land with a manual retry hook?", "note")
    ask(page, "F10", "Which prometheus-client version, and is it vendored?")
    page.fill("#general", "Land storage before anything that reads the job table. Skip multi-tenancy for now.")
    # the F5 detail panel is the dependency-warning screenshot
    expand(page, "F5")
    page.evaluate("document.getElementById('row-F5').scrollIntoView({block: 'start'}); window.scrollBy(0, -150)")
    page.screenshot(path=str(SHOTS / "03-dependency-warning.png"))

    before = snapshot(page)
    print("entries in export:", sorted(before["entries"]))

    # reload: same page object, then a full browser restart on the same profile
    page.reload()
    assert snapshot(page)["entries"] == before["entries"] and snapshot(page)["general_notes"] == before["general_notes"], "state lost on reload"
    print("reload ok")
    ctx.close()
    ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=True, viewport={"width": 1320, "height": 900},
                                               accept_downloads=True, permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page(); page.goto(URL)
    after = snapshot(page)
    assert after["entries"] == before["entries"], "state lost across browser restart"
    print("browser restart ok")

    # main view screenshot: filter reset, collapse everything, scroll top
    page.screenshot(path=str(SHOTS / "01-main.png"))
    expand(page, "F4")
    page.evaluate("document.getElementById('row-F4').scrollIntoView({block: 'start'}); window.scrollBy(0, -150)")
    page.screenshot(path=str(SHOTS / "02-expanded-entry.png"))

    # Save path 1: export download
    with page.expect_download() as dl:
        page.click('button[data-act="export"]')
    d = dl.value; assert d.suggested_filename == "responses.json"
    d.save_as(OUT / "responses.json")
    # Save path 2: copy
    page.click('button[data-act="copy"]')
    clip = page.evaluate("navigator.clipboard.readText()")
    assert clip.startswith("Harvest responses, round 1") and "```json" in clip
    copied = json.loads(clip.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    # Save path 3: File System Access, with the native picker stubbed by an OPFS handle (headless cannot drive a real dialog)
    print("real API present on file://:", page.evaluate("[typeof window.showSaveFilePicker, window.isSecureContext]"))
    page.evaluate("""() => { window.__file = null; window.showSaveFilePicker = async (o) => ({ name: o.suggestedName,
        queryPermission: async () => 'granted', requestPermission: async () => 'granted',
        createWritable: async () => { let buf = ''; return { write: async t => { buf += t; }, close: async () => { window.__file = buf; } }; } }); }""")
    page.evaluate("document.getElementById('b-fsa').disabled = false")
    page.click('button[data-act="fsa"]')
    page.wait_for_function("document.getElementById('savestate').textContent.includes('writing to responses.json')")
    page.fill('input[data-k="batch:F9"]', "health")      # a change after connecting must be rewritten
    page.wait_for_timeout(900)
    fsa_text = page.evaluate("window.__file")
    fsa = json.loads(fsa_text)
    assert fsa["entries"]["F9"]["batch"] == "health", fsa["entries"].get("F9")
    print("fsa auto-write ok (fake handle standing in for the native picker)")
    print("page errors:", errs)
    ctx.close()

# compare the three paths (ignoring timestamp and the later F9 edit)
exp = json.load(open(OUT / "responses.json"))
for o in (exp, copied, fsa):
    o.pop("created")
    o["entries"]["F9"].pop("batch", None) if o is fsa or o is not fsa else None
fsa["entries"]["F9"].pop("batch", None)
assert exp == copied == fsa, "the three save paths disagree"
print("export == copy == fsa")
r = sh("check", str(OUT / "responses.json"), str(HERE / "fixture/origin-main.md"))
assert r.returncode == 0
print(json.dumps(json.load(open(OUT / "responses.json")), indent=1)[:1800])
