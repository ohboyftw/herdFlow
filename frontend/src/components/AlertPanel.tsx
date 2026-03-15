import { useState } from 'react';
import type { Alert, Severity } from '../types/generated';

interface AlertPanelProps {
  alerts: Alert[];
}

const SEVERITY_STYLES: Record<Severity, { container: string; badge: string; label: string }> = {
  info: {
    container: 'bg-blue-900/30 border-blue-500',
    badge: 'bg-blue-500/20 text-blue-300',
    label: 'INFO',
  },
  warning: {
    container: 'bg-amber-900/30 border-amber-500',
    badge: 'bg-amber-500/20 text-amber-300',
    label: 'WARNING',
  },
  alert: {
    container: 'bg-orange-900/30 border-orange-500',
    badge: 'bg-orange-500/20 text-orange-300',
    label: 'ALERT',
  },
  critical: {
    container: 'bg-red-900/30 border-red-500 animate-pulse',
    badge: 'bg-red-500/20 text-red-300',
    label: 'CRITICAL',
  },
};

function formatRelativeTime(ts: string | undefined): string {
  if (!ts) return '';
  try {
    const diffMs = Date.now() - new Date(ts).getTime();
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 5) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffHr = Math.floor(diffMin / 60);
    return `${diffHr}h ago`;
  } catch {
    return ts;
  }
}

export function AlertPanel({ alerts }: AlertPanelProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const dismiss = (id: string) =>
    setDismissed((prev) => new Set(prev).add(id));

  const visible = alerts
    .slice(-10)
    .reverse()
    .filter((a) => {
      const key = a.id ?? `${a.type}-${a.entity_track_id}-${a.timestamp}`;
      return !dismissed.has(key);
    });

  const activeCount = alerts.filter((a) => {
    const key = a.id ?? `${a.type}-${a.entity_track_id}-${a.timestamp}`;
    return !dismissed.has(key);
  }).length;

  return (
    <div className="flex flex-col border-b border-slate-700 bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-sm font-semibold text-slate-200">Alerts</span>
        {activeCount > 0 && (
          <span className="text-xs bg-red-600/80 text-white px-1.5 py-0.5 rounded-full">
            {activeCount}
          </span>
        )}
      </div>

      {/* Alert cards */}
      <div className="flex flex-col gap-2 px-4 pb-3 max-h-64 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="text-xs text-slate-500 text-center py-3">No active alerts</p>
        ) : (
          visible.map((alert) => {
            const key = alert.id ?? `${alert.type}-${alert.entity_track_id}-${alert.timestamp}`;
            const s = SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info;
            return (
              <div
                key={key}
                className={`rounded-md border px-3 py-2 ${s.container}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 ${s.badge}`}>
                      {s.label}
                    </span>
                    <span className="text-xs font-medium text-slate-200 truncate">{alert.type}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] text-slate-400">
                      {formatRelativeTime(alert.timestamp)}
                    </span>
                    <button
                      onClick={() => dismiss(key)}
                      className="text-slate-500 hover:text-slate-300 transition-colors leading-none"
                      aria-label="Dismiss alert"
                      title="Dismiss"
                    >
                      <svg
                        className="w-3 h-3"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>
                <p className="text-xs text-slate-300 leading-snug">{alert.description}</p>
                <p className="text-[10px] text-slate-500 mt-1">Track: {alert.entity_track_id}</p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
