#!/usr/bin/env python3
"""Render a harvest ledger as the batched review page, and check a responses file against
the ledger. Standard library only. See references/REPORT.md.

    python3 scripts/report.py render <ledger> [--responses <prev.json>] [-o <page.html>] [--template <t.html>] [--strict]
    python3 scripts/report.py check  <responses.json> <ledger>

render
    Parses the ledger, embeds it as JSON in assets/report-template.html, and writes one
    self-contained page, by default <head>.report-r<round>.html beside the ledger. The round
    is one more than the ledger's `Report: round N ingested` header line (1 if absent).
    --responses is the previous round's responses file: the page then shows its questions
    that the ledger has no answer for yet. Prints every parse warning; --strict exits 1
    when there are any.

check
    Validates a harvest-responses/1 file and compares it with the current ledger. Prints
    one line per finding: STALE, GAP, HEAD CHANGED, LEDGER CHANGED, MISSING ENTRY,
    TITLE CHANGED, STATUS CHANGED, LANDED, DEPENDENCY, or the SCHEMA problems.
    Exit 0: safe to ingest (LEDGER CHANGED and DEPENDENCY lines are advisory).
    Exit 1: resolve every line before applying anything.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

ID_RE = r"(?:F\d+|S\d+|Plumbing|Head-only)"
HEADING_RE = re.compile(r"^###\s+(%s)(?:[.:]|\s[-—])?\s*(.*?)\s*$" % ID_RE)
BULLET_RE = re.compile(r"^-\s+([A-Za-z][A-Za-z ]*?):\s*(.*)$")
NOTE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(Q|Note)(?:\s+\((r\d+)(?:\.(q\d+))?\))?:\s*(.*)$", re.S)
MODES = ("cherry-pick", "rework", "rebuild")
BULLETS = ("Size", "Commits", "Files", "Depends on", "Fit", "Status")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- parsing

def parse_header(lines, warns):
    h = {}
    for ln in lines:
        m = re.match(r"^[-*]?\s*\**([A-Za-z][A-Za-z -]*?)\**:\s*(.*)$", ln)
        if m:
            h[m.group(1).strip().lower()] = m.group(2).strip()
    out = {"raw": h}
    for key in ("base", "head"):
        v = h.get(key, "").replace("`", "")
        m = re.match(r"^(.*?)\s*(?:@|\()\s*([0-9a-f]{7,40})\)?\s*$", v)
        if m:
            out[key], out[key + "_sha"] = m.group(1).strip(), m.group(2)
        else:
            out[key], out[key + "_sha"] = v, ""
            warns.append("header: could not read a SHA from '%s: %s'" % (key.title(), v))
    out["merge_base"] = h.get("merge-base", "").replace("`", "")
    out["updated"] = h.get("updated", "")
    m = re.search(r"round\s+(\d+)", h.get("report", ""))
    out["ingested_round"] = int(m.group(1)) if m else 0
    for k in ("base", "head", "merge_base", "updated"):
        if not out[k]:
            warns.append("header: missing '%s'" % k)
    return out


def parse_status(raw, eid, warns):
    s = raw.strip().rstrip(".")
    if s == "open":
        return {"kind": "open"}
    if s == "left":
        return {"kind": "left"}
    m = re.match(r"^picked:\s*(cherry-pick|rework|rebuild)(?:,\s*batch:\s*(.+))?$", s)
    if m:
        return {"kind": "picked", "mode": m.group(1), "batch": (m.group(2) or "").strip() or None}
    m = re.match(r"^landed:\s*(.+)$", s)
    if m:
        br = m.group(1).strip()
        return {"kind": "landed", "branch": br, "on_base": br == "already on base"}
    warns.append("%s: unrecognised status '%s' (treated as open)" % (eid, raw))
    return {"kind": "open"}


def parse_notes(sub, eid):
    """Notes sub-bullets -> dated items. Continuation lines join the previous item."""
    items = []
    for ln in sub:
        m = re.match(r"^\s+-\s+(.*)$", ln)
        if m:
            items.append(m.group(1).strip())
        elif ln.strip() and items:
            items[-1] += " " + ln.strip()
    out = []
    for it in items:
        m = NOTE_RE.match(it)
        if not m:
            out.append({"kind": "plain", "text": it})
            continue
        date, kind, rnd, qid, rest = m.groups()
        item = {"date": date, "kind": "question" if kind == "Q" else "note",
                "round": int(rnd[1:]) if rnd else None,
                "qid": ("%s.%s" % (rnd, qid) if rnd and qid else None)}
        if kind == "Q" and " A: " in rest:
            q, a = rest.split(" A: ", 1)
            item["text"], item["answer"] = q.strip(), a.strip()
        else:
            item["text"] = rest.strip()
        out.append(item)
    return out


def parse_depends(raw, eid, warns):
    """`Depends on:` -> (ids, cuts). Ids come from the text before the first `;`, outside
    parentheses, so prose and reasons can mention other entries. A range `F2-F4` is expanded,
    with a warning. After the `;`, each `cut F4: <how>` records a dependency the human cut."""
    ids_part, _, rest = raw.partition(";")
    ids_part = re.sub(r"\([^()]*\)", "", ids_part)

    def expand(m):
        a, b = int(m.group(1)), int(m.group(2))
        warns.append("%s: Depends on names the range F%d-F%d; name each id" % (eid, a, b))
        return ", ".join("F%d" % i for i in range(a, b + 1))
    ids_part = re.sub(r"\bF(\d+)\s*[-–]\s*F(\d+)\b", expand, ids_part)
    deps = []
    for d in re.findall(r"\b%s\b" % ID_RE, ids_part):
        if d != eid and d not in deps:
            deps.append(d)
    cuts = {}
    for m in re.finditer(r"(?:^|;)\s*cut\b\s*(%s)?\s*:\s*(.*?)\s*(?=;\s*cut\b|$)" % ID_RE, rest, re.S):
        if not m.group(1):
            warns.append("%s: a cut must name the dependency it cuts, as 'cut F4: <how>': %r" % (eid, m.group(2)[:40]))
        elif m.group(1) not in deps:
            warns.append("%s: cuts %s, which is not in its Depends on ids" % (eid, m.group(1)))
        elif m.group(2):
            cuts[m.group(1)] = m.group(2)
    return deps, cuts


def parse_entry(block, warns):
    head = HEADING_RE.match(block[0])
    eid, title = head.group(1), head.group(2)
    desc, why = [], ""
    bullets, sub = {}, {}
    cur = None
    for ln in block[1:]:
        if not ln.strip():
            continue
        m = BULLET_RE.match(ln)
        if m:
            cur = m.group(1).strip()
            bullets[cur] = m.group(2).strip()
            sub[cur] = []
            continue
        if cur is not None:
            if ln[:1] in (" ", "\t"):
                sub[cur].append(ln)
                if not re.match(r"^\s+-\s", ln):
                    bullets[cur] += " " + ln.strip()
            else:
                warns.append("%s: stray line after bullets: %r" % (eid, ln[:50]))
            continue
        if ln.startswith("Why:"):
            why = ln[4:].strip()
        elif why:
            why += " " + ln.strip()
        else:
            desc.append(ln.strip())
    for b in BULLETS:
        if b not in bullets:
            warns.append("%s: missing bullet '%s'" % (eid, b))
    if not why:
        warns.append("%s: missing 'Why:' line" % eid)
    status = parse_status(bullets.get("Status", "open"), eid, warns)
    dep_raw = bullets.get("Depends on", "none")
    deps, cuts = parse_depends(dep_raw, eid, warns)
    fit_raw = bullets.get("Fit", "")
    fm = re.match(r"^(aligned|tension|conflict)\b", fit_raw)
    if not fm:
        warns.append("%s: Fit does not start with aligned/tension/conflict: '%s'" % (eid, fit_raw[:40]))
    if eid == "Plumbing":
        kind = "plumbing"
    elif eid == "Head-only":
        kind = "headonly"
    elif status["kind"] == "landed" and status.get("on_base"):
        kind = "setaside"
    else:
        kind = "feature"
    return {
        "id": eid, "title": title, "kind": kind,
        "description": " ".join(desc), "why": why,
        "size": bullets.get("Size", ""), "commits": bullets.get("Commits", ""),
        "files": bullets.get("Files", ""), "depends_raw": dep_raw, "depends": deps, "cuts": cuts,
        "fit_raw": fit_raw, "fit": fm.group(1) if fm else "?",
        "status_raw": bullets.get("Status", ""), "status": status,
        "notes": parse_notes(sub.get("Notes", []), eid),
        "notes_inline": bullets.get("Notes", "") if not sub.get("Notes") else "",
        "raw": "\n".join(block).rstrip(),
    }


def parse_ledger(text):
    warns = []
    lines = text.splitlines()
    idx = [i for i, ln in enumerate(lines) if ln.startswith("### ")]
    header = parse_header(lines[: idx[0]] if idx else lines, warns)
    m = re.match(r"^#\s+(.*)$", lines[0]) if lines else None
    header["title"] = m.group(1) if m else ""
    set_aside_lines = [ln for ln in lines[: idx[0]] if idx and "already on base" in ln and ln.lstrip().startswith(("-", "*"))]
    if set_aside_lines:
        warns.append("header: %d set-aside item(s) listed outside '### S<n>.' entries; the page does not show them"
                     % len(set_aside_lines))
    entries = []
    for n, i in enumerate(idx):
        j = idx[n + 1] if n + 1 < len(idx) else len(lines)
        # An entry also ends at a higher-level heading, so a trailing section is not read as its body.
        j = next((k for k in range(i + 1, j) if re.match(r"^#{1,2}\s", lines[k])), j)
        if not HEADING_RE.match(lines[i]):
            warns.append("heading without a recognised id (F<n>/S<n>/Plumbing/Head-only): %r" % lines[i][:60])
            continue
        e = parse_entry(lines[i:j], warns)
        if not e["title"]:
            warns.append("%s: heading has no title; write '### %s. <title>'" % (e["id"], e["id"]))
        entries.append(e)
    ids = [e["id"] for e in entries]
    for d in {x for x in ids if ids.count(x) > 1}:
        warns.append("duplicate entry id %s" % d)
    for e in entries:
        for d in e["depends"]:
            if d not in ids:
                warns.append("%s: depends on %s, which is not in the ledger" % (e["id"], d))
        e["depends"] = [d for d in e["depends"] if d in ids]
        e["cuts"] = {d: how for d, how in e["cuts"].items() if d in ids}
    return header, order_entries(entries), warns


def order_entries(entries):
    """Dependency order for features (ties by id number); Plumbing, Head-only, set-aside last."""
    def num(e):
        m = re.search(r"\d+", e["id"])
        return int(m.group()) if m else 10 ** 6

    feats = sorted([e for e in entries if e["kind"] == "feature"], key=num)
    placed, out, left = set(), [], list(feats)
    ids = {e["id"] for e in feats}
    while left:
        ready = [e for e in left if all(d in placed or d not in ids for d in e["depends"])]
        if not ready:  # cycle: emit the rest in id order and say nothing here; page shows deps
            ready = [left[0]]
        e = ready[0]
        out.append(e)
        placed.add(e["id"])
        left.remove(e)
    for k in ("plumbing", "headonly", "setaside"):
        out += [e for e in entries if e["kind"] == k]
    for i, e in enumerate(out):
        e["order"] = i
    return out


# ---------------------------------------------------------------- render

def default_out(ledger, round_):
    """<head>.report-r<round>.html beside the ledger <head>.md."""
    stem = os.path.basename(ledger)
    if stem.endswith(".md"):
        stem = stem[:-3]
    return os.path.join(os.path.dirname(os.path.abspath(ledger)), "%s.report-r%d.html" % (stem, round_))


def cmd_render(a):
    text = open(a.ledger, encoding="utf-8").read()
    header, entries, warns = parse_ledger(text)
    prev = None
    if a.responses:
        prev = json.load(open(a.responses, encoding="utf-8"))
        problems = validate_responses(prev)
        if problems:
            warns += ["previous responses: " + p for p in problems]
    ingested = header["ingested_round"]
    round_ = ingested + 1
    pending = {}
    if prev:
        pr = prev.get("round", 0)
        if pr > ingested:
            warns.append("responses round %d has not been ingested into the ledger "
                         "(ledger says round %d); its questions are shown as pending" % (pr, ingested))
            round_ = pr + 1
        known = {n.get("qid") for e in entries for n in e["notes"] if n.get("qid")}
        for eid, er in (prev.get("entries") or {}).items():
            for c in er.get("comments", []):
                if c.get("kind") == "question" and c.get("id") not in known:
                    pending.setdefault(eid, []).append(
                        {"id": c.get("id"), "text": c.get("text", ""), "answer": c.get("answer"),
                         "round": prev.get("round")})
    data = {
        "meta": {
            "title": header["title"], "base": header["base"], "base_sha": header["base_sha"],
            "head": header["head"], "head_sha": header["head_sha"],
            "merge_base": header["merge_base"], "updated": header["updated"],
            "header": header["raw"], "ledger_name": os.path.basename(a.ledger),
            "ledger_sha256": sha256(text), "round": round_, "ingested_round": ingested,
            "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "parse_warnings": warns,
        },
        "pending": pending,
        "entries": entries,
    }
    here = os.path.dirname(os.path.abspath(__file__))
    tpl = open(a.template or os.path.join(here, os.pardir, "assets", "report-template.html"),
               encoding="utf-8").read()
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028")
    if "__HARVEST_DATA__" not in tpl:
        sys.exit("template has no __HARVEST_DATA__ placeholder")
    out = a.out or default_out(a.ledger, round_)
    open(out, "w", encoding="utf-8").write(tpl.replace("__HARVEST_DATA__", payload))
    for w in warns:
        print("warning:", w, file=sys.stderr)
    print("wrote %s (%d entries, round %d, %d parse warnings)" % (out, len(entries), round_, len(warns)))
    return 1 if (a.strict and warns) else 0


# ---------------------------------------------------------------- responses

def validate_responses(r):
    """Hand-rolled check of the harvest-responses/1 schema (references/REPORT.md). Returns a list of problems."""
    p = []

    def need(cond, msg):
        if not cond:
            p.append(msg)

    if not isinstance(r, dict):
        return ["top level must be an object"]
    need(r.get("schema") == "harvest-responses/1", "schema must be 'harvest-responses/1'")
    need(isinstance(r.get("round"), int) and r["round"] >= 1, "round must be an integer >= 1")
    need(isinstance(r.get("created"), str), "created must be an ISO timestamp string")
    led = r.get("ledger")
    if not isinstance(led, dict):
        p.append("ledger must be an object")
    else:
        need(re.fullmatch(r"[0-9a-f]{64}", str(led.get("sha256", ""))), "ledger.sha256 must be 64 hex chars")
        for k in ("name", "head", "head_sha", "base", "base_sha", "updated"):
            need(isinstance(led.get(k), str), "ledger.%s must be a string" % k)
    need(isinstance(r.get("general_notes", ""), str), "general_notes must be a string")
    ents = r.get("entries")
    if not isinstance(ents, dict):
        p.append("entries must be an object keyed by entry id")
        return p
    for eid, e in ents.items():
        w = "entries.%s" % eid
        need(re.fullmatch(ID_RE, eid) is not None, "%s: key is not an entry id" % w)
        if not isinstance(e, dict):
            p.append(w + " must be an object")
            continue
        need(isinstance(e.get("title"), str), w + ".title must be a string (as rendered)")
        need(isinstance(e.get("status"), str), w + ".status must be a string (as rendered)")
        if "mode" in e:
            need(e["mode"] in MODES + ("left", "open"), w + ".mode must be cherry-pick|rework|rebuild|left|open")
        if e.get("batch") is not None:
            need(isinstance(e["batch"], str) and e["batch"].strip() != "", w + ".batch must be a non-empty string or null")
            need(e.get("mode") in MODES, w + ".batch only makes sense with a pick mode")
        for c in e.get("cuts", []):
            need(isinstance(c, dict) and re.fullmatch(ID_RE, str(c.get("dep", ""))) is not None
                 and isinstance(c.get("how"), str) and c["how"].strip() != "", w + ".cuts needs {dep, how}")
        seen = set()
        for c in e.get("comments", []):
            ok = isinstance(c, dict) and c.get("kind") in ("question", "note") \
                and isinstance(c.get("text"), str) and c["text"].strip() != "" \
                and re.fullmatch(r"r\d+\.q\d+", str(c.get("id", ""))) is not None
            need(ok, w + ".comments: each needs id 'r<round>.q<n>', kind question|note, non-empty text")
            if ok:
                need(c["id"] not in seen, w + ".comments: duplicate id " + c["id"])
                seen.add(c["id"])
                if isinstance(r.get("round"), int):
                    need(c["id"].startswith("r%d." % r["round"]), w + ".comments: id %s is not from round %d" % (c["id"], r["round"]))
    return p


def cmd_check(a):
    r = json.load(open(a.responses, encoding="utf-8"))
    text = open(a.ledger, encoding="utf-8").read()
    header, entries, _ = parse_ledger(text)
    by = {e["id"]: e for e in entries}
    problems = validate_responses(r)
    notes = []
    if problems:
        print("SCHEMA")
        for x in problems:
            print("  " + x)
    ing = header["ingested_round"]
    rr = r.get("round", 0)
    if rr <= ing:
        notes.append("STALE: responses round %d but the ledger already records round %d ingested" % (rr, ing))
    elif rr > ing + 1:
        notes.append("GAP: responses round %d but the ledger records round %d ingested; an earlier round is missing" % (rr, ing))
    led = r.get("ledger", {})
    if led.get("head_sha") and led["head_sha"] != header["head_sha"]:
        notes.append("HEAD CHANGED: page was rendered at head %s, ledger is now at %s (resume ran)" % (led["head_sha"], header["head_sha"]))
    if led.get("sha256") and led["sha256"] != sha256(text):
        notes.append("LEDGER CHANGED since render (sha256 differs); entries are compared one by one below")
    for eid, e in (r.get("entries") or {}).items():
        cur = by.get(eid)
        if not cur:
            notes.append("MISSING ENTRY %s: not in the ledger any more (split, merged or dropped); do not apply" % eid)
        elif cur["title"] != e.get("title"):
            notes.append("TITLE CHANGED %s: rendered '%s', now '%s'; confirm it is the same feature" % (eid, e.get("title"), cur["title"]))
        elif cur["status_raw"].strip() != str(e.get("status", "")).strip():
            notes.append("STATUS CHANGED %s: rendered '%s', ledger now '%s'; the mark may be out of date" % (eid, e.get("status"), cur["status_raw"].strip()))
        if cur and e.get("mode") in MODES and cur["status"]["kind"] == "landed":
            notes.append("LANDED %s: marked %s but already %s" % (eid, e["mode"], cur["status_raw"].strip()))

    # dependency check on the state the file would produce
    def eff(e):
        cur = by[e]["status"]
        m = (r.get("entries") or {}).get(e, {}).get("mode")
        if cur["kind"] == "landed" or m is None:
            return "picked" if cur["kind"] == "picked" else cur["kind"]
        return "picked" if m in MODES else m
    for e in entries:
        if eff(e["id"]) != "picked":
            continue
        cuts = set(e["cuts"]) | {c.get("dep") for c in (r.get("entries") or {}).get(e["id"], {}).get("cuts", [])}
        for d in e["depends"]:
            if eff(d) not in ("picked", "landed") and d not in cuts:
                notes.append("DEPENDENCY %s is picked but needs %s (%s) and no cut was given" % (e["id"], d, eff(d)))
    for x in notes:
        print(x)
    if not problems and not notes:
        print("OK: responses round %d matches the ledger" % rr)
    return 1 if (problems or any(not n.startswith(("LEDGER CHANGED", "DEPENDENCY")) for n in notes)) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("render", help="write the review page for a ledger")
    r.add_argument("ledger")
    r.add_argument("--responses", help="the previous round's responses file")
    r.add_argument("-o", "--out", help="default: <head>.report-r<round>.html beside the ledger")
    r.add_argument("--template", help="default: ../assets/report-template.html")
    r.add_argument("--strict", action="store_true", help="exit 1 on any parse warning")
    c = sp.add_parser("check", help="compare a responses file with the ledger before ingesting it")
    c.add_argument("responses")
    c.add_argument("ledger")
    a = ap.parse_args()
    sys.exit(cmd_render(a) if a.cmd == "render" else cmd_check(a))


if __name__ == "__main__":
    main()
