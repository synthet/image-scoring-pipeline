---
description: Test-triage footguns — host path artifacts, shared global state, harmless 5433 refusals
paths:
  - "tests/**"
  - "pytest.ini"
---

# Footguns: test triage

Distilled from [docs/LESSONS_LEARNED.md § Test triage](../../docs/LESSONS_LEARNED.md#test-triage).

- **`D:/Photos` vs `/mnt/d/Photos` path-test failures on the Windows host are not your bug** — confirm with `git stash` or run in gpu-shell before "fixing".
- **Pass alone, fail in the full suite = shared global state** (config cache, singletons) first. `_isolate_config_cache` in `tests/conftest.py` is the global fix; do not add per-file cache fixtures.
- **Connection refused on 5433** during a plain unit run is the E2E test DB being down — noise, not a failure.
- Fast subset needs `--ignore=tests/test_probe.py` (import-time DB calls).
- **The PostgreSQL test DB keeps state between runs.** `clean_postgres` truncates at test *setup*, so the last PG test leaves its rows and modes behind (e.g. localization authority `active`). A unit test that reaches the real DB through newly added code then fails only after a PG suite ran. Stub that DB path in the unit tests, and prove they are hermetic by rerunning with `POSTGRES_HOST` set to an unreachable host.
- **A skipped DB suite is not a baseline.** Views a newer branch created in `image_scoring_test` can make an older checkout's bootstrap fail, and pytest reports skips, not failures. When comparing against an older commit (temporary worktree), check the skip count; drop the newer read views first; the newer bootstrap recreates them.
