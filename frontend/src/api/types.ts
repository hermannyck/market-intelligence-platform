// Types mirror backend/app/services/repository.py's return shapes and
// backend/app/api/routers/*.py's response bodies. Kept loose (many optional/unknown fields)
// since the backend returns plain JSON-serialized dicts (Phase 13 deliberately didn't wrap
// every response in a rigid Pydantic model -- see docs/architecture.md's Backend API section).

export type Asset = "EURUSD" | "BTCUSD" | "XAUUSD";
export type Timeframe = "M15" | "H1" | "H4" | "D1";
export type ModelKey = "logistic_regression" | "random_forest" | "svm" | "xgboost";
export type TargetLabel = "BUY" | "HOLD" | "SELL";

export interface Bar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  EMA20?: number;
  EMA50?: number;
  EMA200?: number;
  RSI14?: number;
  MACD?: number;
  MACD_signal?: number;
  MACD_histogram?: number;
  ATR14?: number;
  BB_upper?: number;
  BB_middle?: number;
  BB_lower?: number;
  regime?: string | null;
  [key: string]: unknown;
}

export interface RegimeInfo {
  current_regime: string | null;
  regime_history: { timestamp: string; regime: string }[];
  regime_distribution: {
    total_labeled_rows: number;
    counts: Record<string, number>;
    percentages: Record<string, number>;
  };
}

export interface MarketAnalysisResponse {
  asset_key: Asset;
  asset_code: string;
  timeframe: Timeframe;
  current_timestamp: string;
  current_price: number;
  bars: Bar[];
  multi_timeframe_bias: Record<string, string | null>;
  regime: RegimeInfo | null;
}

export interface ModelPrediction {
  model_name: ModelKey;
  predicted_class: TargetLabel;
  probabilities: Record<TargetLabel, number>;
}

export interface PredictionsResponse {
  asset_key: Asset;
  asset_code: string;
  timeframe: Timeframe;
  timestamp: string;
  price: number;
  predictions: ModelPrediction[];
  consensus_class: TargetLabel | null;
  consensus_ratio: string | null;
}

export interface LocalExplanation {
  predicted_class: TargetLabel;
  probabilities: Record<TargetLabel, number>;
  top_factors: { feature: string; shap_value: number }[];
  base_value_for_predicted_class: number;
  timestamp: string;
}

export interface ExplainabilityResponse {
  asset_key: Asset;
  timeframe: Timeframe;
  model_name: ModelKey;
  global_feature_importance: Record<string, number>;
  local_explanations: LocalExplanation[];
}

export interface ModelLabResponse {
  asset_key: Asset;
  timeframe: Timeframe;
  baseline_comparison: {
    train_rows: number;
    test_rows: number;
    models: Record<string, { accuracy: number; f1_macro: number; precision_macro: number; recall_macro: number }>;
  } | null;
  walk_forward: {
    n_resolved_windows: number;
    window_source: string;
    overall: Record<string, Record<string, number>>;
  } | null;
}

export interface WalkForwardWindowResult {
  window: { train_start: string; train_end: string; test_start: string; test_end: string };
  source: string;
  train_rows: number;
  test_rows: number;
  models: Record<string, { accuracy: number; f1_macro: number; roc_auc_macro: number | null }>;
}

export interface WalkForwardResponse {
  asset_key: Asset;
  timeframe: Timeframe;
  n_configured_windows: number;
  n_resolved_windows: number;
  window_source: string;
  windows: WalkForwardWindowResult[];
  overall: Record<string, Record<string, number>>;
}

export interface Trade {
  entry_time: string;
  exit_time: string;
  direction: TargetLabel;
  entry_price: number;
  exit_price: number;
  exit_reason: string;
  net_return_pct: number;
  pnl: number;
  equity_after: number;
}

export interface BacktestSummary {
  num_trades: number;
  total_return: number;
  win_rate: number | null;
  profit_factor: number | null;
  sharpe_ratio: number | null;
  max_drawdown: number;
  avg_trade_return: number | null;
  final_equity: number;
}

export interface BacktestResponse {
  asset_key: Asset;
  timeframe: Timeframe;
  model_name: ModelKey;
  backtest_config: Record<string, unknown>;
  summary: BacktestSummary;
  trades: Trade[];
  equity_curve: { timestamp: string; equity: number }[];
}

export type PerformanceByRegime = Record<string, { num_trades: number; win_rate: number; avg_return_pct: number }>;

export interface NewsArticle {
  published_at: string;
  headline: string;
  sentiment_score: number;
  positive_prob: number;
  negative_prob: number;
  neutral_prob: number;
}

export interface NewsSentimentResponse {
  asset_key: Asset;
  asset_code?: string;
  articles: NewsArticle[];
  source?: string;
  note?: string;
}
