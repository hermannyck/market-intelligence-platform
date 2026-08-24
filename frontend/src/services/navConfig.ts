// Single source of truth for the spec's Section 13 navigation. Pages and the sidebar both
// read from this list so they can't drift out of sync.
export interface NavItem {
  path: string;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard" },
  { path: "/market-analysis", label: "Market Analysis" },
  { path: "/predictions", label: "Predictions" },
  { path: "/explainability", label: "Explainability" },
  { path: "/model-lab", label: "Model Lab" },
  { path: "/walk-forward-validation", label: "Walk-Forward Validation" },
  { path: "/backtesting", label: "Backtesting" },
  { path: "/news-sentiment", label: "News Sentiment" },
];

export const ASSETS = ["EUR/USD", "BTC/USD", "XAU/USD"] as const;
export const TIMEFRAMES = ["M15", "H1", "H4", "D1"] as const;
export const MODELS = [
  "Logistic Regression",
  "Random Forest",
  "SVM",
  "XGBoost",
  "Ensemble",
] as const;

export const NOT_LIVE_TRADING_DISCLAIMER =
  "This platform operates entirely on historical data for research and education. " +
  "It is not a live trading system: it does not stream real-time market data, place " +
  "orders, connect to a broker, or execute trades. Predictions are not financial advice " +
  "and do not guarantee future performance.";
