// Erpis — Screen Components
// Depends on: window.T, window.ACCENT_COLORS, window.ErpisData, and all UI primitives

// ── Dashboard ────────────────────────────────────────────────────────────────
function ScreenDashboard() {
  const d = ErpisData.dashboard;
  return (
    <div>
      <PageHeader title="Dashboard" icon="fa-home">
        <Btn variant="outline" icon="fa-download" small>Export</Btn>
        <Btn variant="primary" icon="fa-plus" small>Quick Add</Btn>
      </PageHeader>

      {/* Priority / Action stack (high-level) */}
      <PriorityStack items={d.priority} />

      {/* KPI Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {d.stats.map((s, i) => <KpiCard key={i} {...s} />)}
      </div>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

        {/* Recent Projects */}
        <Card>
          <CardHeader icon="fa-project-diagram" iconColor={ACCENT_COLORS.blue.main} title="Recent Projects" actionLabel="View all" action={() => {}} />
          <Table
            cols={[
              { label: 'Project', key: 'name' },
              { label: 'Status', render: r => <Badge status={r.status} /> },
              { label: 'Progress', render: r => <ProgressBar pct={r.progress} /> },
            ]}
            rows={d.recentProjects}
          />
        </Card>

        {/* Recent Employees */}
        <Card>
          <CardHeader icon="fa-users" iconColor={ACCENT_COLORS.emerald.main} title="Recent Employees" actionLabel="View all" action={() => {}} />
          <Table
            cols={[
              { label: 'Employee', render: r => (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Avatar initials={r.initials} />
                  <div>
                    <div style={{ fontWeight: 600, color: T.text, fontSize: 13 }}>{r.name}</div>
                    <div style={{ fontSize: 11, color: T.muted }}>{r.id}</div>
                  </div>
                </div>
              )},
              { label: 'Dept', render: r => <span style={{ fontSize: 12, color: T.muted }}>{r.dept}</span> },
              { label: 'Status', render: r => <Badge status={r.status} /> },
            ]}
            rows={d.recentEmployees}
          />
        </Card>

        {/* Finance Summary */}
        <Card style={{ gridColumn: '1 / -1' }}>
          <CardHeader icon="fa-wallet" iconColor={ACCENT_COLORS.purple.main} title="Finance — This Month" actionLabel="Open Finance" action={() => {}} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 0 }}>
            {[
              { label: 'Total Balance', value: 'FCFA 4,280,000', color: T.text },
              { label: 'Credits In', value: '+FCFA 480,000', color: ACCENT_COLORS.emerald.main },
              { label: 'Debits Out', value: '-FCFA 200,000', color: ACCENT_COLORS.red.main },
            ].map((f, i) => (
              <div key={i} style={{
                padding: '20px 24px',
                borderRight: i < 2 ? `1px solid ${T.border}` : 'none',
              }}>
                <div style={{ fontSize: 12, color: T.muted, marginBottom: 6 }}>{f.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: f.color }}>{f.value}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Roadmap / Recommendations */}
      <Card style={{ marginTop: 20 }}>
        <CardHeader icon="fa-flag" iconColor={ACCENT_COLORS.blue.main} title="Roadmap & Recommendations" actionLabel="View roadmap" action={() => {}} />
        <div style={{ padding: 18 }}>
          <Roadmap items={d.roadmap} />
        </div>
      </Card>
    </div>
  );
}

// ── Finance ──────────────────────────────────────────────────────────────────
function ScreenFinance() {
  const d = ErpisData.finance;
  return (
    <div>
      <PageHeader title="Finance" icon="fa-wallet">
        <Btn variant="outline" icon="fa-file-invoice-dollar" small>New Invoice</Btn>
        <Btn variant="primary" icon="fa-plus" small>New Transaction</Btn>
      </PageHeader>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {d.stats.map((s, i) => <KpiCard key={i} {...s} />)}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
        {/* Recent Transactions */}
        <Card>
          <CardHeader icon="fa-exchange-alt" title="Recent Transactions" actionLabel="View all" action={() => {}} />
          <Table
            cols={[
              { label: 'Date', render: r => <span style={{ color: T.muted, fontSize: 12 }}>{r.date}</span> },
              { label: 'Account', key: 'account' },
              { label: 'Description', render: r => <span style={{ color: T.muted }}>{r.description}</span> },
              { label: 'Credit', right: true, render: r => r.credit
                  ? <span style={{ color: ACCENT_COLORS.emerald.main, fontWeight: 600 }}>+{r.credit}</span>
                  : <span style={{ color: T.mutedDim }}>—</span>
              },
              { label: 'Debit', right: true, render: r => r.debit
                  ? <span style={{ color: ACCENT_COLORS.red.main, fontWeight: 600 }}>-{r.debit}</span>
                  : <span style={{ color: T.mutedDim }}>—</span>
              },
            ]}
            rows={d.transactions}
          />
        </Card>

        {/* Top Accounts */}
        <Card>
          <CardHeader icon="fa-university" title="Top Accounts" actionLabel="All" action={() => {}} />
          <div>
            {d.topAccounts.map((a, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '14px 18px',
                borderBottom: i < d.topAccounts.length - 1 ? `1px solid ${T.border}22` : 'none',
                transition: 'background 0.15s',
              }}
                onMouseEnter={e => e.currentTarget.style.background = T.surface2}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: ACCENT_COLORS.emerald.main, opacity: 0.7 }}></div>
                  <span style={{ fontSize: 13, color: T.text, fontWeight: 500 }}>{a.name}</span>
                </div>
                <span style={{ fontSize: 13, fontWeight: 700, color: ACCENT_COLORS.emerald.main }}>
                  {a.balance}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ── Employees ────────────────────────────────────────────────────────────────
function ScreenEmployees() {
  const [search, setSearch] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState('');
  const all = ErpisData.employees;
  const filtered = all.filter(e => {
    const q = search.toLowerCase();
    return (!q || e.name.toLowerCase().includes(q) || e.id.toLowerCase().includes(q) || e.email.toLowerCase().includes(q))
        && (!statusFilter || e.status === statusFilter);
  });

  const selectStyle = {
    background: T.surface2, border: `1px solid ${T.border}`,
    borderRadius: 8, padding: '7px 12px', color: T.text,
    fontSize: 13, outline: 'none', cursor: 'pointer',
  };

  return (
    <div>
      <PageHeader title="Employees" icon="fa-users">
        <Btn variant="outline" icon="fa-file-export" small>Export</Btn>
        <Btn variant="outline" icon="fa-file-import" small>Import</Btn>
        <Btn variant="primary" icon="fa-plus" small>Add Employee</Btn>
      </PageHeader>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        <KpiCard label="Total" value={String(all.length)} icon="fa-users" color="blue" />
        <KpiCard label="Active" value={String(all.filter(e => e.status === 'active').length)} icon="fa-user-check" color="emerald" />
        <KpiCard label="On Leave" value={String(all.filter(e => e.status === 'on_leave').length)} icon="fa-umbrella-beach" color="amber" />
        <KpiCard label="Inactive" value={String(all.filter(e => e.status === 'inactive').length)} icon="fa-user-slash" color="red" />
      </div>

      {/* Filter bar */}
      <div style={{
        background: T.surface, border: `1px solid ${T.border}`,
        borderRadius: 12, padding: '14px 20px', marginBottom: 20,
        display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 12px', flex: '1 1 220px' }}>
          <i className="fas fa-search" style={{ color: T.mutedDim, fontSize: 13 }}></i>
          <input
            placeholder="Search name, ID, email…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ background: 'none', border: 'none', outline: 'none', color: T.text, fontSize: 13, width: '100%' }}
          />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={selectStyle}>
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="on_leave">On Leave</option>
          <option value="inactive">Inactive</option>
        </select>
        <select style={selectStyle}>
          <option value="">All Departments</option>
          <option>Engineering</option>
          <option>Finance</option>
          <option>HR</option>
          <option>Sales</option>
          <option>Marketing</option>
        </select>
        {(search || statusFilter) && (
          <Btn variant="ghost" icon="fa-times" small onClick={() => { setSearch(''); setStatusFilter(''); }}>Clear</Btn>
        )}
      </div>

      <Card>
        <Table
          cols={[
            { label: 'Employee', render: r => (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <Avatar initials={r.initials} />
                <div>
                  <div style={{ fontWeight: 600, color: T.text }}>{r.name}</div>
                  <div style={{ fontSize: 11, color: T.muted }}>{r.id} · {r.email}</div>
                </div>
              </div>
            )},
            { label: 'Department', render: r => (
              <span style={{ fontSize: 12, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6, padding: '3px 8px', color: T.muted }}>{r.dept}</span>
            )},
            { label: 'Role', render: r => (
              <span style={{ fontSize: 12, color: T.muted }}>{r.role}</span>
            )},
            { label: 'Status', render: r => <Badge status={r.status} /> },
            { label: 'Salary', right: true, render: r => <span style={{ fontFamily: 'monospace', fontSize: 13 }}>FCFA {r.salary}</span> },
            { label: 'Joined', render: r => <span style={{ fontSize: 12, color: T.muted }}>{r.joined}</span> },
            { label: '', render: r => (
              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                {['fa-eye','fa-edit','fa-trash'].map((ic, i) => (
                  <button key={i} style={{
                    width: 28, height: 28, borderRadius: 6, background: T.surface2,
                    border: `1px solid ${T.border}`, color: T.muted, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12,
                    transition: 'color 0.15s, border-color 0.15s',
                  }}
                    onMouseEnter={e => { e.currentTarget.style.color = T.text; e.currentTarget.style.borderColor = T.mutedDim; }}
                    onMouseLeave={e => { e.currentTarget.style.color = T.muted; e.currentTarget.style.borderColor = T.border; }}
                  >
                    <i className={`fas ${ic}`}></i>
                  </button>
                ))}
              </div>
            )},
          ]}
          rows={filtered}
          emptyMsg="No employees match your filters."
        />
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: T.muted }}>{filtered.length} employee{filtered.length !== 1 ? 's' : ''}</span>
          <Btn variant="outline" icon="fa-sitemap" small>Departments</Btn>
        </div>
      </Card>
    </div>
  );
}

// ── HR ───────────────────────────────────────────────────────────────────────
function ScreenHR() {
  const d = ErpisData.hr;
  const [tab, setTab] = React.useState('leaves');
  const tabs = [
    { id: 'leaves', label: 'Leave Requests' },
    { id: 'payroll', label: 'Payroll' },
    { id: 'performance', label: 'Performance' },
    { id: 'training', label: 'Training' },
  ];

  return (
    <div>
      <PageHeader title="HR" icon="fa-user-tie">
        <Btn variant="outline" icon="fa-calendar-plus" small>New Leave</Btn>
        <Btn variant="primary" icon="fa-plus" small>Quick Actions</Btn>
      </PageHeader>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {d.stats.map((s, i) => <KpiCard key={i} {...s} />)}
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: 4, width: 'fit-content' }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '7px 16px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 13,
            background: tab === t.id ? T.surface2 : 'transparent',
            color: tab === t.id ? T.text : T.muted,
            fontWeight: tab === t.id ? 600 : 400,
            transition: 'all 0.15s',
          }}>{t.label}</button>
        ))}
      </div>

      {tab === 'leaves' && (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20 }}>
          {/* Pending */}
          <Card>
            <CardHeader icon="fa-clock" iconColor={ACCENT_COLORS.amber.main} title="Pending Requests" />
            <div>
              {d.pendingLeaves.map((lv, i) => (
                <div key={i} style={{
                  padding: '14px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  borderBottom: i < d.pendingLeaves.length - 1 ? `1px solid ${T.border}22` : 'none',
                  transition: 'background 0.15s',
                }}
                  onMouseEnter={e => e.currentTarget.style.background = T.surface2}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Avatar initials={lv.name.split(' ').map(n => n[0]).join('')} size={34} />
                    <div>
                      <div style={{ fontWeight: 600, color: T.text, fontSize: 13 }}>{lv.name}</div>
                      <div style={{ fontSize: 11, color: T.muted }}>{lv.type} · {lv.from} → {lv.to} ({lv.days}d)</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button style={{ padding: '5px 12px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, background: ACCENT_COLORS.emerald.dim, color: ACCENT_COLORS.emerald.main }}>
                      <i className="fas fa-check me-1"></i> Approve
                    </button>
                    <button style={{ padding: '5px 12px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, background: ACCENT_COLORS.red.dim, color: ACCENT_COLORS.red.main }}>
                      <i className="fas fa-times"></i> Deny
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Currently on leave */}
            <Card>
              <CardHeader icon="fa-umbrella-beach" iconColor={ACCENT_COLORS.blue.main} title="On Leave Now" />
              <div>
                {d.onLeave.map((lv, i) => (
                  <div key={i} style={{
                    padding: '12px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    borderBottom: i < d.onLeave.length - 1 ? `1px solid ${T.border}22` : 'none',
                  }}>
                    <span style={{ fontSize: 13, fontWeight: 500, color: T.text }}>{lv.name}</span>
                    <span style={{ fontSize: 11, color: T.muted }}>returns {lv.returns}</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* Upcoming */}
            <Card>
              <CardHeader icon="fa-calendar-alt" iconColor={ACCENT_COLORS.purple.main} title="Upcoming (30 days)" />
              <div>
                {d.upcomingLeaves.map((lv, i) => (
                  <div key={i} style={{
                    padding: '12px 18px',
                    borderBottom: i < d.upcomingLeaves.length - 1 ? `1px solid ${T.border}22` : 'none',
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: T.text }}>{lv.name}</div>
                    <div style={{ fontSize: 11, color: T.muted }}>{lv.type} · {lv.from} → {lv.to}</div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}

      {tab !== 'leaves' && (
        <Card>
          <div style={{ padding: 48, textAlign: 'center', color: T.muted }}>
            <i className="fas fa-tools" style={{ fontSize: 32, marginBottom: 12, display: 'block', opacity: 0.4 }}></i>
            <div style={{ fontWeight: 600, marginBottom: 4, color: T.text }}>{tabs.find(t => t.id === tab)?.label}</div>
            <div style={{ fontSize: 13 }}>This section is available in the full build.</div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ── Inventory ────────────────────────────────────────────────────────────────
function ScreenInventory() {
  const d = ErpisData.inventory;
  return (
    <div>
      <PageHeader title="Inventory" icon="fa-boxes">
        <Btn variant="outline" icon="fa-file-import" small>Import</Btn>
        <Btn variant="outline" icon="fa-tags" small>Categories</Btn>
        <Btn variant="primary" icon="fa-plus" small>Add Stock</Btn>
      </PageHeader>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {d.stats.map((s, i) => <KpiCard key={i} {...s} />)}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Low Stock Alerts */}
        <Card>
          <CardHeader icon="fa-exclamation-triangle" iconColor={ACCENT_COLORS.amber.main} title="Low Stock Alerts" actionLabel="View report" action={() => {}} />
          <Table
            cols={[
              { label: 'Item', render: r => (
                <div>
                  <div style={{ fontWeight: 600, color: T.text, fontSize: 13 }}>{r.name}</div>
                  <div style={{ fontSize: 11, color: T.muted }}>{r.code} · {r.category}</div>
                </div>
              )},
              { label: 'Qty', render: r => <span style={{ color: ACCENT_COLORS.amber.main, fontWeight: 700 }}>{r.qty}</span> },
              { label: 'Reorder', render: r => <span style={{ color: T.muted, fontSize: 12 }}>{r.reorder}</span> },
              { label: '', render: r => (
                <button style={{ padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600, background: ACCENT_COLORS.blue.dim, color: ACCENT_COLORS.blue.main }}>
                  Restock
                </button>
              )},
            ]}
            rows={d.lowStock}
          />
        </Card>

        {/* Recent Transactions */}
        <Card>
          <CardHeader icon="fa-history" title="Recent Transactions" actionLabel="View journal" action={() => {}} />
          <Table
            cols={[
              { label: 'Time', render: r => <span style={{ color: T.muted, fontSize: 12, fontFamily: 'monospace' }}>{r.time}</span> },
              { label: 'Item', render: r => (
                <div>
                  <div style={{ fontSize: 13, color: T.text }}>{r.name}</div>
                  <div style={{ fontSize: 11, color: T.muted }}>{r.code}</div>
                </div>
              )},
              { label: 'Type', render: r => {
                const cfg = { in: { label: 'IN', color: ACCENT_COLORS.emerald.main }, out: { label: 'OUT', color: ACCENT_COLORS.red.main }, adj: { label: 'ADJ', color: ACCENT_COLORS.blue.main } };
                const c = cfg[r.type];
                return <span style={{ fontSize: 11, fontWeight: 700, color: c.color, background: c.color + '22', padding: '2px 8px', borderRadius: 4 }}>{c.label}</span>;
              }},
              { label: 'Qty', render: r => (
                <span style={{ fontWeight: 600, color: r.type === 'in' ? ACCENT_COLORS.emerald.main : r.type === 'out' ? ACCENT_COLORS.red.main : T.text }}>
                  {r.type === 'in' ? '+' : r.type === 'out' ? '-' : ''}{r.qty}
                </span>
              )},
              { label: 'By', render: r => <span style={{ fontSize: 12, color: T.muted }}>{r.user}</span> },
            ]}
            rows={d.recentTransactions}
          />
        </Card>

        {/* Monthly Movement */}
        <Card>
          <CardHeader icon="fa-chart-line" title="Monthly Movement" />
          <div style={{ padding: '24px 24px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
              {[
                { label: 'Stock In (30d)', value: '+1,240', color: ACCENT_COLORS.emerald.main },
                { label: 'Stock Out (30d)', value: '-980', color: ACCENT_COLORS.red.main },
              ].map((m, i) => (
                <div key={i} style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 28, fontWeight: 800, color: m.color }}>{m.value}</div>
                  <div style={{ fontSize: 12, color: T.muted, marginTop: 4 }}>{m.label}</div>
                </div>
              ))}
            </div>
            <div style={{ height: 10, borderRadius: 5, overflow: 'hidden', background: T.surface2, display: 'flex' }}>
              <div style={{ width: '56%', background: ACCENT_COLORS.emerald.main, transition: 'width 0.6s' }}></div>
              <div style={{ flex: 1, background: ACCENT_COLORS.red.main }}></div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 11, color: T.muted }}>
              <span>In: 56%</span><span>Out: 44%</span>
            </div>
          </div>
        </Card>

        {/* Quick Actions */}
        <Card>
          <CardHeader icon="fa-bolt" iconColor={ACCENT_COLORS.amber.main} title="Quick Actions" />
          <div style={{ padding: 20, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {[
              { icon: 'fa-file-import', label: 'Bulk Import', color: 'blue' },
              { icon: 'fa-chart-bar', label: 'Reports', color: 'emerald' },
              { icon: 'fa-tags', label: 'Categories', color: 'amber' },
              { icon: 'fa-exchange-alt', label: 'Transaction', color: 'purple' },
            ].map((a, i) => (
              <button key={i} style={{
                background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 10,
                padding: '16px 12px', cursor: 'pointer', display: 'flex', flexDirection: 'column',
                alignItems: 'center', gap: 8, transition: 'border-color 0.15s, transform 0.15s',
              }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = ACCENT_COLORS[a.color].main; e.currentTarget.style.transform = 'translateY(-1px)'; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.transform = 'none'; }}
              >
                <i className={`fas ${a.icon}`} style={{ color: ACCENT_COLORS[a.color].main, fontSize: 18 }}></i>
                <span style={{ fontSize: 12, color: T.muted, fontWeight: 500 }}>{a.label}</span>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ── Meetings ─────────────────────────────────────────────────────────────────
function ScreenMeetings() {
  const d = ErpisData.meetings;
  return (
    <div>
      <PageHeader title="Meetings" icon="fa-calendar-alt">
        <Btn variant="outline" icon="fa-chart-bar" small>Report</Btn>
        <Btn variant="primary" icon="fa-plus" small>Schedule Meeting</Btn>
      </PageHeader>

      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 20 }}>
        {/* Upcoming */}
        <Card>
          <CardHeader icon="fa-calendar-alt" iconColor={ACCENT_COLORS.blue.main} title="Upcoming Meetings" />
          <div>
            {d.upcoming.map((m, i) => (
              <div key={i} style={{
                padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 16,
                borderBottom: i < d.upcoming.length - 1 ? `1px solid ${T.border}22` : 'none',
                transition: 'background 0.15s',
              }}
                onMouseEnter={e => e.currentTarget.style.background = T.surface2}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{
                  width: 48, flexShrink: 0, textAlign: 'center',
                  background: ACCENT_COLORS.blue.dim, borderRadius: 10, padding: '8px 4px',
                }}>
                  <div style={{ fontSize: 10, color: ACCENT_COLORS.blue.main, fontWeight: 700, textTransform: 'uppercase' }}>
                    {m.date.split(' ')[1]}
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: T.text, lineHeight: 1.1 }}>
                    {m.date.split(' ')[0]}
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, color: T.text, fontSize: 14 }}>{m.title}</div>
                  <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>
                    {m.time} · {m.duration} · {m.location}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                  <i className="fas fa-users" style={{ color: T.mutedDim, fontSize: 11 }}></i>
                  <span style={{ fontSize: 12, color: T.muted }}>{m.attendees}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Recent */}
        <Card>
          <CardHeader icon="fa-history" title="Recent Meetings" actionLabel="View all" action={() => {}} />
          <div>
            {d.recent.map((m, i) => (
              <div key={i} style={{
                padding: '14px 18px',
                borderBottom: i < d.recent.length - 1 ? `1px solid ${T.border}22` : 'none',
                transition: 'background 0.15s',
              }}
                onMouseEnter={e => e.currentTarget.style.background = T.surface2}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ fontWeight: 600, color: T.text, fontSize: 13 }}>{m.title}</div>
                  <span style={{ fontSize: 11, color: T.muted, flexShrink: 0, marginLeft: 8 }}>{m.date}</span>
                </div>
                <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
                  <span style={{ fontSize: 11, color: T.muted }}><i className="fas fa-users" style={{ marginRight: 4 }}></i>{m.attendees} attendees</span>
                  {m.notes && <span style={{ fontSize: 11, color: ACCENT_COLORS.emerald.main }}><i className="fas fa-file-alt" style={{ marginRight: 4 }}></i>Notes</span>}
                  {m.actions > 0 && <span style={{ fontSize: 11, color: ACCENT_COLORS.amber.main }}><i className="fas fa-tasks" style={{ marginRight: 4 }}></i>{m.actions} actions</span>}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ── Marketplace ───────────────────────────────────────────────────────────────
function ScreenMarketplace() {
  const d = ErpisData.marketplace;
  const [statusFilter, setStatusFilter] = React.useState('');
  const filtered = d.orders.filter(o => !statusFilter || o.status === statusFilter);

  return (
    <div>
      <PageHeader title="Marketplace Orders" icon="fa-shopping-cart">
        <Btn variant="outline" icon="fa-store" small>Store Settings</Btn>
        <Btn variant="primary" icon="fa-ship" small>Process Orders</Btn>
      </PageHeader>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {d.stats.map((s, i) => <KpiCard key={i} {...s} />)}
      </div>

      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {['', 'pending', 'shipped', 'delivered', 'cancelled'].map(s => (
          <button key={s} onClick={() => setStatusFilter(s)} style={{
            padding: '6px 14px', borderRadius: 20, border: `1px solid ${statusFilter === s ? ACCENT_COLORS.emerald.main : T.border}`,
            background: statusFilter === s ? ACCENT_COLORS.emerald.dim : 'transparent',
            color: statusFilter === s ? ACCENT_COLORS.emerald.main : T.muted,
            cursor: 'pointer', fontSize: 12, fontWeight: 600, transition: 'all 0.15s',
          }}>
            {s === '' ? 'All Orders' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <Card>
        <Table
          cols={[
            { label: 'Order', render: r => <span style={{ fontFamily: 'monospace', fontSize: 13, fontWeight: 700, color: T.text }}>{r.id}</span> },
            { label: 'Customer', render: r => (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Avatar initials={r.customer.split(' ').map(n => n[0]).join('')} size={28} />
                <span style={{ fontSize: 13 }}>{r.customer}</span>
              </div>
            )},
            { label: 'Items', render: r => <span style={{ color: T.muted, fontSize: 12 }}>{r.items} item{r.items > 1 ? 's' : ''}</span> },
            { label: 'Total', right: true, render: r => <span style={{ fontWeight: 700, color: T.text }}>FCFA {r.total}</span> },
            { label: 'Status', render: r => <Badge status={r.status} /> },
            { label: 'Date', render: r => <span style={{ fontSize: 12, color: T.muted }}>{r.date}</span> },
            { label: '', render: r => (
              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                {r.status === 'pending' && (
                  <button style={{ padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600, background: ACCENT_COLORS.emerald.dim, color: ACCENT_COLORS.emerald.main }}>
                    Ship
                  </button>
                )}
                <button style={{ padding: '4px 10px', borderRadius: 6, border: `1px solid ${T.border}`, cursor: 'pointer', fontSize: 11, color: T.muted, background: 'transparent' }}>
                  View
                </button>
              </div>
            )},
          ]}
          rows={filtered}
        />
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: T.muted }}>{filtered.length} order{filtered.length !== 1 ? 's' : ''}</span>
        </div>
      </Card>
    </div>
  );
}

// Export all screens
Object.assign(window, {
  ScreenDashboard,
  ScreenFinance,
  ScreenEmployees,
  ScreenHR,
  ScreenInventory,
  ScreenMeetings,
  ScreenMarketplace,
});
