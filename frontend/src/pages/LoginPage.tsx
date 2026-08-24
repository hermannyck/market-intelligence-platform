import { useNavigate } from "react-router-dom";
import DisclaimerBanner from "../components/DisclaimerBanner";
import { useAuth } from "../hooks/useAuth";

// Phase 1 note: accepts any input and "logs in" locally. Real credential handling against
// the backend's /api/auth endpoints lands once that router has logic behind it (Phase 13).
export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    login();
    navigate("/", { replace: true });
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
          <input type="password" name="password" required />
        </label>
        <label className="acknowledge">
          <input type="checkbox" required />
          I understand this is a research tool operating on historical data only.
        </label>
        <button type="submit">Enter platform</button>
      </form>
    </div>
  );
}
