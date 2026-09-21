// Erpis — Shared UI Components
// Requires React on window, FontAwesome loaded via CDN

const ACCENT_COLORS = {
  emerald: { main: 'oklch(0.70 0.17 162)', dim: 'oklch(0.70 0.17 162 / 0.15)', text: 'oklch(0.70 0.17 162)' },
  blue:    { main: 'oklch(0.65 0.17 245)', dim: 'oklch(0.65 0.17 245 / 0.15)', text: 'oklch(0.65 0.17 245)' },
  amber:   { main: 'oklch(0.78 0.17 75)',  dim: 'oklch(0.78 0.17 75 / 0.15)',  text: 'oklch(0.78 0.17 75)' },
  purple:  { main: 'oklch(0.68 0.17 300)', dim: 'oklch(0.68 0.17 300 / 0.15)', text: 'oklch(0.68 0.17 300)' },
  red:     { main: 'oklch(0.62 0.20 25)',  dim: 'oklch(0.62 0.20 25 / 0.15)',  text: 'oklch(0.62 0.20 25)' },
};

// Theme tokens
const T = {
  bg:       '#0d1117',
  surface:  '#161b22',
  surface2: '#21262d',
  border:   '#30363d',
  text:     '#e6edf3',
  muted:    '#8b949e',
  mutedDim: '#484f58',
};

// ── KPI Card ────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon, color = 'emerald', accent }) {
  const ac = ACCENT_COLORS[color] || ACCENT_COLORS.emerald;
  const [hov, setHov] = React.useState(false);
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: T.surface,
        border: `1px solid ${hov ? ac.main : T.border}`,
        borderRadius: 12,
        padding: '14px 18px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        transition: 'border-color 0.2s, transform 0.2s, box-shadow 0.2s',
        transform: hov ? 'translateY(-2px)' : 'none',
        boxShadow: hov ? `0 8px 24px rgba(0,0,0,0.25)` : '0 1px 4px rgba(0,0,0,0.2)',
        cursor: 'default',
        flex: 1,
        minWidth: 0,
      }}
    >
      <div style={{
        width: 48, height: 48, borderRadius: 12,
        background: ac.dim, display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <i className={`fas ${icon}`} style={{ color: ac.main, fontSize: 20 }}></i>
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 11, color: T.muted, marginBottom: 2, whiteSpace: 'nowrap' }}>{label}</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: T.text, letterSpacing: '-0.6px', whiteSpace: 'nowrap' }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: T.muted, marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}

// ── Priority Stack (action-oriented summary) ───────────────────────────────
function PriorityStack({ items = [] }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 16, alignItems: 'stretch', flexWrap: 'wrap' }}>
      {items.map((it, i) => (
        <div key={i} style={{
          flex: '0 1 260px', display: 'flex', alignItems: 'center', gap: 12,
          background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: '12px 14px'
        }}>
          <div style={{ width: 10, height: 40, borderRadius: 6, background: it.color || ACCENT_COLORS.amber.main, flexShrink: 0 }}></div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 4 }}>{it.title}</div>
            <div style={{ fontSize: 12, color: T.muted, marginBottom: 8 }}>{it.description}</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Btn variant="outline" small onClick={it.onView}>View</Btn>
              <Btn variant="primary" small onClick={it.onAct} accent={it.color}>{it.action || 'Act'}</Btn>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Roadmap / Recommendations (scaffold) ─────────────────────────────────────
function Roadmap({ items = [] }) {
  if (!items || items.length === 0) return (
    <div style={{ padding: 24, color: T.muted }}>No roadmap items yet.</div>
  );
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {items.map((it, i) => (
        <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: 12 }}>
          <div style={{ width: 8, height: 48, borderRadius: 6, background: it.status === 'In Progress' ? ACCENT_COLORS.blue.main : ACCENT_COLORS.emerald.main }}></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{it.title}</div>
              <div style={{ fontSize: 12, color: T.muted }}>{it.status} · {it.progress}%</div>
            </div>
            <div style={{ marginTop: 6, fontSize: 13, color: T.muted }}>{it.recommendation}</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn variant="outline" small>Details</Btn>
            <Btn variant="primary" small>Recommend</Btn>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Badge ────────────────────────────────────────────────────────────────────
function Badge({ status }) {
  const map = {
    active:    { label: 'Active',    color: ACCENT_COLORS.emerald.main },
    on_leave:  { label: 'On Leave',  color: ACCENT_COLORS.amber.main },
    inactive:  { label: 'Inactive',  color: T.muted },
    terminated:{ label: 'Terminated',color: ACCENT_COLORS.red.main },
    in_progress:{ label: 'In Progress', color: ACCENT_COLORS.blue.main },
    completed: { label: 'Completed', color: ACCENT_COLORS.emerald.main },
    on_hold:   { label: 'On Hold',   color: ACCENT_COLORS.amber.main },
    cancelled: { label: 'Cancelled', color: ACCENT_COLORS.red.main },
    pending:   { label: 'Pending',   color: ACCENT_COLORS.amber.main },
    shipped:   { label: 'Shipped',   color: ACCENT_COLORS.blue.main },
    delivered: { label: 'Delivered', color: ACCENT_COLORS.emerald.main },
  };
  const cfg = map[status] || { label: status, color: T.muted };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontSize: 11, fontWeight: 600, letterSpacing: '0.03em',
      padding: '3px 10px', borderRadius: 20,
      background: cfg.color + '22', color: cfg.color,
      border: `1px solid ${cfg.color}44`,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: cfg.color, flexShrink: 0 }}></span>
      {cfg.label}
    </span>
  );
}

// ── Avatar ───────────────────────────────────────────────────────────────────
function Avatar({ initials, size = 34 }) {
  const colors = ['#1a6b45','#1a4a6b','#6b3a1a','#4a1a6b','#1a5a6b'];
  const idx = (initials.charCodeAt(0) + (initials.charCodeAt(1) || 0)) % colors.length;
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: colors[idx], color: '#fff',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.34, fontWeight: 700, flexShrink: 0, letterSpacing: '0.02em',
    }}>{initials}</div>
  );
}

// ── Progress Bar ─────────────────────────────────────────────────────────────
function ProgressBar({ pct }) {
  const color = pct === 100 ? ACCENT_COLORS.emerald.main : pct >= 50 ? ACCENT_COLORS.blue.main : ACCENT_COLORS.amber.main;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 5, borderRadius: 3, background: T.surface2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.6s ease' }}></div>
      </div>
      <span style={{ fontSize: 11, color: T.muted, minWidth: 28, textAlign: 'right' }}>{pct}%</span>
    </div>
  );
}

// ── Card ─────────────────────────────────────────────────────────────────────
function Card({ children, style }) {
  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 12, overflow: 'hidden', ...style,
    }}>{children}</div>
  );
}

// ── Card Header ───────────────────────────────────────────────────────────────
function CardHeader({ icon, iconColor, title, action, actionLabel }) {
  return (
    <div style={{
      padding: '14px 20px', borderBottom: `1px solid ${T.border}`,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: T.surface,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {icon && <i className={`fas ${icon}`} style={{ color: iconColor || T.muted, fontSize: 14 }}></i>}
        <span style={{ fontWeight: 600, fontSize: 14, color: T.text }}>{title}</span>
      </div>
      {action && (
        <button onClick={action} style={{
          fontSize: 12, color: T.muted, background: 'none', border: `1px solid ${T.border}`,
          borderRadius: 6, padding: '4px 10px', cursor: 'pointer',
          transition: 'color 0.15s, border-color 0.15s',
        }}
          onMouseEnter={e => { e.target.style.color = T.text; e.target.style.borderColor = T.mutedDim; }}
          onMouseLeave={e => { e.target.style.color = T.muted; e.target.style.borderColor = T.border; }}
        >{actionLabel || 'View all'}</button>
      )}
    </div>
  );
}

// ── Table ─────────────────────────────────────────────────────────────────────
function Table({ cols, rows, emptyMsg = 'No data.' }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            {cols.map((c, i) => (
              <th key={i} style={{
                padding: '10px 16px', textAlign: c.right ? 'right' : 'left',
                color: T.muted, fontWeight: 600, fontSize: 11, letterSpacing: '0.05em',
                textTransform: 'uppercase', whiteSpace: 'nowrap',
              }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={cols.length} style={{ padding: 32, textAlign: 'center', color: T.muted }}>{emptyMsg}</td></tr>
          ) : rows.map((row, ri) => (
            <tr key={ri} style={{ borderBottom: `1px solid ${T.border}22`, transition: 'background 0.15s' }}
              onMouseEnter={e => e.currentTarget.style.background = T.surface2}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {cols.map((c, ci) => (
                <td key={ci} style={{
                  padding: '12px 16px', color: T.text,
                  textAlign: c.right ? 'right' : 'left',
                }}>{c.render ? c.render(row) : row[c.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Btn ───────────────────────────────────────────────────────────────────────
function Btn({ children, variant = 'primary', icon, onClick, small, accent }) {
  const [hov, setHov] = React.useState(false);
  const acMain = accent || ACCENT_COLORS.emerald.main;
  const acDim  = accent ? accent + '22' : ACCENT_COLORS.emerald.dim;
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    borderRadius: 8, fontWeight: 600, cursor: 'pointer',
    fontSize: small ? 12 : 13, padding: small ? '5px 12px' : '8px 16px',
    border: '1px solid transparent', transition: 'all 0.15s',
  };
  let style = {};
  if (variant === 'primary') {
    style = { ...base, background: hov ? acMain + 'cc' : acMain, color: '#0d1117', borderColor: acMain };
  } else if (variant === 'ghost') {
    style = { ...base, background: hov ? T.surface2 : 'transparent', color: T.muted, borderColor: hov ? T.border : 'transparent' };
  } else if (variant === 'outline') {
    style = { ...base, background: hov ? acDim : 'transparent', color: acMain, borderColor: hov ? acMain + '66' : T.border };
  } else {
    // fallback to outline-like
    style = { ...base, background: hov ? acDim : 'transparent', color: acMain, borderColor: hov ? acMain + '66' : T.border };
  }
  return (
    <button style={style} onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
      {icon && <i className={`fas ${icon}`}></i>}
      {children}
    </button>
  );
}

// ── Page Header ───────────────────────────────────────────────────────────────
function PageHeader({ title, icon, children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 38, height: 38, borderRadius: 10,
          background: ACCENT_COLORS.emerald.dim,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <i className={`fas ${icon}`} style={{ color: ACCENT_COLORS.emerald.main, fontSize: 16 }}></i>
        </div>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: T.text, letterSpacing: '-0.4px' }}>{title}</h1>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>{children}</div>
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: 'dashboard',   label: 'Dashboard',   icon: 'fa-home' },
  { id: 'employees',   label: 'Employees',   icon: 'fa-users' },
  { id: 'finance',     label: 'Finance',     icon: 'fa-wallet' },
  { id: 'hr',          label: 'HR',          icon: 'fa-user-tie' },
  { id: 'inventory',   label: 'Inventory',   icon: 'fa-boxes' },
  { id: 'meetings',    label: 'Meetings',    icon: 'fa-calendar-alt' },
  { id: 'marketplace', label: 'Marketplace', icon: 'fa-shopping-cart' },
];

function Sidebar({ active, onNav, collapsed }) {
  const acMain = ACCENT_COLORS.emerald.main;
  return (
    <aside style={{
      width: collapsed ? 64 : 220,
      minWidth: collapsed ? 64 : 220,
      background: '#080d12',
      borderRight: `1px solid ${T.border}`,
      display: 'flex', flexDirection: 'column',
      height: '100vh', position: 'sticky', top: 0,
      transition: 'width 0.25s ease, min-width 0.25s ease',
      overflow: 'hidden', flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{
        height: 60, display: 'flex', alignItems: 'center',
        padding: collapsed ? '0 16px' : '0 20px',
        borderBottom: `1px solid ${T.border}`,
        gap: 10,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: acMain, display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <i className="fas fa-bolt" style={{ color: '#0d1117', fontSize: 14 }}></i>
        </div>
        {!collapsed && <span style={{ fontWeight: 800, fontSize: 18, color: T.text, letterSpacing: '-0.5px' }}>Erpis</span>}
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV_ITEMS.map(item => {
          const isActive = active === item.id;
          return (
            <button key={item.id} onClick={() => onNav(item.id)} style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: collapsed ? '10px 0' : '10px 12px',
              borderRadius: 8, border: 'none', cursor: 'pointer',
              background: isActive ? acMain + '22' : 'transparent',
              color: isActive ? acMain : T.muted,
              width: '100%', textAlign: 'left',
              transition: 'background 0.15s, color 0.15s',
              justifyContent: collapsed ? 'center' : 'flex-start',
            }}
              onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.text; } }}
              onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = T.muted; } }}
            >
              <i className={`fas ${item.icon}`} style={{ fontSize: 15, flexShrink: 0, width: 18, textAlign: 'center' }}></i>
              {!collapsed && <span style={{ fontSize: 13.5, fontWeight: isActive ? 600 : 400 }}>{item.label}</span>}
              {isActive && !collapsed && <div style={{ marginLeft: 'auto', width: 4, height: 4, borderRadius: '50%', background: acMain }}></div>}
            </button>
          );
        })}
      </nav>

      {/* User */}
      <div style={{
        padding: collapsed ? '12px 8px' : '12px 16px',
        borderTop: `1px solid ${T.border}`,
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <Avatar initials="AD" size={32} />
        {!collapsed && (
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Amara Diallo</div>
            <div style={{ fontSize: 11, color: T.muted }}>Admin</div>
          </div>
        )}
      </div>
    </aside>
  );
}

// ── Top Bar ───────────────────────────────────────────────────────────────────
function TopBar({ page, onToggleSidebar }) {
  const acMain = ACCENT_COLORS.emerald.main;
  return (
    <div style={{
      height: 60, display: 'flex', alignItems: 'center',
      padding: '0 24px', borderBottom: `1px solid ${T.border}`,
      background: T.surface, gap: 16, flexShrink: 0,
    }}>
      <button onClick={onToggleSidebar} style={{
        background: 'none', border: 'none', color: T.muted, cursor: 'pointer',
        fontSize: 16, padding: 4, borderRadius: 6, transition: 'color 0.15s',
      }}
        onMouseEnter={e => e.target.style.color = T.text}
        onMouseLeave={e => e.target.style.color = T.muted}
      >
        <i className="fas fa-bars"></i>
      </button>

      {/* Search */}
      <div style={{
        flex: 1, maxWidth: 340,
        display: 'flex', alignItems: 'center', gap: 8,
        background: T.surface2, border: `1px solid ${T.border}`,
        borderRadius: 8, padding: '7px 12px',
      }}>
        <i className="fas fa-search" style={{ color: T.mutedDim, fontSize: 13 }}></i>
        <input placeholder="Search…" style={{
          background: 'none', border: 'none', outline: 'none',
          color: T.text, fontSize: 13, width: '100%',
        }} />
        <span style={{
          fontSize: 10, color: T.mutedDim, border: `1px solid ${T.border}`,
          borderRadius: 4, padding: '1px 5px', letterSpacing: '0.05em',
        }}>⌘K</span>
      </div>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Notifications */}
        <button style={{
          width: 36, height: 36, borderRadius: 8, background: T.surface2,
          border: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', position: 'relative', color: T.muted,
        }}>
          <i className="fas fa-bell" style={{ fontSize: 14 }}></i>
          <span style={{
            position: 'absolute', top: 6, right: 6, width: 7, height: 7,
            background: ACCENT_COLORS.red.main, borderRadius: '50%',
            border: `1.5px solid ${T.surface}`,
          }}></span>
        </button>
        {/* Date */}
        <div style={{ fontSize: 12, color: T.muted, paddingLeft: 8 }}>
          <i className="fas fa-calendar-alt" style={{ marginRight: 6 }}></i>
          Apr 29, 2026
        </div>
      </div>
    </div>
  );
}

// Export everything
Object.assign(window, {
  T, ACCENT_COLORS,
  KpiCard, Badge, Avatar, ProgressBar,
  Card, CardHeader, Table, Btn, PageHeader,
  Sidebar, TopBar,
  PriorityStack,
  Roadmap,
});
