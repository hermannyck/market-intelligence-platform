import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Asset, ModelKey, Timeframe } from "../api/types";

interface SelectionContextValue {
  asset: Asset;
  timeframe: Timeframe;
  model: ModelKey;
  setAsset: (a: Asset) => void;
  setTimeframe: (t: Timeframe) => void;
  setModel: (m: ModelKey) => void;
}

const SelectionContext = createContext<SelectionContextValue | undefined>(undefined);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [asset, setAsset] = useState<Asset>("EURUSD");
  const [timeframe, setTimeframe] = useState<Timeframe>("D1");
  const [model, setModel] = useState<ModelKey>("random_forest");

  const value = useMemo(
    () => ({ asset, timeframe, model, setAsset, setTimeframe, setModel }),
    [asset, timeframe, model],
  );

  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection(): SelectionContextValue {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error("useSelection must be used within a SelectionProvider");
  return ctx;
}
