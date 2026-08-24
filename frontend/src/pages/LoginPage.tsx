import { useState } from "react";
import { useNavigate } from "react-router-dom";
import DisclaimerBanner from "../components/DisclaimerBanner";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../api/client";

// Phase 13: real register/login against the backend's /api/auth endpoints, replacing Phase
// 1's stub that accepted any input.
export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");

    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Could not reach the backend API. Is it running?");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <h1>Market Intelligence Platform</h1>
      <DisclaimerBanner />
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" name="email" required />
        </label>
        <label>
          Password
          <input type="password" name="password" required minLength={mode === "register" ? 8 : undefined} />
        </label>
        <label className="acknowledge">
          <input type="checkbox" required />
          I understand this is a research tool operating on historical data only.
        </label>
        {error && <div className="error">{error}</div>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
      <button
        type="button"
        className="link-button"
        onClick={() => {
          setMode(mode === "login" ? "register" : "login");
          setError(null);
        }}
      >
        {mode === "login" ? "Need an account? Register" : "Already have an account? Log in"}
      </button>
    </div>
  );
}
