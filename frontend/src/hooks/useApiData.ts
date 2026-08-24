import { useEffect, useState } from "react";
import { ApiError } from "../api/client";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  notFound: boolean;
}

/** Runs `fetcher` whenever any value in `deps` changes, tracking loading/error/not-found
 * state. `notFound` is split out from `error` since a 404 here almost always means "that
 * phase's pipeline hasn't been run for this combination yet" (a data gap), not a real error --
 * pages render a friendlier message for it. */
export function useApiData<T>(fetcher: () => Promise<T>, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null, notFound: false });

  useEffect(() => {
    let cancelled = false;
    setState({ data: null, loading: true, error: null, notFound: false });

    fetcher()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null, notFound: false });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ data: null, loading: false, error: null, notFound: true });
        } else {
          const message = err instanceof Error ? err.message : "Unknown error";
          setState({ data: null, loading: false, error: message, notFound: false });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
