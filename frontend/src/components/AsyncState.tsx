import type { ReactNode } from "react";

interface Props {
  loading: boolean;
  error: string | null;
  notFound: boolean;
  notFoundMessage?: string;
  children: ReactNode;
}

/** Standard loading/error/not-found/content branches, used identically across every data
 * page so each page's own component only has to handle the "data is present" case. */
export default function AsyncState({ loading, error, notFound, notFoundMessage, children }: Props) {
  if (loading) return <div className="loading-state">Loading…</div>;
  if (error) return <div className="error-state">Could not load data: {error}</div>;
  if (notFound) {
    return (
      <div className="empty-state">
        {notFoundMessage ?? "No data yet for this asset/timeframe/model combination — run the corresponding backend pipeline phase first."}
      </div>
    );
  }
  return <>{children}</>;
}
