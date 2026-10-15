"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, Board, api } from "./api";

const KEY = "shortlist.workspace";

function read(): string | null {
  try { return window.localStorage.getItem(KEY); } catch { return null; }
}
function write(value: string) {
  try { window.localStorage.setItem(KEY, value); } catch { /* private window */ }
}

export function useWorkspace() {
  const [ws, setWs] = useState<string | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id: string): Promise<boolean> => {
    try {
      setBoard(await api.board(id));
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return false;
      setError(e instanceof Error ? e.message : String(e));
      return true;
    }
  }, []);

  useEffect(() => {
    (async () => {
      let id = read();
      if (!id || !(await load(id))) {
        try {
          id = (await api.createWorkspace()).workspace_id;
          write(id);
          await load(id);
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
          return;
        }
      }
      setWs(id);
    })();
  }, [load]);

  const refresh = useCallback(async () => { if (ws) await load(ws); }, [ws, load]);
  const reset = useCallback(async () => { if (ws) { await api.reset(ws); await load(ws); } }, [ws, load]);
  return { ws, board, error, refresh, reset };
}
