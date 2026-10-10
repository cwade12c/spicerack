"""The harvest review page end to end with Playwright: round 1 by keyboard, protocol parity with the
round-1 prototype, focus handling, round 2, a cut recorded in the ledger, a phone viewport, and scale.

    python3 tests/harvest/test_report_page.py                     # Chromium
    python3 tests/harvest/test_report_page.py --browser firefox
    uv run --no-project --with playwright python tests/harvest/test_report_page.py --browser all   # Chromium, Firefox

Needs python3 playwright and its browsers (`playwright install chromium firefox`). Writes
tests/harvest/out/<browser>/ (git-ignored): the rendered pages, the exported responses files, and
screenshots to look at.
"""
import argparse
import json
import pathlib
import random
import shutil
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
REPORT = REPO / "skills/harvest/scripts/report.py"
FIX = HERE / "fixtures"
LEDGER = FIX / "origin-main.md"
VIEW = {"width": 1440, "height": 900}


def sh(*a):
    r = subprocess.run([sys.executable, str(REPORT), *a], capture_output=True, text=True)
    print("  $ report.py", a[0], "->", (r.stdout.strip() or r.stderr.strip()).splitlines()[-1:])
    return r


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ok ", msg)


def key(page, *keys):
    for k in keys:
        page.keyboard.press(k)


def sel(page):
    return page.evaluate("document.querySelector('.row.sel') && document.querySelector('.row.sel').dataset.id")


def responses(page):
    return page.evaluate("JSON.parse(JSON.stringify(window.__harvest.buildResponses()))")


def active(page, selector):
    """True when the focused element matches selector."""
    return page.evaluate("s => !!document.activeElement && document.activeElement.matches(s)", selector)


def ask(page, eid, text, note=False):
    page.click(f"#opt-{eid}")
    key(page, "c")
    page.keyboard.type(text)
    key(page, "Shift+Control+Enter" if note else "Control+Enter")
    page.keyboard.press("Escape")


def strip_times(r):
    r = json.loads(json.dumps(r))
    r.pop("created", None)
    for e in r["entries"].values():
        for c in e.get("comments", []):
            c.pop("created", None)
    return r


def run(p, name):
    print(f"[{name}]")
    out = HERE / "out" / name
    shutil.rmtree(out, ignore_errors=True)
    shots = out / "shots"
    shots.mkdir(parents=True)
    bt = getattr(p, name)
    chromium = name == "chromium"
    errs = []

    def watch(page):
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errs.append(m.text))

    def shot(page, file):
        page.evaluate("document.getElementById('toastbox').innerHTML = ''")
        page.wait_for_timeout(350)
        page.screenshot(path=str(shots / file))

    # ------------------------------------------------------------------ render defaults
    print("render")
    shutil.copy(LEDGER, out / "origin-main.md")
    r = sh("render", str(out / "origin-main.md"))
    check(r.returncode == 0 and (out / "origin-main.report-r1.html").exists(),
          "with no -o or --template: the template comes from assets/, the page lands beside the ledger as <head>.report-r1.html")
    check("0 parse warnings" in r.stdout, "the fixture ledger parses without warnings")
    page_r1 = out / "origin-main.report-r1.html"
    url = page_r1.as_uri()

    # ------------------------------------------------------------------ round 1
    print("round 1")
    ctx_opts = dict(headless=True, viewport=VIEW, color_scheme="dark", accept_downloads=True)
    if chromium:
        ctx_opts["permissions"] = ["clipboard-read", "clipboard-write"]
    mk = lambda: bt.launch_persistent_context(str(out / "profile"), **ctx_opts)
    ctx = mk()
    page = ctx.new_page()
    watch(page)
    page.goto(url)
    ids = page.eval_on_selector_all(".row", "r => r.map(x => x.dataset.id)")
    check(len(ids) == 21, "21 entries listed")
    check(ids[-4:] == ["Plumbing", "Head-only", "S1", "S2"], "Plumbing, Head-only and set-aside items come last")
    pos = {i: n for n, i in enumerate(ids)}
    check(all(all(pos[d] < pos[e] for d in deps) for e, deps in
              {"F4": ["F3", "F1"], "F5": ["F4", "F3"], "F12": ["F11", "F10"], "F17": ["F3", "F2", "F7"]}.items()),
          "every dependency is listed before the entries that build on it")
    check(sel(page) == "F2", "opens on the first undecided entry (F2)")
    check("Finish round" in page.inner_text("#sendbtn") and "Claude" not in page.content(),
          "the page names no particular agent; the hand-back button says what it does")
    check("2/18 decided" in page.inner_text("#progress"), "progress starts from the ledger: 2/18 decided (F8 picked, F14 left)")

    t0 = time.perf_counter()
    key(page, "1", "b"); page.keyboard.type("config"); key(page, "Enter")          # F2 cherry-pick, batch config
    key(page, "j", "2", "b"); page.keyboard.type("storage"); key(page, "Enter")    # F3 rework, storage
    key(page, "j", "x")                                                            # F4 left
    key(page, "j", "3")                                                            # F5 rebuild -> needs F4
    key(page, "j", "2", "b"); page.keyboard.type("storage"); key(page, "Enter")    # F6 rework, storage
    page.click("#opt-F9"); key(page, "1")                                          # F9 cherry-pick (F1 landed: fine)
    page.click("#opt-F12"); key(page, "x")                                         # F12 left
    page.click("#opt-F10"); key(page, "2")                                         # F10 rework (F9 picked: fine)
    print(f"  8 decisions by keyboard in {time.perf_counter() - t0:.2f}s")
    check(page.locator("#opt-F5 .rflags .w").count() == 1, "F5 is flagged: it needs F4, which is left")
    check(page.locator("#opt-F9 .rflags .w").count() == 0, "F9 is not flagged: its dependency F1 is landed")
    check("10/18 decided" in page.inner_text("#progress"), "progress reads 10/18 decided")
    check(page.locator(".chip.attn").count() == 1 and "1" in page.inner_text(".chip.attn"), "a 'Needs attention 1' filter appears")

    page.click("#opt-F12"); key(page, "1")
    check(responses(page)["entries"]["F12"]["mode"] == "cherry-pick", "F12 re-marked cherry-pick")
    key(page, "u")
    check(responses(page)["entries"]["F12"]["mode"] == "left", "U undoes it: F12 back to left")

    page.click("#opt-F4")
    check("Picked F5 depends on this entry" in page.inner_text("#dscroll"), "F4 explains that picked F5 depends on it")
    page.click("#opt-F5")
    check("F5 needs F4, which is left" in page.inner_text("#dscroll"), "F5 offers ways to resolve the missing dependency")

    ask(page, "F3", "ADR-002 says job state is in memory. Is the SQLite file optional, or always on?")
    ask(page, "F5", "Does the dead-letter table share the job table's retention policy?")
    ask(page, "F5", "If F4 stays left, can F5 still land with a manual retry hook?", note=True)
    ask(page, "F10", "Which prometheus-client version, and is it vendored?")
    r = responses(page)
    check([c["id"] for c in r["entries"]["F5"]["comments"]] == ["r1.q2", "r1.q3"] and r["entries"]["F5"]["comments"][1]["kind"] == "note",
          "comment ids are r1.q<n> in order; Shift+Ctrl+Enter makes a note")

    page.click("#opt-F5")
    shot(page, "01-review.png")
    key(page, "p")
    page.fill("#general", "Land storage before anything that reads the job table. Skip multi-tenancy for now.")
    page.click(".planhead h2")
    check(page.locator(".bstep").count() == 6, "plan shows 6 branches (config, storage, F5, F8, F9, F10)")
    check("harvest/storage" in page.inner_text("#plan") and "branches off harvest/config" in page.inner_text("#plan"),
          "storage lands after config (F3 needs F2)")
    shot(page, "03-plan.png")
    key(page, "m")
    page.evaluate("window.__harvest.select('F5')")
    check(page.locator(".edge.bad").count() == 1, "the map draws exactly one unresolved edge (F4 -> F5)")
    page.mouse.move(5, 5)
    shot(page, "02-map.png")
    key(page, "r")

    before = responses(page)
    page.reload()
    check(strip_times(responses(page)) == strip_times(before), "state survives a reload")
    ctx.close()
    ctx = mk()
    page = ctx.new_page()
    watch(page)
    page.goto(url)
    check(strip_times(responses(page)) == strip_times(before), "state survives a browser restart")

    # hand-off: send dialog -> copy, and the download path
    page.evaluate("""() => { const w = navigator.clipboard && navigator.clipboard.writeText.bind(navigator.clipboard);
        if (w) navigator.clipboard.writeText = t => { window.__copied = t; return w(t); }; }""")
    key(page, "s")
    check(page.locator(".dialog .callout.w").count() == 1, "send dialog warns about the one unresolved dependency")
    page.click(".bigsend")
    page.wait_for_selector(".bigsend.done")
    clip = page.evaluate("window.__copied")
    if chromium:
        check(page.evaluate("navigator.clipboard.readText()") == clip, "the system clipboard holds the copied text")
    check(clip.startswith("Harvest responses, round 1 (origin-main.md): 7 picked, 3 left, 3 questions, 1 dependency to cut."),
          "copied text starts with a one-line summary the agent can read")
    copied = json.loads(clip.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    shot(page, "04-send.png")
    with page.expect_download() as dl:
        page.click('.dialog [data-act="export"]')
    check(dl.value.suggested_filename == "responses-r1.json", "download is named responses-r1.json")
    dl.value.save_as(out / "responses-r1.json")
    exported = json.load(open(out / "responses-r1.json"))
    check(strip_times(exported) == strip_times(copied), "copy and download carry the same responses")

    # protocol parity: the same decisions as the round-1 prototype's test give the same file it exported
    v1 = json.load(open(FIX / "v1-responses-r1.json"))
    check(strip_times(exported) == strip_times(v1), "export equals the pinned round-1 prototype export (timestamps aside): schema unchanged")
    check(sh("check", str(out / "responses-r1.json"), str(LEDGER)).returncode == 0, "report.py check: exit 0")

    # ------------------------------------------------------------------ focus (after parity: these change state, then undo)
    print("focus")
    page.click("#opt-F7")
    page.click('#dock .mb2[data-m="rework"]')
    check(active(page, '#dock .mb2[data-m="rework"][aria-pressed="true"]'), "after a mouse click on a decision, focus is back on that button")
    key(page, "Tab")
    check(active(page, '#dock .mb2[data-m="rebuild"]'), "Tab then moves on to the next decision, so Tab position survives")
    key(page, "u")
    check("F7" not in responses(page)["entries"], "undo clears the clicked decision")
    page.click("#opt-F5")
    page.click('#dscroll [data-act="mode"][data-id="F5"]')        # Un-pick F5: its button goes away with the card
    check(active(page, '#dock .mb2[data-m="rebuild"]'), "when the clicked button is gone, focus lands on the same decision in the dock")
    key(page, "u")
    check(responses(page)["entries"]["F5"]["mode"] == "rebuild", "undo restores F5's pick")
    key(page, "m")
    page.evaluate("window.__harvest.select('F7')")
    page.click('#insp .mb2[data-m="cherry-pick"]')
    check(active(page, '#insp .mb2[data-m="cherry-pick"]'), "on the map, focus returns to the inspector's button")
    key(page, "u", "r")

    for opener, label in (("s", "send dialog"), ("?", "keyboard help")):
        page.click("#opt-F3")
        page.locator("#list").focus()
        key(page, opener)
        check(page.evaluate("document.getElementById('app').inert"), f"{label}: the page behind is inert")
        inside = []
        for _ in range(25):
            key(page, "Tab")
            inside.append(page.evaluate("document.getElementById('layer').contains(document.activeElement)"))
        check(all(inside), f"{label}: Tab cycles inside the dialog (25 presses)")
        first = page.evaluate("""() => { const f = [...document.querySelectorAll('#layer button, #layer [href], #layer input, #layer summary, #layer textarea')]
            .filter(n => !n.disabled && n.getClientRects().length); f[0].focus(); return f.length; }""")
        key(page, "Shift+Tab")
        check(page.evaluate("""() => { const f = [...document.querySelectorAll('#layer button, #layer [href], #layer input, #layer summary, #layer textarea')]
            .filter(n => !n.disabled && n.getClientRects().length); return document.activeElement === f[f.length - 1]; }"""),
              f"{label}: Shift+Tab from the first control wraps to the last ({first} controls)")
        key(page, "Escape")
        check(not page.evaluate("document.getElementById('app').inert") and active(page, "#list"),
              f"{label}: Esc closes it, the page is live again, and focus returns to where it was")
    page.click('[data-act="menu"]')
    for _ in range(3):                                              # each click redraws the menu; auto -> light -> dark -> auto
        page.click('[data-act="theme"]')
    key(page, "Escape")
    check(active(page, '[data-act="menu"]'), "a menu redrawn in place still returns focus to its opener")

    # cut a dependency on the page
    page.click("#opt-F5")
    page.click('[data-act="cutedit"][data-id="F5"]')
    page.keyboard.type("Land with a manual retry hook; F4's backoff can follow later.")
    page.click('[data-act="cutdone"][data-id="F5"]')
    r = responses(page)
    check(r["entries"]["F5"]["cuts"] == [{"dep": "F4", "how": "Land with a manual retry hook; F4's backoff can follow later."}], "the cut is exported as {dep, how}")
    check(page.locator(".chip.attn").count() == 0 and page.locator("#opt-F5 .rflags .w").count() == 0, "a cut clears the warning")
    key(page, "u")
    check("cuts" not in responses(page)["entries"]["F5"], "the cut can be undone")

    page.emulate_media(color_scheme="light")
    page.click("#opt-F3")
    shot(page, "05-review-light.png")
    page.emulate_media(color_scheme="dark")
    ctx.close()

    # ------------------------------------------------------------------ mobile
    print("mobile")
    b = bt.launch(headless=True)
    mopts = dict(viewport={"width": 390, "height": 844}, color_scheme="dark", device_scale_factor=2, has_touch=True)
    if chromium:
        mopts["is_mobile"] = True                                   # Firefox has no mobile emulation
    m = b.new_page(**mopts)
    watch(m)
    m.goto(url)
    # clientWidth, not innerWidth: a mobile browser widens its layout viewport to fit overflow, which hides it.
    check(m.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth && innerWidth === 390"),
          "no horizontal page scroll at 390px")
    m.tap("#opt-F5")
    m.wait_for_timeout(350)
    m.tap('.mb2[data-m="rebuild"]')
    check(responses(m)["entries"]["F5"]["mode"] == "rebuild", "tap to decide works on a phone")
    shot(m, "06-mobile-detail.png")
    m.close()

    # ------------------------------------------------------------------ round 2
    print("round 2")
    shutil.copy(FIX / "origin-main.after-round1.md", out / "ledger-r1.md")
    assert sh("render", str(out / "ledger-r1.md"), "--responses", str(out / "responses-r1.json"), "-o", str(out / "report-r2.html")).returncode == 0
    pg = b.new_page(viewport=VIEW, color_scheme="dark")
    watch(pg)
    pg.goto((out / "report-r2.html").as_uri())
    check("round 2" in pg.inner_text("#refs").lower(), "page says round 2")
    check("3 answers from round 1" in pg.inner_text("#roundnote"), "round-2 banner: 3 answers from round 1")
    check(sel(pg) == "F3", "opens on the first entry with a new answer (F3)")
    check(pg.locator(".tag.new").count() == 1, "the answer is marked New")
    check(responses(pg)["entries"] == {}, "nothing to send yet: marks now live in the ledger")
    check("10/18 decided" in pg.inner_text("#progress"), "decisions carried over from the ledger")
    check(pg.locator("#opt-F5 .rflags .w").count() == 1, "F5's dependency warning carries into round 2")
    shot(pg, "07-round2.png")
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
    dl.value.save_as(out / "responses-r2.json")
    r = sh("check", str(out / "responses-r2.json"), str(out / "ledger-r1.md"))
    check(r.returncode == 0 and "DEPENDENCY F5" in r.stdout, "round-2 file checks clean against the ingested ledger; F5's uncut dependency is advisory")
    check(sh("check", str(out / "responses-r1.json"), str(out / "ledger-r1.md")).returncode == 1, "the spent round-1 file is reported stale")
    pg.close()

    # ------------------------------------------------------------------ a cut recorded in the ledger
    print("ledger cut")
    led = (out / "ledger-r1.md").read_text()
    dep = "- Depends on: F4 (hooks the retry-exhausted event), F3 (dead letters are rows in the job table)"
    check(dep in led, "fixture has F5's Depends on line")
    (out / "ledger-cut.md").write_text(led.replace(dep, dep + "; cut F4: land with a manual retry hook (r1.q3)"))
    r = sh("render", str(out / "ledger-cut.md"), "-o", str(out / "report-cut.html"))
    check("0 parse warnings" in r.stdout, "a `cut F4:` clause parses without warnings")
    pg = b.new_page(viewport=VIEW, color_scheme="dark")
    watch(pg)
    pg.goto((out / "report-cut.html").as_uri())
    check(pg.locator("#opt-F5 .rflags .w").count() == 0 and pg.locator(".chip.attn").count() == 0,
          "a cut in the ledger resolves F5's warning on the page")
    pg.click("#opt-F5")
    check("From the ledger" in pg.inner_text("#dscroll") and "manual retry hook" in pg.inner_text("#dscroll"),
          "the entry shows the ledger's cut, marked as from the ledger")
    check("cuts" not in responses(pg)["entries"].get("F5", {}), "a ledger cut is not sent back as a new cut")
    shot(pg, "08-ledger-cut.png")
    r = sh("check", str(out / "responses-r2.json"), str(out / "ledger-cut.md"))
    check("DEPENDENCY" not in r.stdout, "check honours the ledger's cut too")

    ledger_how, new_how = "land with a manual retry hook (r1.q3)", "bring over F4's _retry_delay only"

    def edit_cut(text, seeded=None):
        pg.click('[data-act="cutedit"][data-id="F5"]')
        if seeded is not None:
            check(pg.input_value('[data-k="cut:F5:F4"]') == seeded, "Edit opens with the ledger's text")
        pg.fill('[data-k="cut:F5:F4"]', text)
        pg.click('[data-act="cutdone"][data-id="F5"]')

    edit_cut(new_how, seeded=ledger_how)
    check(responses(pg)["entries"]["F5"].get("cuts") == [{"dep": "F4", "how": new_how}], "an edited ledger cut is sent as the new {dep, how}")
    check(f"Was “{ledger_how}” in the ledger" in pg.inner_text("#dscroll") and pg.locator('[data-act="cutrevert"]').count() == 1,
          "the edited cut shows the ledger's text and an Undo edit button")
    shot(pg, "09-ledger-cut-edited.png")
    (out / "responses-cut-edit.json").write_text(json.dumps(responses(pg)))
    r = sh("check", str(out / "responses-cut-edit.json"), str(out / "ledger-cut.md"))
    check(r.returncode == 0 and "DEPENDENCY" not in r.stdout and "STALE CUT" not in r.stdout, "check accepts the edited cut")
    pg.click('[data-act="cutrevert"]')
    check("F5" not in responses(pg)["entries"] and "From the ledger" in pg.inner_text("#dscroll"), "Undo edit restores the ledger's cut")
    edit_cut(new_how)
    key(pg, "u")
    check("F5" not in responses(pg)["entries"], "U undoes an edit")
    edit_cut(new_how)
    key(pg, "Control+z")
    check("F5" not in responses(pg)["entries"], "Ctrl+Z undoes an edit")
    edit_cut(ledger_how)
    check("F5" not in responses(pg)["entries"], "editing a cut back to the ledger's text sends nothing")
    pg.close()

    # ------------------------------------------------------------------ scale: 40 features
    print("scale")
    random.seed(7)
    words = "queue retry cache schema export audit token batch worker index stream backoff lease shard quota snapshot".split()
    head = LEDGER.read_text().split("### F1.")[0]
    body = []
    for i in range(1, 41):
        deps = sorted(random.sample(range(1, i), k=min(i - 1, random.choice([0, 0, 1, 1, 2, 3])))) if i > 1 else []
        fit = random.choice(["aligned", "aligned", "tension", "conflict"])
        body.append(f"### F{i}. {random.choice(words).title()} {random.choice(words)} {random.choice(words)} support\n\n"
                    f"Synthetic entry {i} for a scale test.\nWhy: unstated.\n\n- Size: +{random.randint(10, 900)} / -{random.randint(0, 120)} across {random.randint(1, 12)} files\n"
                    f"- Commits: {random.getrandbits(28):07x}\n- Files: 1 (0 shared). Source: src/x{i}.py\n"
                    f"- Depends on: {', '.join('F%d' % d for d in deps) or 'none'}\n- Fit: {fit}. Synthetic.\n- Status: open\n")
    (out / "scale.md").write_text(head + "\n".join(body))
    assert sh("render", str(out / "scale.md"), "-o", str(out / "scale.html")).returncode == 0
    pg = b.new_page(viewport=VIEW, color_scheme="dark")
    watch(pg)
    t0 = time.perf_counter(); pg.goto((out / "scale.html").as_uri()); load = time.perf_counter() - t0
    t0 = time.perf_counter()
    for _ in range(20):
        key(pg, random.choice("123x"), "j")
    per = (time.perf_counter() - t0) / 20
    check(pg.locator(".row").count() == 40, f"40 entries; load {load:.2f}s, {per * 1000:.0f} ms per mark-and-move (incl. Playwright round-trips)")
    b.close()

    check(not errs, "no page errors: %s" % errs)
    print(f"[{name}] ok; screenshots in {shots.relative_to(REPO)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--browser", choices=("chromium", "firefox", "webkit", "all"), default="chromium")
    a = ap.parse_args()
    names = ("chromium", "firefox") if a.browser == "all" else (a.browser,)
    with sync_playwright() as p:
        for n in names:
            run(p, n)


if __name__ == "__main__":
    main()
