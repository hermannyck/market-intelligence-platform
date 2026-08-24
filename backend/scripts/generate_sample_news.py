"""One-off generator for data/news/sample_headlines.csv.

**This produces synthetic, template-based sample headlines — not real historical news.** A
genuine multi-year historical financial news archive requires a licensed data vendor (e.g.
RavenPack, Dow Jones, Bloomberg) this project doesn't have. The spec's own Section 7 explicitly
anticipates this: "If historical news data is unavailable during the initial implementation,
create a clean news-data interface and use a clearly documented sample/historical dataset
rather than pretending that future news is available." This script is that documented sample,
kept in the repo so exactly how it was produced is transparent and reproducible (fixed random
seed) — not a black-box CSV that showed up with no explanation.

The templates below are deliberately real-world-plausible (genuine categories of financial news:
central bank decisions, macro data releases, regulatory news, risk sentiment) with realistic
positive/negative/neutral tone variety, so FinBERT (Phase 10's actual sentiment model) has
something meaningfully varied to score — but no headline claims to report a specific real event
that did or didn't happen. Dates are weighted toward the last ~2 years (skewed further toward
the last ~90 days) to align with where this project's H1/M15 OHLCV history actually exists
(see docs/data_sources.md) — this sample does NOT attempt to cover D1's multi-decade history,
and that gap is documented, not hidden (see docs/leakage_prevention.md's Phase 10 entry).

Run: `cd backend && .venv/Scripts/python scripts/generate_sample_news.py`
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "news" / "sample_headlines.csv"

SEED = 20260824  # fixed for reproducibility -- rerunning this script regenerates the same file
HEADLINES_PER_ASSET = 60  # -> 180 total across 3 assets

ASSET_DISPLAY = {"EURUSD": "EUR/USD", "BTCUSD": "BTC/USD", "XAUUSD": "Gold"}

POSITIVE_TEMPLATES = [
    "{asset} rallies as {reason}",
    "{asset} extends gains after {reason}",
    "Analysts turn bullish on {asset} amid {reason}",
    "{asset} climbs on {reason}",
    "{asset} strengthens as traders cite {reason}",
]

NEGATIVE_TEMPLATES = [
    "{asset} slides as {reason}",
    "{asset} under pressure following {reason}",
    "{asset} tumbles on {reason}",
    "{asset} weakens amid {reason}",
    "{asset} retreats as traders weigh {reason}",
]

NEUTRAL_TEMPLATES = [
    "{asset} trades sideways ahead of {event}",
    "Investors await {event} for {asset} direction",
    "{asset} little changed in quiet trading",
    "{asset} holds steady as markets digest {event}",
    "Traders eye {event} for the next move in {asset}",
]

REASONS = {
    "EURUSD": {
        "positive": [
            "stronger-than-expected Eurozone PMI data",
            "hawkish signals from ECB policymakers",
            "German industrial output beating forecasts",
            "easing inflation supporting the euro outlook",
            "improved risk appetite across European markets",
        ],
        "negative": [
            "weak German factory orders",
            "rising political uncertainty in France",
            "dovish comments from ECB officials",
            "broad US dollar strength",
            "a widening Eurozone trade deficit",
        ],
        "event": [
            "the ECB rate decision",
            "Eurozone CPI data",
            "US non-farm payrolls",
            "German GDP figures",
            "the Federal Reserve's policy meeting",
        ],
    },
    "BTCUSD": {
        "positive": [
            "strong inflows into spot Bitcoin ETFs",
            "growing institutional adoption",
            "improved regulatory clarity in the US",
            "record trading volumes on major exchanges",
            "renewed risk-on sentiment across crypto markets",
        ],
        "negative": [
            "a wave of long liquidations",
            "regulatory crackdown concerns",
            "an exchange outage disrupting trading",
            "profit-taking after a sharp rally",
            "broader risk-off sentiment in markets",
        ],
        "event": [
            "the next FOMC meeting",
            "a key options expiry",
            "a widely-watched support level test",
            "quarterly futures settlement",
            "upcoming US inflation data",
        ],
    },
    "XAUUSD": {
        "positive": [
            "rising safe-haven demand amid geopolitical tensions",
            "falling real yields",
            "broad US dollar weakness",
            "continued central bank gold purchases",
            "persistent inflation concerns",
        ],
        "negative": [
            "a stronger US dollar",
            "rising Treasury yields",
            "improved risk appetite reducing haven demand",
            "profit-taking after recent highs",
            "reduced expectations of Fed rate cuts",
        ],
        "event": [
            "the Fed's rate decision",
            "US CPI data",
            "the monthly jobs report",
            "central bank gold reserve data",
            "the next FOMC statement",
        ],
    },
}


def _random_timestamp(rng: Random, now: datetime) -> datetime:
    """Weighted toward recent history: 45% in the last 90 days, 40% in the 90d-2y range,
    15% in the 2y-3y range -- aligned with actual H1/M15 data depth (docs/data_sources.md),
    not claiming coverage this project's D1 backbone doesn't have real news for."""
    roll = rng.random()
    if roll < 0.45:
        days_ago = rng.uniform(0, 90)
    elif roll < 0.85:
        days_ago = rng.uniform(90, 730)
    else:
        days_ago = rng.uniform(730, 1095)
    ts = now - timedelta(days=days_ago, hours=rng.uniform(0, 24))
    return ts.replace(microsecond=0)


def generate() -> list[dict]:
    rng = Random(SEED)
    now = datetime.now(timezone.utc)
    rows = []
    for asset_key, display in ASSET_DISPLAY.items():
        reasons = REASONS[asset_key]
        per_tone = HEADLINES_PER_ASSET // 3
        for tone, templates, reason_key in (
            ("positive", POSITIVE_TEMPLATES, "positive"),
            ("negative", NEGATIVE_TEMPLATES, "negative"),
            ("neutral", NEUTRAL_TEMPLATES, "event"),
        ):
            for _ in range(per_tone):
                template = rng.choice(templates)
                reason = rng.choice(reasons[reason_key])
                headline = template.format(asset=display, reason=reason, event=reason)
                rows.append(
                    {
                        "published_at": _random_timestamp(rng, now).isoformat(),
                        "asset_key": asset_key,
                        "headline": headline,
                        "generated_tone": tone,  # the INTENDED tone of the template, not a
                        # FinBERT score -- kept only as provenance/sanity-check metadata, never
                        # used as a feature or ground truth (see module docstring).
                    }
                )
    rows.sort(key=lambda r: r["published_at"])
    return rows


if __name__ == "__main__":
    rows = generate()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["published_at", "asset_key", "headline", "generated_tone"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} sample headlines to {OUTPUT_PATH}")
