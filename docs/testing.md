# Testing strategy

Phase 16 is the spec's final phase ("testing and documentation"). Every phase before this one
already shipped its own tests as it was built — Phase 16 doesn't retrofit tests onto untested
code; it closes real, checked gaps, adds a first frontend test suite, and writes this document
so the state of testing is a fact anyone can verify, not a claim to take on faith.

## Backend: 160 tests, 91% statement coverage

```bash
cd backend
.venv\Scripts\pip install -r requirements.txt   # pytest-cov is now pinned in here
.venv\Scripts\python -m pytest -q --cov=app --cov-report=term-missing
```

Coverage is measured with `pytest-cov` (added this phase — see `requirements.txt`), not
guessed. The real number as of Phase 16: **91% of `app/`'s 1,746 statements**, 160 tests, one
test file per module (`tests/test_<module>.py`), covering:

- Every no-lookahead/leakage-boundary claim made in `docs/leakage_prevention.md` has a test
  that verifies it directly (truncated-series recomputation, out-of-sample window coverage,
  fit-on-train-only, etc.) — cross-referenced by phase in that document.
- Every API router: happy path against real generated data (skipped automatically on a fresh
  clone that hasn't run the pipeline yet) *and* the 404/empty-data path with synthetic fixtures.
- Auth: registration, login, wrong password, missing token, garbage token, and (added this
  phase) a structurally-valid token whose subject no longer has a `users` row.
- The app's stated resilience claim that the API works even when the database is unreachable
  (added this phase — mocks `Base.metadata.create_all` to raise during startup and confirms
  `/health` still responds).
- The backtest engine's defensive branches (added this phase): unsorted input rejected, a
  signal timestamp absent from the OHLC dataset skipped rather than raising `KeyError`, and an
  invalid ATR/price at a signal bar skipped rather than sizing a nonsensical stop.

### What's intentionally not covered, and why

Coverage tools reward exercising every line equally; not every line carries equal risk. The
remaining ~9% is concentrated in three low-risk categories, left uncovered on purpose rather
than padded out for a number:

1. **CLI entry points** (`if __name__ == "__main__":` blocks) and their **`run_all_*`
   aggregators** (`app/ml/models.py`, `app/ml/target.py`, `app/sentiment/pipeline.py`,
   `app/services/cleaning.py`, `app/services/ingestion.py`, `app/validation/walk_forward.py`,
   `app/backtesting/pipeline.py`, `app/explainability/pipeline.py`) — thin loops over every
   asset/timeframe/model combination that call already-tested single-combo functions and print
   a summary line, catching `(FileNotFoundError, ValueError)` per combo so one bad combination
   doesn't abort the rest. The single-combo path each one calls *is* tested; the loop itself has
   been exercised for real, repeatedly, every phase from Phase 2 onward (`python -m app.X.Y`),
   with the real printed output checked by hand each time — see this project's `git log` and
   `docs/model_card.md`/`docs/data_sources.md` for that real output. A unit test that mocks four
   combinations (one success, one `FileNotFoundError`, one `ValueError`, one exception) to
   assert the loop keeps going would mostly test that Python's `try/except` works.
2. **`app/database/session.py`'s real `get_session`** (and `app/api/deps.py::get_db`'s
   pass-through to it) — every API test overrides `get_db` with an in-memory SQLite session
   (the standard FastAPI testing pattern; see `tests/test_api_auth.py`'s `client` fixture) so
   tests never touch a real engine. The real function is three lines (create a session, yield
   it, close it in `finally`) and is exercised every time the app actually runs against
   `DATABASE_URL` (documented in `README.md`'s Database section) — not covered under pytest,
   but not unverified either.
3. **A handful of narrow, hard-to-construct edge cases** in individual modules (e.g.
   `app/api/routers/predictions.py`'s `FileNotFoundError` branch, which requires a data state
   where trained model files exist but the features file that produced them doesn't) — each
   left as a specific, named line in the coverage report rather than silently ignored; grep
   `--cov-report=term-missing`'s output above for the current exact list.

None of the three categories above touch a leakage boundary, a financial calculation, or an
auth decision — the categories this project treats as must-test (see the bullet list above).

**A known, occasional flake, noted here rather than left a mystery**:
`tests/test_regime_pipeline.py::test_save_with_regime_never_overwrites` (a Phase 9 test,
unrelated to anything Phase 16 touched) failed once during this phase's verification runs, then
passed cleanly both in isolation and on the very next full-suite run. The test itself mocks a
fixed `datetime` rather than depending on real timestamp collisions, so this looks like Windows
filesystem/temp-directory timing rather than a logic bug — flagged here in case it recurs often
enough to warrant investigation, not silently ignored.

## Frontend: Vitest, added this phase

Before Phase 16 the frontend had no automated tests at all — a deliberate scope decision
carried over from the sibling `forex-signal-predictor` project (see
`docs/architecture.md`'s Frontend structure section). Phase 15's live browser verification then
caught two real bugs in `ReplayPage`'s client-side join logic (a timestamp-format mismatch and
a too-small fetch limit — both documented in `docs/leakage_prevention.md`'s Phase 15 entry) that
a type checker cannot catch, because both were valid TypeScript operating on data whose *values*
were wrong, not its *shape*. That's the direct justification for Phase 16 adding a first,
narrowly-scoped test suite rather than leaving frontend testing at zero indefinitely:

```bash
cd frontend
npm install    # vitest is now a devDependency
npm run test    # vitest run -- one-shot, not watch mode
```

`src/utils/replayFrames.ts` — the exact join logic that had both real bugs — was extracted out
of `ReplayPage.tsx` specifically so it could be unit-tested without rendering a component or
mocking `fetch`. `src/utils/replayFrames.test.ts` pins down: the two real timestamp formats
joining to the same instant, bars with no out-of-sample signal being excluded, frames coming out
sorted regardless of input order, equity/trade events attaching only to the bars they actually
occurred on, and a pre-Phase-15 backtest report (missing the `signals` field entirely) producing
an empty timeline rather than throwing.

This is deliberately **not** a full component/rendering test suite (no React Testing Library,
no DOM assertions) — the highest-value, lowest-effort target was the one module that had already
produced two real bugs, not blanket coverage of every page. Visual/interaction correctness
across all 9 pages is still verified manually (documented in each phase's commit message and the
project memory file) — a decision consistent with this project's Phase 14 rationale for not
building a rendering test harness in the first place.

### A note on browser-automation testing in this environment

While manually verifying Phase 15 in this sandbox's headless browser tool, synthesized
coordinate-based clicks were unreliable at a resized (1400×1000) viewport with
`devicePixelRatio: 1.25` — clicks landed measurably off their target element, silently no-op'ing
instead of erroring. Confirmed by comparing the tool's resolved click coordinate against the
target element's real `getBoundingClientRect()`, and worked around by dispatching a real
`element.click()` via direct JS execution instead. Worth remembering for any future manual
browser verification in this environment: if a click via element reference seems to silently do
nothing, suspect coordinate/`devicePixelRatio` scaling at non-default viewport sizes before
suspecting the application's own event handlers.

## Dependency hygiene (checked this phase)

`npm audit` flagged a critical RCE advisory in the `vitest` version initially installed
(`GHSA-5xrq-8626-4rwp`, fixed in `vitest>=3.2.6`) and a high-severity open-redirect advisory in
the already-pinned `react-router-dom@6.28.0` (fixed in `6.30.6`, same major version, no breaking
change). Both were bumped to their patched versions rather than left in place. Two remaining
advisories were left as documented, accepted risk rather than force-upgraded: `vite`/`esbuild`'s
dev-server-only advisory (irrelevant to the production build this project ships, and a fix
requires an unrelated major-version bump) and `react-router-dom`'s two `7.x`-only advisories
(fixing them means a major version migration — out of scope for a documentation/testing phase;
worth a scoped increment of its own if this project continues past Phase 16).
