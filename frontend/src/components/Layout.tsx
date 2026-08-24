import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import DisclaimerBanner from "./DisclaimerBanner";
import { ASSETS, MODELS, NAV_ITEMS, TIMEFRAMES } from "../services/navConfig";
import { useAuth } from "../hooks/useAuth";
import { useSelection } from "../hooks/useSelection";
import type { Asset, ModelKey, Timeframe } from "../api/types";

export default function Layout({ children }: { children: ReactNode }) {
  const { logout } = useAuth();
  const { asset, timeframe, model, setAsset, setTimeframe, setModel } = useSelection();

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="app-title">Market Intelligence Platform</h1>
        <nav>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button onClick={logout}>Log out</button>
      </aside>

      <div className="main">
        <DisclaimerBanner />

        <div className="global-selectors">
          <label>
            Asset
            <select value={asset} onChange={(e) => setAsset(e.target.value as Asset)}>
              {ASSETS.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Timeframe
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)}>
              {TIMEFRAMES.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Model
            <select value={model} onChange={(e) => setModel(e.target.value as ModelKey)}>
              {MODELS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <main>{children}</main>
      </div>
    </div>
  );
}
