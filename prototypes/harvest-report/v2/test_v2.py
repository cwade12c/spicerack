"""v2 end to end with Playwright: round 1 driven by keyboard, protocol parity with v1, round 2, scale, mobile.

    python3 v2/test_v2.py          # from prototypes/harvest-report; needs python3 playwright + Chromium

Writes v2/out/ (scratch, git-ignored), v2/shots/ (screenshots) and v2/example/ (the round-1 and round-2 pages
and the responses files exported from them).
"""
import json, pathlib, random, shutil, subprocess, sys, time
from playwright.sync_api import sync_playwright

V2 = pathlib.Path(__file__).resolve().parent
ROOT = V2.parent
OUT, SHOTS = V2 / "out", V2 / "shots"
shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir(); SHOTS.mkdir(exist_ok=True)
TPL = str(V2 / "report-template.html")
VIEW = {"width": 1440, "height": 900}


def sh(*a):
    r = subprocess.run([sys.executable, str(ROOT / "render_report.py"), *a], capture_output=True, text=True)
    print("  $ render_report.py", a[0], "->", (r.stdout.strip() or r.stderr.strip()).splitlines()[-1:]); return r


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ok ", msg)


def shot(page, name, full=False):
    page.evaluate("document.getElementById('toastbox').innerHTML = ''")
    page.wait_for_timeout(350)
    page.screenshot(path=str(SHOTS / name), full_page=full)


def key(page, *keys):
    for k in keys:
        page.keyboard.press(k)


def sel(page):
    return page.evaluate("window.__harvest.state && document.querySelector('.row.sel') && document.querySelector('.row.sel').dataset.id")


def responses(page):
    return page.evaluate("JSON.parse(JSON.stringify(window.__harvest.buildResponses()))")


def ask(page, eid, text, note=False):
    page.click(f"#opt-{eid}")
    key(page, "c")
    page.keyboard.type(text)
    key(page, "Shift+Control+Enter" if note else "Control+Enter")
    page.keyboard.press("Escape")


def strip_times(r):
    r = json.loads(json.dumps(r)); r.pop("created", None)
    for e in r["entries"].values():
        for c in e.get("comments", []):
            c.pop("created", None)
    return r


errs = []
with sync_playwright() as p:
    # ------------------------------------------------------------------ round 1
    print("round 1")
    assert sh("render", str(ROOT / "fixture/origin-main.md"), "--template", TPL, "-o", str(OUT / "report.html")).returncode == 0
    URL = (OUT / "report.html").as_uri()
    mk = lambda: p.chromium.launch_persistent_context(str(OUT / "profile"), headless=True, viewport=VIEW, color_scheme="dark",
                                                      accept_downloads=True, permissions=["clipboard-read", "clipboard-write"])
    ctx = mk(); page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e))); page.on("console", lambda m: m.type == "error" and errs.append(m.text))
    page.goto(URL)
    ids = page.eval_on_selector_all(".row", "r => r.map(x => x.dataset.id)")
    check(len(ids) == 21, "21 entries listed")
    check(ids[-4:] == ["Plumbing", "Head-only", "S1", "S2"], "Plumbing, Head-only and set-aside items come last")
    pos = {i: n for n, i in enumerate(ids)}
    check(all(all(pos[d] < pos[e] for d in deps) for e, deps in {"F4": ["F3", "F1"], "F5": ["F4", "F3"], "F12": ["F11", "F10"], "F17": ["F3", "F2", "F7"]}.items()),
          "every dependency is listed before the entries that build on it")
    check(sel(page) == "F2", "opens on the first undecided entry (F2)")
    check("2/18 decided" in page.inner_text("#progress"), "progress starts from the ledger: 2/18 decided (F8 picked, F14 left)")
    shot(page, "00-first-open.png")

    # decide by keyboard: 1/2/3/x mark, b edits the batch, j/k move
    t0 = time.perf_counter()
    key(page, "1", "b"); page.keyboard.type("config"); key(page, "Enter")               # F2 cherry-pick, batch config
    key(page, "j", "2", "b"); page.keyboard.type("storage"); key(page, "Enter")         # F3 rework, storage
    key(page, "j", "x")                                                                 # F4 left
    key(page, "j", "3")                                                                 # F5 rebuild -> needs F4
    key(page, "j", "2", "b"); page.keyboard.type("storage"); key(page, "Enter")         # F6 rework, storage
    page.click("#opt-F9"); key(page, "1")                                               # F9 cherry-pick (F1 landed: fine)
    page.click("#opt-F12"); key(page, "x")                                              # F12 left
    page.click("#opt-F10"); key(page, "2")                                              # F10 rework (F9 picked: fine)
    print(f"  8 decisions by keyboard in {time.perf_counter() - t0:.2f}s")
    check(page.locator("#opt-F5 .rflags .w").count() == 1, "F5 is flagged: it needs F4, which is left")
    check(page.locator("#opt-F9 .rflags .w").count() == 0, "F9 is not flagged: its dependency F1 is landed")
    check("10/18 decided" in page.inner_text("#progress"), "progress reads 10/18 decided")
    check(page.locator(".chip.attn").count() == 1 and "1" in page.inner_text(".chip.attn"), "a 'Needs attention 1' filter appears")

    # undo
    page.click("#opt-F12"); key(page, "1")
    check(responses(page)["entries"]["F12"]["mode"] == "cherry-pick", "F12 re-marked cherry-pick")
    key(page, "u")
    check(responses(page)["entries"]["F12"]["mode"] == "left", "U undoes it: F12 back to left")

    # the dependency, from both sides
    page.click("#opt-F4")
    check("Picked F5 depends on this entry" in page.inner_text("#dscroll"), "F4 explains that picked F5 depends on it")
    page.click("#opt-F5")
    check("F5 needs F4, which is left" in page.inner_text("#dscroll"), "F5 offers ways to resolve the missing dependency")
    shot(page, "01-review-dependency.png")

    # questions and notes
    ask(page, "F3", "ADR-002 says job state is in memory. Is the SQLite file optional, or always on?")
    ask(page, "F5", "Does the dead-letter table share the job table's retention policy?")
    ask(page, "F5", "If F4 stays left, can F5 still land with a manual retry hook?", note=True)
    ask(page, "F10", "Which prometheus-client version, and is it vendored?")
    r = responses(page)
    check([c["id"] for c in r["entries"]["F5"]["comments"]] == ["r1.q2", "r1.q3"] and r["entries"]["F5"]["comments"][1]["kind"] == "note",
          "comment ids are r1.q<n> in order; Shift+Ctrl+Enter makes a note")
    page.click("#opt-F3"); page.evaluate("document.getElementById('conv').scrollIntoView({block:'start'}); document.getElementById('dscroll').scrollBy(0,-170)")
    shot(page, "02-review-conversation.png")

    # plan + general notes
    key(page, "p")
    page.fill("#general", "Land storage before anything that reads the job table. Skip multi-tenancy for now.")
    page.click(".planhead h2")
    check(page.locator(".bstep").count() == 6, "plan shows 6 branches (config, storage, F5, F8, F9, F10)")
    check("harvest/storage" in page.inner_text("#plan") and "branches off harvest/config" in page.inner_text("#plan"),
          "storage lands after config (F3 needs F2)")
    shot(page, "04-plan.png")
    key(page, "m"); page.evaluate("window.__harvest.select('F5')")
    check(page.locator(".edge.bad").count() == 1, "the map draws exactly one unresolved edge (F4 -> F5)")
    page.mouse.move(5, 5)
    shot(page, "03-map.png")
    key(page, "r")

    before = responses(page)
    page.reload()
    check(strip_times(responses(page)) == strip_times(before), "state survives a reload")
    ctx.close(); ctx = mk(); page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e))); page.goto(URL)
    check(strip_times(responses(page)) == strip_times(before), "state survives a browser restart")

    # hand-off: send dialog -> copy, and the download path
    key(page, "s")
    check(page.locator(".dialog .callout.w").count() == 1, "send dialog warns about the one unresolved dependency")
    page.click(".bigsend")
    page.wait_for_selector(".bigsend.done")
    clip = page.evaluate("navigator.clipboard.readText()")
    check(clip.startswith("Harvest responses, round 1 (origin-main.md): 7 picked, 3 left, 3 questions, 1 dependency to cut."),
          "clipboard starts with a one-line summary Claude can read")
    copied = json.loads(clip.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    shot(page, "05-send.png")
    with page.expect_download() as dl:
        page.click('.dialog [data-act="export"]')
    check(dl.value.suggested_filename == "responses-r1.json", "download is named responses-r1.json")
    dl.value.save_as(OUT / "responses-r1.json")
    exported = json.load(open(OUT / "responses-r1.json"))
    check(strip_times(exported) == strip_times(copied), "copy and download carry the same responses")

    # protocol parity: same decisions as v1's test -> same responses file as v1 produced
    v1 = json.load(open(ROOT / "out/responses.json"))
    check(strip_times(exported) == strip_times(v1), "v2's export equals v1's out/responses.json (timestamps aside): schema unchanged")
    check(sh("check", str(OUT / "responses-r1.json"), str(ROOT / "fixture/origin-main.md")).returncode == 0, "render_report.py check: exit 0")

    # cut a dependency (after the parity check: v1's run had no cut)
    page.click("#opt-F5")
    page.click('[data-act="cutedit"][data-id="F5"]')
    page.keyboard.type("Land with a manual retry hook; F4's backoff can follow later.")
    page.click('[data-act="cutdone"][data-id="F5"]')
    r = responses(page)
    check(r["entries"]["F5"]["cuts"] == [{"dep": "F4", "how": "Land with a manual retry hook; F4's backoff can follow later."}], "the cut is exported as {dep, how}")
    check(page.locator(".chip.attn").count() == 0 and page.locator("#opt-F5 .rflags .w").count() == 0, "a cut clears the warning")
    shot(page, "06-review-cut.png")
    key(page, "u")
    check("cuts" not in responses(page)["entries"]["F5"], "the cut can be undone")

    # light theme, help
    page.emulate_media(color_scheme="light")
    page.click("#opt-F3")
    shot(page, "07-review-light.png")
    key(page, "m"); page.mouse.move(5, 5); shot(page, "08-map-light.png"); key(page, "p"); shot(page, "09-plan-light.png"); key(page, "r")
    page.emulate_media(color_scheme="dark")
    key(page, "?"); shot(page, "10-keyboard.png"); key(page, "Escape")
    ctx.close()

    # ------------------------------------------------------------------ mobile
    print("mobile")
    b = p.chromium.launch(headless=True)
    m = b.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark", device_scale_factor=2, is_mobile=True, has_touch=True)
    m.on("pageerror", lambda e: errs.append(str(e)))
    m.goto(URL)
    check(m.evaluate("document.documentElement.scrollWidth <= innerWidth"), "no horizontal page scroll at 390px")
    shot(m, "11-mobile-list.png")
    m.tap("#opt-F5"); m.wait_for_timeout(350)
    m.tap('.mb2[data-m="rebuild"]')
    check(responses(m)["entries"]["F5"]["mode"] == "rebuild", "tap to decide works on a phone")
    shot(m, "12-mobile-detail.png")
    m.close()

    # ------------------------------------------------------------------ round 2
    print("round 2")
    shutil.copy(ROOT / "fixture/origin-main.after-round1.md", OUT / "ledger-r1.md")
    assert sh("render", str(OUT / "ledger-r1.md"), "--responses", str(OUT / "responses-r1.json"), "--template", TPL, "-o", str(OUT / "report-r2.html")).returncode == 0
    pg = b.new_page(viewport=VIEW, color_scheme="dark")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto((OUT / "report-r2.html").as_uri())
    check("round 2" in pg.inner_text("#refs").lower(), "page says round 2")
    check("Claude answered 3 questions from round 1" in pg.inner_text("#roundnote"), "round-2 banner: Claude answered 3 questions")
    check(sel(pg) == "F3", "opens on the first entry with a new answer (F3)")
    check(pg.locator(".tag.new").count() == 1, "the answer is marked New")
    check(responses(pg)["entries"] == {}, "nothing to send yet: marks now live in the ledger")
    check("10/18 decided" in pg.inner_text("#progress"), "decisions carried over from the ledger")
    check(pg.locator("#opt-F5 .rflags .w").count() == 1, "F5's dependency warning carries into round 2")
    pg.evaluate("document.getElementById('conv').scrollIntoView({block:'start'}); document.getElementById('dscroll').scrollBy(0,-150)")
    shot(pg, "13-round2-answers.png")
    pg.click('#roundnote [data-act="filter"]')
    check(pg.locator(".row").count() == 3, "'Read them' filters to the 3 answered entries")
    key(pg, "j")
    check(pg.locator("#opt-F3 .newdot").count() == 0, "an answer counts as read once its entry is opened")
    pg.click('.chip[data-f="all"]')
    pg.click("#opt-F7"); key(pg, "1", "b"); pg.keyboard.type("lanes"); pg.click('.mb2[data-m="rework"]')
    check(responses(pg)["entries"]["F7"] == {"title": "Per-queue concurrency limits", "status": "open", "mode": "rework", "batch": "lanes"},
          "typing a batch name and then clicking a mode keeps both")
    key(pg, "u", "u", "u")
    check("F7" not in responses(pg)["entries"], "undo walks back the mode, the batch name and the first mark")
    pg.click("#opt-F3"); key(pg, "c"); pg.keyboard.type("So F4 and F5 hard-depend on the file being on?"); key(pg, "Control+Enter")
    check(responses(pg)["entries"]["F3"]["comments"][0]["id"] == "r2.q1", "a follow-up gets id r2.q1")
    with pg.expect_download() as dl:
        key(pg, "Escape", "s"); pg.click('.dialog [data-act="export"]')
    dl.value.save_as(OUT / "responses-r2.json")
    check(sh("check", str(OUT / "responses-r2.json"), str(OUT / "ledger-r1.md")).returncode == 0, "round-2 file checks clean against the ingested ledger")
    check(sh("check", str(OUT / "responses-r1.json"), str(OUT / "ledger-r1.md")).returncode == 1, "the spent round-1 file is reported stale")
    pg.close()

    # ------------------------------------------------------------------ scale: 40 features
    print("scale")
    random.seed(7)
    words = "queue retry cache schema export audit token batch worker index stream backoff lease shard quota snapshot".split()
    head = (ROOT / "fixture/origin-main.md").read_text().split("### F1.")[0]
    body = []
    for i in range(1, 41):
        deps = sorted(random.sample(range(1, i), k=min(i - 1, random.choice([0, 0, 1, 1, 2, 3])))) if i > 1 else []
        fit = random.choice(["aligned", "aligned", "tension", "conflict"])
        body.append(f"### F{i}. {random.choice(words).title()} {random.choice(words)} {random.choice(words)} support\n\n"
                    f"Synthetic entry {i} for a scale test.\nWhy: unstated.\n\n- Size: +{random.randint(10, 900)} / -{random.randint(0, 120)} across {random.randint(1, 12)} files\n"
                    f"- Commits: {random.getrandbits(28):07x}\n- Files: 1 (0 shared). Source: src/x{i}.py\n"
                    f"- Depends on: {', '.join('F%d' % d for d in deps) or 'none'}\n- Fit: {fit}. Synthetic.\n- Status: open\n")
    (OUT / "scale.md").write_text(head + "\n".join(body))
    assert sh("render", str(OUT / "scale.md"), "--template", TPL, "-o", str(OUT / "scale.html")).returncode == 0
    pg = b.new_page(viewport=VIEW, color_scheme="dark"); pg.on("pageerror", lambda e: errs.append(str(e)))
    t0 = time.perf_counter(); pg.goto((OUT / "scale.html").as_uri()); load = time.perf_counter() - t0
    t0 = time.perf_counter()
    for _ in range(20):
        key(pg, random.choice("123x"), "j")
    per = (time.perf_counter() - t0) / 20
    check(pg.locator(".row").count() == 40, f"40 entries; load {load:.2f}s, {per * 1000:.0f} ms per mark-and-move (incl. Playwright round-trips)")
    key(pg, "m"); pg.mouse.move(5, 5); shot(pg, "14-scale-map.png")
    b.close()

check(not errs, "no page errors: %s" % errs)

# example pages and the responses they produced, kept in the repo for review
EX = V2 / "example"; EX.mkdir(exist_ok=True)
for src, dst in (("report.html", "report-r1.html"), ("report-r2.html", "report-r2.html"),
                 ("responses-r1.json", "responses-r1.json"), ("responses-r2.json", "responses-r2.json")):
    shutil.copy(OUT / src, EX / dst)
print("v2 ok")
