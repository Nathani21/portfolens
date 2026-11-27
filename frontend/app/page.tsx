"use client";

import dynamic from "next/dynamic";

// A2UI draws components in the browser, so skip server rendering for it.
const Dashboard = dynamic(() => import("./dashboard"), {
  ssr: false,
  loading: () => <p className="p-6">Loading dashboard…</p>,
});

export default function Home() {
  return <Dashboard />;
}
