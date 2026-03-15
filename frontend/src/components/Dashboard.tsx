import type { SceneGraph } from '../types/generated';

interface DashboardProps {
  sceneGraph: SceneGraph | null;
}

interface StatCardProps {
  label: string;
  value: number | string;
  sub?: string;
  highlight?: boolean;
}

function StatCard({ label, value, sub, highlight = false }: StatCardProps) {
  return (
    <div className="flex flex-col gap-0.5 bg-slate-800/60 rounded-md px-3 py-2">
      <span className="text-[10px] text-slate-400 uppercase tracking-wider">{label}</span>
      <span className={`text-xl font-bold ${highlight ? 'text-red-400' : 'text-slate-100'}`}>
        {value}
      </span>
      {sub && <span className="text-[10px] text-slate-500">{sub}</span>}
    </div>
  );
}

interface BehaviorBarProps {
  label: string;
  count: number;
  total: number;
  color: string;
}

function BehaviorBar({ label, count, total, color }: BehaviorBarProps) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-slate-400 w-16 shrink-0">{label}</span>
      <div className="flex-1 bg-slate-700 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] text-slate-400 w-8 text-right">{count}</span>
    </div>
  );
}

// Mock data shown before LiveKit data channel delivers real SceneGraph
const MOCK_SCENE: SceneGraph = {
  timestamp: new Date().toISOString(),
  frame_id: 0,
  herd_summary: {
    total_visible: 24,
    standing: 10,
    lying: 6,
    walking: 4,
    feeding: 3,
    drinking: 1,
  },
  tracked_entities: [],
  zones: {
    pasture_a: { occupancy: 10 },
    pasture_b: { occupancy: 8 },
    water_station: { occupancy: 6 },
  },
  active_alerts: [],
};

export function Dashboard({ sceneGraph }: DashboardProps) {
  const data = sceneGraph ?? MOCK_SCENE;
  const { herd_summary, zones, active_alerts } = data;
  const total = herd_summary.total_visible;

  const behaviors: Array<{ label: string; key: keyof typeof herd_summary; color: string }> = [
    { label: 'Standing', key: 'standing', color: 'bg-sky-500' },
    { label: 'Lying', key: 'lying', color: 'bg-violet-500' },
    { label: 'Walking', key: 'walking', color: 'bg-emerald-500' },
    { label: 'Feeding', key: 'feeding', color: 'bg-amber-500' },
    { label: 'Drinking', key: 'drinking', color: 'bg-cyan-500' },
  ];

  return (
    <div className="flex flex-col gap-3 px-4 py-4 bg-slate-900 flex-1">
      <span className="text-sm font-semibold text-slate-200">Herd Summary</span>

      {sceneGraph === null && (
        <p className="text-[10px] text-slate-500 -mt-1">Showing demo data — awaiting live feed</p>
      )}

      {/* Top stats */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="Total Visible" value={total} sub="animals tracked" />
        <StatCard
          label="Active Alerts"
          value={active_alerts.length}
          sub="requiring attention"
          highlight={active_alerts.length > 0}
        />
      </div>

      {/* Behavior breakdown */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] text-slate-400 uppercase tracking-wider">Behaviors</span>
        {behaviors.map(({ label, key, color }) => (
          <BehaviorBar
            key={key}
            label={label}
            count={herd_summary[key] as number}
            total={total}
            color={color}
          />
        ))}
      </div>

      {/* Zone occupancy */}
      {Object.keys(zones).length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Zone Occupancy</span>
          {Object.entries(zones).map(([zone, { occupancy }]) => (
            <BehaviorBar
              key={zone}
              label={zone.replace(/_/g, ' ')}
              count={occupancy}
              total={total}
              color="bg-teal-500"
            />
          ))}
        </div>
      )}
    </div>
  );
}
