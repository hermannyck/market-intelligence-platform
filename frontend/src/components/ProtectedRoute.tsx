import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, checkingSession } = useAuth();
  if (checkingSession) {
    return <div className="loading-state">Checking session…</div>;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
