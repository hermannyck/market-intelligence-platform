# data/raw/

Immutable ingested data, exactly as pulled from the source (yfinance) in Phase 2. **Never
overwrite or edit files here** — if a re-pull is needed, write a new timestamped file rather
than replacing an existing one, so every experiment can point at the exact raw snapshot it
used. Downstream cleaning/feature code treats everything here as read-only input.
