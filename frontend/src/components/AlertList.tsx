import type { AlertItem } from "../api/types";

interface AlertListProps {
  alerts: AlertItem[];
}

export function AlertList({ alerts }: AlertListProps) {
  return (
    <section className="panel">
      <header className="panel-header">
        <h3>Smart Alerts</h3>
        <span className="pill">{alerts.length}</span>
      </header>
      <ul className="alert-list" aria-label="Smart Alerts">
        {alerts.map((alert, index) => (
          <li key={`${alert.message}-${index}`} className={`alert ${alert.severity}`}>
            {alert.message}
          </li>
        ))}
      </ul>
    </section>
  );
}
