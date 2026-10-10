# Harvest ledger: origin/main → upstream/main

<!-- SYNTHETIC FIXTURE. The real ledger (~/code/curry/matt-daemon/.git/harvest/curry.md) was not reachable
     from the cloud container this prototype was built in. Entries are invented but follow the entry
     template in skills/harvest/SKILL.md. -->

Base: upstream/main @ 4be19e2
Head: origin/main @ 8c1d2e0
Merge-base: 3f2a91c
Updated: 2026-10-02 16:40
Content-free merges: 71d0c5a (merge of origin/dev, no content), e92b4f1 (merge of upstream/main into origin/main)
Not in range: 5aa3c10 (upstream merge "rate limiter rebuild", brought fork-authored work in below the merge-base)
Read in full: src/pantry/**, daemon/**
Attributed only: tests/**, docs/**, deploy/**, uv.lock

### F1. Structured JSON logging with request ids

Every log line is emitted as one JSON object carrying the job id and a per-request id, instead of free-form text.
Why: "grep-able logs for the on-call rotation" (commit 7ab1c22).

- Size: +180 / -41 across 5 files
- Commits: 7ab1c22, 0de4f19
- Files: 5 (1 shared). Source: src/pantry/log.py (new), src/pantry/worker.py (shared with F4)
- Depends on: none
- Fit: aligned. CONTRIBUTING.md:31 asks for "machine-readable logs where practical".
- Status: landed: harvest/structured-json-logging

### F2. Layered TOML config loader

Config is read from /etc, then the user directory, then the working directory, each layer overriding the last.
Why: "ops wanted per-host overrides without editing the shipped file" (commit 3c9d8e0).

- Size: +210 / -66 across 4 files
- Commits: 3c9d8e0, b4417ad
- Files: 4 (2 shared). Source: src/pantry/config.py (shared with F14, F16), src/pantry/cli.py
- Depends on: none
- Fit: aligned. README.md:58 lists "files in /etc" as supported config; layering is a small extension.
- Status: open

### F3. Persist job records in SQLite

Job state survives a daemon restart because it is stored in a SQLite file instead of an in-memory dict.
Why: "jobs were lost on every deploy" (commit 91fe0b3).

- Size: +520 / -88 across 9 files
- Commits: 91fe0b3, a77c4de, 2d0e8b9
- Files: 9 (3 shared). Source: src/pantry/store.py (new), src/pantry/queue.py (shared with F6, F13), src/pantry/models.py
- Depends on: F2 (reads the database path from the layered config)
- Fit: tension. ADR-002 says "job state is in memory; durability is the caller's problem".
- Status: open

### F4. Retry failed jobs with exponential backoff

Jobs that fail are retried up to five times with growing delays, instead of being dropped.
Why: "flaky downstreams drop work silently" (commit c3a90e5).

- Size: +240 / -12 across 6 files
- Commits: c3a90e5, e4f5a6b (partial: src/pantry/queue.py)
- Files: 6 (2 shared). Source: src/pantry/retry.py (new), src/pantry/queue.py (shared with F3)
- Depends on: F3 (attempt counts live in the job table), F1 (adds `_retry_delay` to F1's log context)
- Fit: tension. Adds a background timer thread; ADR-004 says the worker is single-threaded.
- Status: open
- Notes:
  - 2026-10-02 Q: Does the retry timer really need its own thread? A: It only runs the backoff sleep (retry.py:40-88). Base's worker already has a scheduled-job queue (worker/jobs.py:12), so a retry could re-enqueue itself with a delay and ADR-004 stays intact.

### F5. Dead-letter queue for exhausted retries

Jobs that use up their retries are parked in a dead-letter table where an operator can inspect and replay them.
Why: "we kept losing the jobs that mattered most" (commit 5f1be27).

- Size: +160 / -4 across 3 files
- Commits: 5f1be27
- Files: 3 (1 shared). Source: src/pantry/deadletter.py (new), src/pantry/retry.py (shared with F4)
- Depends on: F4 (hooks the retry-exhausted event), F3 (dead letters are rows in the job table)
- Fit: aligned. docs/design.md:44 already names a "dead letter" as a future concept.
- Status: open

### F6. Priority lanes (high, normal, low)

Jobs carry a priority and workers drain high before normal before low, instead of strict arrival order.
Why: "billing jobs queued behind a 40,000-row export" (commit 08ac6d1).

- Size: +130 / -30 across 4 files
- Commits: 08ac6d1, 1b7e33f
- Files: 4 (1 shared). Source: src/pantry/queue.py (shared with F3), src/pantry/priority.py (new)
- Depends on: F3 (priority is a column on the job row)
- Fit: aligned. README.md:72 lists "ordering" as an extension point.
- Status: open

### F7. Per-queue concurrency limits

Each named queue can cap how many of its jobs run at once, instead of one global worker count.
Why: "one noisy queue starves the rest" (commit d19e840).

- Size: +95 / -22 across 3 files
- Commits: d19e840
- Files: 3 (2 shared). Source: src/pantry/worker.py (shared with F1, F8), src/pantry/config.py (shared with F2)
- Depends on: F2 (limits are configured per queue), F6 (limits apply per lane)
- Fit: tension. ADR-004's single-threaded worker has no notion of concurrent jobs; this assumes a thread pool.
- Status: open

### F8. Graceful shutdown drains in-flight jobs

On SIGTERM the daemon stops taking new jobs and waits for running ones to finish, up to a configurable grace period.
Why: "deploys killed jobs halfway through" (commit 6e2d415).

- Size: +85 / -9 across 3 files
- Commits: 6e2d415
- Files: 3 (1 shared). Source: src/pantry/shutdown.py (new), src/pantry/worker.py (shared with F1, F7)
- Depends on: none
- Fit: aligned. CONTRIBUTING.md:19 asks that long-running processes handle SIGTERM.
- Status: picked: cherry-pick, batch: shutdown

### F9. Health endpoint

`GET /healthz` returns 200 while the worker loop is alive and 503 once it stalls, for load balancers and orchestrators.
Why: "the orchestrator could not tell a stuck daemon from a busy one" (commit f0a1c93).

- Size: +70 / -0 across 2 files
- Commits: f0a1c93
- Files: 2 (0 shared). Source: src/pantry/health.py (new), src/pantry/http.py
- Depends on: F1 (uses the request-id middleware)
- Fit: aligned. README.md:90 says "a health check is welcome".
- Status: open

### F10. Prometheus metrics endpoint

`GET /metrics` exposes queue depth, job durations and failure counts in Prometheus text format.
Why: unstated.

- Size: +190 / -6 across 4 files
- Commits: 44cd02e, 9be5f71
- Files: 4 (1 shared). Source: src/pantry/metrics.py (new), src/pantry/http.py (shared with F9)
- Depends on: F9 (registers on the same HTTP server), F1
- Fit: tension. CONTRIBUTING.md:44 says new runtime dependencies need an ADR; this adds `prometheus-client`.
- Status: open

### F11. Admin CLI for jobs

`pantryctl jobs list|show|retry|cancel` lets an operator inspect and act on jobs from a shell.
Why: "we were running SQL by hand" (commit b82f6a4).

- Size: +310 / -0 across 5 files
- Commits: b82f6a4, 73e9d0c
- Files: 5 (1 shared). Source: src/pantryctl/ (new), src/pantry/cli.py (shared with F2)
- Depends on: F3 (reads the job table), F5 (the `retry` subcommand replays dead letters)
- Fit: aligned. docs/design.md:61 sketches a control CLI.
- Status: open

### F12. Web admin UI

A small single-page web app lists queues and jobs, with buttons to retry and cancel, served from the daemon itself.
Why: "the CLI is not for the support team" (commit e61f3b8).

- Size: +1,420 / -0 across 22 files
- Commits: e61f3b8, 02d7aa4, c5b9e61
- Files: 22 (1 shared). Source: web/ (new), src/pantry/http.py (shared with F9, F10)
- Depends on: F11 (calls the same actions), F10 (draws charts from /metrics)
- Fit: conflict. README.md:12 states "no web UI; the daemon is headless by design".
- Status: open

### F13. Scheduled (cron-style) jobs

A job can be registered with a cron expression and the daemon enqueues it on schedule, instead of relying on an external cron.
Why: "cron on three hosts fired the same job three times" (commit 1ae48d7).

- Size: +260 / -14 across 5 files
- Commits: 1ae48d7, 8d03fb6
- Files: 5 (2 shared). Source: src/pantry/schedule.py (new), src/pantry/queue.py (shared with F3, F6)
- Depends on: F3 (schedule state is persisted), F6 (scheduled jobs pick a lane)
- Fit: tension. ADR-005 says "scheduling is the caller's job".
- Status: open

### F14. Signed job payloads (HMAC)

Payloads are signed when enqueued and verified before running, so a tampered row is rejected.
Why: "the queue file is world-readable on shared hosts" (commit a2e07c8).

- Size: +120 / -3 across 3 files
- Commits: a2e07c8
- Files: 3 (1 shared). Source: src/pantry/signing.py (new), src/pantry/config.py (shared with F2)
- Depends on: F2 (the signing key comes from config)
- Fit: aligned. CONTRIBUTING.md:52 asks for integrity checks on persisted data.
- Status: left

### F15. Job timeouts with cancellation

A job that runs past its timeout is cancelled cooperatively, and killed if it ignores the cancellation.
Why: "a hung job held a worker slot for nine days" (commit 37b5d1e).

- Size: +175 / -20 across 4 files
- Commits: 37b5d1e, c0f9a42
- Files: 4 (2 shared). Source: src/pantry/timeout.py (new), src/pantry/worker.py (shared with F1, F7, F8)
- Depends on: F8 (reuses the drain/cancel path), F4 (a timeout counts as a failed attempt)
- Fit: tension. Cooperative cancellation needs a second thread; ADR-004.
- Status: open

### F16. Webhook notification when a job dead-letters

An operator-configured URL receives a POST with the job summary when a job lands in the dead-letter table.
Why: "we found dead jobs a week late" (commit 9d44e6b).

- Size: +110 / -0 across 3 files
- Commits: 9d44e6b
- Files: 3 (1 shared). Source: src/pantry/notify.py (new), src/pantry/config.py (shared with F2)
- Depends on: F5 (fires on the dead-letter event), F2 (URL from config), F1 (line to edit: log context in `notify._post`)
- Fit: aligned. README.md:95 mentions "outgoing hooks" as welcome.
- Status: open
- Notes:
  - 2026-10-02 Note: A shared secret for the webhook is stored in plain config; check whether F14's signing key can be reused.

### F17. Multi-tenant namespaces

Queues, jobs and config can be scoped to a tenant name, and tenants cannot see each other's jobs.
Why: "we host three customers on one daemon" (commit 55e1d0b).

- Size: +640 / -210 across 14 files
- Commits: 55e1d0b, 61c8fa2, d7a03e9
- Files: 14 (6 shared). Source: src/pantry/tenancy.py (new), src/pantry/store.py (shared with F3), src/pantry/config.py (shared with F2)
- Depends on: F3, F2, F7 (per-tenant concurrency)
- Fit: conflict. README.md:12 and ADR-001 describe a single-tenant daemon; every public function would change.
- Status: open

### Plumbing. Dependency bumps, CI cache, renames

Formatting, lockfile updates, the CI cache key and a package rename, with no user-facing intent.
Why: unstated.

- Size: +310 / -290 across 18 files
- Commits: 1f0c2b7, 8a6d9e4, c71e0b3
- Files: 18 (0 shared). Source: pyproject.toml, uv.lock, .github/workflows/ci.yml
- Depends on: none
- Fit: aligned. Nothing here touches behaviour.
- Status: open

### Head-only. Fork docs, deployment config, persona

The fork's own README banner, Kubernetes manifests and deploy scripts.
Why: unstated.

- Size: +480 / -12 across 17 files
- Commits: 2b9e7a0, f44d1c6
- Files: 17 (0 shared). Source: deploy/**, FORK.md, README.md (banner only)
- Depends on: none
- Fit: conflict. FORK.md:7 keeps deployment config off upstream.
- Status: open

### S1. Token-bucket rate limiter (rebuilt on upstream, merged back)

The rate limiter the fork wrote was rebuilt onto upstream last month and merged back, so the fork's original commits show in the log.
Why: "limit abusive enqueuers" (commit 4d8e2c1).

- Size: +140 / -0 across 3 files
- Commits: 4d8e2c1, 90b3ae7
- Files: 3 (0 shared). Source: src/pantry/ratelimit.py
- Depends on: none
- Fit: aligned. Already on base.
- Status: landed: already on base
- Notes:
  - Evidence: upstream/main src/pantry/ratelimit.py has the same bucket logic (merge 5aa3c10); pass 3.

### S2. `--version` flag

`pantry --version` prints the package version.
Why: unstated.

- Size: +12 / -0 across 1 file
- Commits: 6c1d0fa
- Files: 1 (0 shared). Source: src/pantry/cli.py
- Depends on: none
- Fit: aligned. Already on base.
- Status: landed: already on base
- Notes:
  - Evidence: patch-equivalent commit on base (pass 1, `git log --cherry-pick`).
