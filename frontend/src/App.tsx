import { useMemo, useState } from "react";

import { AskInboxPage } from "./pages/AskInboxPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GmailPage } from "./pages/GmailPage";
import { OnboardingPage } from "./pages/OnboardingPage";

type TabKey = "onboarding" | "dashboard" | "ask" | "gmail";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "dashboard", label: "Dashboard" },
  { key: "ask", label: "Ask Inbox" },
  { key: "gmail", label: "Gmail" },
  { key: "onboarding", label: "Onboarding" }
];

export function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("dashboard");

  const panel = useMemo(() => {
    switch (activeTab) {
      case "onboarding":
        return <OnboardingPage />;
      case "dashboard":
        return <DashboardPage onNavigate={setActiveTab} />;
      case "ask":
        return <AskInboxPage />;
      case "gmail":
        return <GmailPage />;
      default:
        return null;
    }
  }, [activeTab]);

  return (
    <div className="app-shell">
      <div className="app-frame">
        <header className="topbar">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              ✉
            </span>
            <div className="brand-text">
              <strong>Inbox Intelligence</strong>
              <span>AI Email Copilot</span>
            </div>
          </div>

          <nav className="topnav" aria-label="Primary">
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

          <div className="topbar-status">
            <span className="status-chip ready">AI Ready</span>
            <button type="button" className="avatar-chip" onClick={() => setActiveTab("onboarding")}>
              EW
            </button>
          </div>
        </header>

        <main className="workspace">{panel}</main>
      </div>
    </div>
  );
}
