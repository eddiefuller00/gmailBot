import { useMemo, useState } from "react";

import { AskInboxPage } from "./pages/AskInboxPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GmailPage } from "./pages/GmailPage";
import { IngestPage } from "./pages/IngestPage";
import { OnboardingPage } from "./pages/OnboardingPage";

type TabKey = "onboarding" | "dashboard" | "ask" | "gmail" | "ingest";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "onboarding", label: "Onboarding" },
  { key: "dashboard", label: "Dashboard" },
  { key: "ask", label: "Ask Inbox" },
  { key: "gmail", label: "Gmail" },
  { key: "ingest", label: "Data Ingest" }
];

export function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("onboarding");

  const panel = useMemo(() => {
    switch (activeTab) {
      case "onboarding":
        return <OnboardingPage />;
      case "dashboard":
        return <DashboardPage />;
      case "ask":
        return <AskInboxPage />;
      case "gmail":
        return <GmailPage />;
      case "ingest":
        return <IngestPage />;
      default:
        return null;
    }
  }, [activeTab]);

  return (
    <div className="app-shell">
      <header className="hero">
        <p className="eyebrow">Inbox Intelligence</p>
        <h1>AI Email Copilot</h1>
        <p>
          Personalized inbox ranking, deadline/event extraction, and natural-language Q&A over
          your emails.
        </p>
      </header>

      <nav className="tab-bar" aria-label="Primary">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={tab.key === activeTab ? "active" : ""}
            onClick={() => setActiveTab(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main>{panel}</main>
    </div>
  );
}
