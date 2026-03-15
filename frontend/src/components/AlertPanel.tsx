import type { Alert, Severity } from '../types/generated';

interface AlertPanelProps {
  alerts: Alert[];
}

const SEVERITY_STYLES: Record<Severity, { container: string; badge: string; label: string }> = {
  info: {
    container: 'bg-blue-900/50 border-blue-500',
    badge: 'bg-blue-500/20 text-blue-300',
    label: 'INFO',
  },
  warning: {
    container: 'bg-yellow-900/50 border-yellow-500',
    badge: 'bg-yellow-500/20 text-yellow-300',
    label: 'WARNING',
  },
  alert: {
    container: 'bg-orange-900/50 border-orange-500',
    badge: 'bg-orange-500/20 text-orange-300',
    label: 'ALERT',
  },
  critical: {
    container: 'bg-red-900/50 border-red-500',
    badge: 'bg-red-500/20 text-red-300',
    label: 'CRITICAL',
  },
};

function formatTimestamp(ts: string | undefined): string {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return ts;
  }
}

export function AlertPanel({ alerts }: AlertPanelProps) {
  const visible = alerts.slice(-10).reverse();
  const styles = SEVERITY_STYLES;

  return (
    <div className="flex flex-col border-b border-slate-700 bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-sm font-semibold text-slate-200">Alerts</span>
        {alerts.length > 0 && (
          <span className="text-xs bg-red-600/80 text-white px-1.5 py-0.5 rounded-full">
            {alerts.length}
          </span>
        )}
      </div>

      {/* Alert cards */}
      <div className="flex flex-col gap-2 px-4 pb-3 max-h-64 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="text-xs text-slate-500 text-center py-3">No active alerts</p>
        ) : (
          visible.map((alert) => {
            const s = styles[alert.severity] ?? styles.info;
            return (
              <div
                key={alert.id ?? `${alert.type}-${alert.entity_track_id}-${alert.timestamp}`}
                className={`rounded-md border px-3 py-2 ${s.container}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${s.badge}`}>
                      {s.label}
                    </span>
                    <span className="text-xs font-medium text-slate-200">{alert.type}</span>
                  </div>
                  <span className="text-[10px] text-slate-400 shrink-0">
                    {formatTimestamp(alert.timestamp)}
                  </span>
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
