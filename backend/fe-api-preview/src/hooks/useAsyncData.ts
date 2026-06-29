import { useEffect, useState, type DependencyList } from "react";

interface AsyncDataState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

export function useAsyncData<T>(loader: () => Promise<T>, deps: DependencyList = []): AsyncDataState<T> {
  const [state, setState] = useState<AsyncDataState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: null }));

    loader()
      .then((data) => {
        if (!cancelled) {
          setState({ data, loading: false, error: null });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ data: null, loading: false, error: error instanceof Error ? error : new Error("알 수 없는 오류") });
        }
      });

    return () => {
      cancelled = true;
    };
  }, deps);

  return state;
}
