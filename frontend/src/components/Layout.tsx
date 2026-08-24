import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import DisclaimerBanner from "./DisclaimerBanner";
import { ASSETS, MODELS, NAV_ITEMS, TIMEFRAMES } from "../services/navConfig";
import { useAuth } from "../hooks/useAuth";

export default function Layout({ children }: { children: ReactNode }) {
  const { logout } = useAuth();

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="app-title">Market Intelligence Platform</h1>
        <nav>
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === "/"}>
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
            <select defaultValue={ASSETS[0]}>
              {ASSETS.map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </label>
          <label>
            Timeframe
            <select defaultValue={TIMEFRAMES[1]}>
              {TIMEFRAMES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label>
            Model
            <select defaultValue={MODELS[4]}>
              {MODELS.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
        </div>

        <main>{children}</main>
      </div>
    </div>
  );
}
