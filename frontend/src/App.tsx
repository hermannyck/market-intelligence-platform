import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./hooks/useAuth";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import MarketAnalysisPage from "./pages/MarketAnalysisPage";
import PredictionsPage from "./pages/PredictionsPage";
import ExplainabilityPage from "./pages/ExplainabilityPage";
import ModelLabPage from "./pages/ModelLabPage";
import WalkForwardValidationPage from "./pages/WalkForwardValidationPage";
import BacktestingPage from "./pages/BacktestingPage";
import NewsSentimentPage from "./pages/NewsSentimentPage";

function Protected({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Protected><DashboardPage /></Protected>} />
        <Route path="/market-analysis" element={<Protected><MarketAnalysisPage /></Protected>} />
        <Route path="/predictions" element={<Protected><PredictionsPage /></Protected>} />
        <Route path="/explainability" element={<Protected><ExplainabilityPage /></Protected>} />
        <Route path="/model-lab" element={<Protected><ModelLabPage /></Protected>} />
        <Route
          path="/walk-forward-validation"
          element={<Protected><WalkForwardValidationPage /></Protected>}
        />
        <Route path="/backtesting" element={<Protected><BacktestingPage /></Protected>} />
        <Route path="/news-sentiment" element={<Protected><NewsSentimentPage /></Protected>} />
      </Routes>
    </AuthProvider>
  );
}
