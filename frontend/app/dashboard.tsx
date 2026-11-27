"use client";

import { useEffect, useState } from "react";
import { A2uiSurface, MarkdownContext } from "@a2ui/react";
import { renderMarkdown } from "@a2ui/markdown-it";
import { MessageProcessor } from "@a2ui/web_core";
import { basicCatalog } from "@a2ui/web_core/catalogs/basic/v1";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "error"; message: string };

/**
 * Fetches the dashboard's A2UI messages from the backend and renders every surface.
 *
 * The backend only describes the UI; @a2ui/react draws it with the basic catalog.
 */
export default function Dashboard() {
  const [processor] = useState(() => new MessageProcessor([basicCatalog]));
  const [surfaces, setSurfaces] = useState(() =>
    Array.from(processor.model.surfacesMap.values()),
  );
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });

  // Keep the surface list in sync with the processor.
  useEffect(() => {
    const sync = () =>
      setSurfaces(Array.from(processor.model.surfacesMap.values()));
    const createdSub = processor.onSurfaceCreated(sync);
    const deletedSub = processor.onSurfaceDeleted(sync);
    return () => {
      createdSub.unsubscribe();
      deletedSub.unsubscribe();
    };
  }, [processor]);

  // Load the messages once. In development React runs effects twice; the
  // `cancelled` flag makes sure only one createSurface reaches the processor.
  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      try {
        const response = await fetch("/api/dashboard");
        if (!response.ok) {
          throw new Error(`The API returned ${response.status}.`);
        }
        const body = await response.json();
        if (cancelled) return;
        processor.processMessages(body.messages);
        setLoad({ kind: "ready" });
      } catch (error) {
        if (cancelled) return;
        const message =
          error instanceof Error ? error.message : "Something went wrong.";
        setLoad({ kind: "error", message });
      }
    }

    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [processor]);

  return (
    <main className="mx-auto max-w-3xl p-6">
      {load.kind === "loading" && <p>Loading dashboard…</p>}
      {load.kind === "error" && (
        <p role="alert">
          Couldn&apos;t load the dashboard: {load.message} Is the backend
          running?
        </p>
      )}
      <MarkdownContext.Provider value={renderMarkdown}>
        {surfaces.map((surface) => (
          <A2uiSurface key={surface.id} surface={surface} />
        ))}
      </MarkdownContext.Provider>
    </main>
  );
}
