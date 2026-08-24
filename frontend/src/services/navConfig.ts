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
  { path: "/replay", label: "Historical Replay" },
];

export interface SelectOption<K extends string> {
  key: K;
  label: string;
}

export const ASSETS: SelectOption<"EURUSD" | "BTCUSD" | "XAUUSD">[] = [
  { key: "EURUSD", label: "EUR/USD" },
  { key: "BTCUSD", label: "BTC/USD" },
  { key: "XAUUSD", label: "XAU/USD" },
];

export const TIMEFRAMES: SelectOption<"M15" | "H1" | "H4" | "D1">[] = [
  { key: "M15", label: "M15" },
  { key: "H1", label: "H1" },
  { key: "H4", label: "H4" },
  { key: "D1", label: "D1" },
];

export const MODELS: SelectOption<"logistic_regression" | "random_forest" | "svm" | "xgboost">[] = [
  { key: "logistic_regression", label: "Logistic Regression" },
  { key: "random_forest", label: "Random Forest" },
  { key: "svm", label: "SVM" },
  { key: "xgboost", label: "XGBoost" },
];

export const NOT_LIVE_TRADING_DISCLAIMER =
  "This platform operates entirely on historical data for research and education. " +
  "It is not a live trading system: it does not stream real-time market data, place " +
  "orders, connect to a broker, or execute trades. Predictions are not financial advice " +
  "and do not guarantee future performance.";
