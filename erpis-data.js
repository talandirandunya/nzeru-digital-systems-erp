// Erpis Mock Data
const ErpisData = {
  company: { name: "Erpis", domain: "erpis.io" },
  user: { name: "Amara Diallo", role: "Admin", initials: "AD" },

  dashboard: {
    stats: [
      { label: "Total Employees", value: "142", sub: "128 active", icon: "fa-users", color: "emerald" },
      { label: "Active Projects", value: "18", sub: "3 overdue", icon: "fa-project-diagram", color: "blue" },
      { label: "Stock Items", value: "864", sub: "12 low stock", icon: "fa-boxes", color: "amber" },
      { label: "Total Balance", value: "FCFA 4.2M", sub: "+FCFA 280K this month", icon: "fa-wallet", color: "purple" },
    ],
    recentProjects: [
      { name: "Website Redesign", status: "in_progress", progress: 68 },
      { name: "Mobile App v2", status: "in_progress", progress: 42 },
      { name: "ERP Migration", status: "on_hold", progress: 25 },
      { name: "Payroll System", status: "completed", progress: 100 },
      { name: "CRM Integration", status: "in_progress", progress: 55 },
    ],
    recentEmployees: [
      { id: "EMP-001", name: "Kofi Mensah", dept: "Engineering", status: "active", initials: "KM" },
      { id: "EMP-002", name: "Fatima Ouedraogo", dept: "Finance", status: "active", initials: "FO" },
      { id: "EMP-003", name: "Yann Traoré", dept: "HR", status: "on_leave", initials: "YT" },
      { id: "EMP-004", name: "Aisha Bamba", dept: "Sales", status: "active", initials: "AB" },
    ],
    // Action-oriented priority stack (used by PriorityStack)
    priority: [
      { title: 'Approve Payroll', description: 'Payroll for Apr 2026 pending approval — 2 flagged items', color: '#16a34a', action: 'Approve', onView: null, onAct: null },
      { title: 'Resolve Overdue Projects', description: '3 projects overdue — assign owners and schedule remediation', color: '#d97706', action: 'Assign', onView: null, onAct: null },
      { title: 'Low Stock Alerts', description: '12 items below reorder threshold — prioritize replenishment', color: '#d97706', action: 'Restock', onView: null, onAct: null },
    ],
    // Roadmap / recommendations scaffold
    roadmap: [
      { title: 'Payroll Modernization', status: 'In Progress', progress: 45, recommendation: 'Prioritize migration of tax calculation engine.' },
      { title: 'Mobile UX Improvements', status: 'Planned', progress: 10, recommendation: 'Implement responsive grid and touch targets.' },
    ],
  },

  finance: {
    stats: [
      { label: "Total Balance", value: "FCFA 4,280,000", sub: "across 6 accounts", icon: "fa-wallet", color: "emerald" },
      { label: "Total Credits", value: "FCFA 1,820,000", sub: "all time", icon: "fa-arrow-down", color: "emerald" },
      { label: "Total Debits", value: "FCFA 940,000", sub: "all time", icon: "fa-arrow-up", color: "red" },
      { label: "Net This Month", value: "+FCFA 280,000", sub: "↑ 480K · ↓ 200K", icon: "fa-calendar-alt", color: "emerald" },
    ],
    transactions: [
      { date: "29 Apr 2026", account: "Operations", description: "Office supplies purchase", credit: null, debit: "45,000" },
      { date: "28 Apr 2026", account: "Sales Revenue", description: "Client payment – Invoice #1042", credit: "320,000", debit: null },
      { date: "27 Apr 2026", account: "Payroll", description: "April payroll disbursement", credit: null, debit: "980,000" },
      { date: "26 Apr 2026", account: "Sales Revenue", description: "Client payment – Invoice #1039", credit: "150,000", debit: null },
      { date: "25 Apr 2026", account: "Operations", description: "Internet & utilities", credit: null, debit: "18,500" },
      { date: "24 Apr 2026", account: "Sales Revenue", description: "Marketplace orders batch", credit: "88,000", debit: null },
    ],
    topAccounts: [
      { name: "Sales Revenue", balance: "2,100,000" },
      { name: "Operations", balance: "980,000" },
      { name: "Payroll", balance: "740,000" },
      { name: "Tax Reserve", balance: "310,000" },
      { name: "Petty Cash", balance: "150,000" },
    ],
  },

  employees: [
    { id: "EMP-001", name: "Kofi Mensah", email: "k.mensah@erpis.io", dept: "Engineering", role: "Manager", status: "active", salary: "1,200,000", joined: "Jan 12, 2022", initials: "KM" },
    { id: "EMP-002", name: "Fatima Ouedraogo", email: "f.ouedraogo@erpis.io", dept: "Finance", role: "Accountant", status: "active", salary: "980,000", joined: "Mar 3, 2021", initials: "FO" },
    { id: "EMP-003", name: "Yann Traoré", email: "y.traore@erpis.io", dept: "HR", role: "HR Manager", status: "on_leave", salary: "1,050,000", joined: "Jun 19, 2020", initials: "YT" },
    { id: "EMP-004", name: "Aisha Bamba", email: "a.bamba@erpis.io", dept: "Sales", role: "Secretary", status: "active", salary: "850,000", joined: "Aug 7, 2023", initials: "AB" },
    { id: "EMP-005", name: "Moussa Coulibaly", email: "m.coulibaly@erpis.io", dept: "Engineering", role: "Employee", status: "active", salary: "780,000", joined: "Feb 14, 2024", initials: "MC" },
    { id: "EMP-006", name: "Nadia Sawadogo", email: "n.sawadogo@erpis.io", dept: "Marketing", role: "Employee", status: "inactive", salary: "720,000", joined: "Apr 1, 2023", initials: "NS" },
    { id: "EMP-007", name: "Ibrahim Kone", email: "i.kone@erpis.io", dept: "Engineering", role: "Employee", status: "active", salary: "820,000", joined: "Sep 22, 2022", initials: "IK" },
  ],

  inventory: {
    stats: [
      { label: "Total Items", value: "864", sub: "across 14 categories", icon: "fa-boxes", color: "blue" },
      { label: "Total Value", value: "FCFA 8.4M", sub: "at cost price", icon: "fa-dollar-sign", color: "emerald" },
      { label: "Low Stock", value: "12", sub: "need reorder", icon: "fa-exclamation-triangle", color: "amber" },
      { label: "Out of Stock", value: "3", sub: "urgent", icon: "fa-times-circle", color: "red" },
    ],
    lowStock: [
      { code: "STK-042", name: "Printer Paper A4", category: "Office", qty: 5, reorder: 20, value: "12,500" },
      { code: "STK-118", name: "Laptop Charger 65W", category: "Electronics", qty: 2, reorder: 10, value: "68,000" },
      { code: "STK-077", name: "Hand Sanitizer 500ml", category: "Hygiene", qty: 8, reorder: 30, value: "9,600" },
      { code: "STK-203", name: "Ballpoint Pens (box)", category: "Office", qty: 1, reorder: 15, value: "3,500" },
    ],
    recentTransactions: [
      { time: "14:22", code: "STK-042", name: "Printer Paper A4", type: "out", qty: 10, user: "Kofi Mensah" },
      { time: "11:05", code: "STK-310", name: "USB-C Hub", type: "in", qty: 25, user: "Aisha Bamba" },
      { time: "09:48", code: "STK-077", name: "Hand Sanitizer 500ml", type: "out", qty: 12, user: "Moussa Coulibaly" },
      { time: "08:30", code: "STK-210", name: "Whiteboard Markers", type: "adj", qty: 40, user: "System" },
    ],
  },

  hr: {
    stats: [
      { label: "Pending Requests", value: "4", icon: "fa-clock", color: "amber" },
      { label: "Approved", value: "28", icon: "fa-check-circle", color: "emerald" },
      { label: "On Leave Now", value: "3", icon: "fa-user-clock", color: "blue" },
      { label: "Positions", value: "22", icon: "fa-briefcase", color: "purple" },
    ],
    pendingLeaves: [
      { name: "Yann Traoré", type: "Annual Leave", from: "5 May", to: "12 May 2026", days: 7 },
      { name: "Moussa Coulibaly", type: "Sick Leave", from: "30 Apr", to: "2 May 2026", days: 3 },
      { name: "Nadia Sawadogo", type: "Maternity Leave", from: "1 Jun", to: "30 Aug 2026", days: 90 },
      { name: "Ibrahim Kone", type: "Personal Leave", from: "6 May", to: "6 May 2026", days: 1 },
    ],
    onLeave: [
      { name: "Yann Traoré", returns: "12 May" },
      { name: "Aminata Diallo", returns: "3 May" },
      { name: "Sékou Barry", returns: "30 Apr" },
    ],
    upcomingLeaves: [
      { name: "Kofi Mensah", type: "Annual Leave", from: "15 May", to: "22 May" },
      { name: "Fatima Ouedraogo", type: "Personal Leave", from: "10 May", to: "11 May" },
    ],
  },

  meetings: {
    upcoming: [
      { title: "Q2 Finance Review", date: "30 Apr 2026", time: "10:00", duration: "90 min", attendees: 6, location: "Board Room A" },
      { title: "Engineering Sprint Planning", date: "1 May 2026", time: "09:00", duration: "60 min", attendees: 8, location: "Remote" },
      { title: "HR Policy Update", date: "2 May 2026", time: "14:00", duration: "45 min", attendees: 4, location: "Conference Room 2" },
      { title: "Client Onboarding – TechCo", date: "5 May 2026", time: "11:00", duration: "60 min", attendees: 5, location: "Remote" },
    ],
    recent: [
      { title: "Weekly Standup", date: "28 Apr 2026", attendees: 10, notes: true, actions: 3 },
      { title: "Budget Planning FY2026", date: "25 Apr 2026", attendees: 5, notes: true, actions: 7 },
      { title: "Inventory Audit Review", date: "22 Apr 2026", attendees: 4, notes: false, actions: 2 },
    ],
  },

  marketplace: {
    stats: [
      { label: "Orders Today", value: "24", sub: "+12% vs yesterday", icon: "fa-shopping-cart", color: "blue" },
      { label: "Pending", value: "8", sub: "need processing", icon: "fa-clock", color: "amber" },
      { label: "Shipped", value: "13", sub: "in transit", icon: "fa-truck", color: "emerald" },
      { label: "Revenue Today", value: "FCFA 184,000", sub: "12 paid orders", icon: "fa-money-bill-wave", color: "purple" },
    ],
    orders: [
      { id: "#ORD-1081", customer: "Marie Dupont", items: 3, total: "24,500", status: "pending", date: "29 Apr, 14:32" },
      { id: "#ORD-1080", customer: "Jean-Paul Aka", items: 1, total: "8,000", status: "shipped", date: "29 Apr, 13:15" },
      { id: "#ORD-1079", customer: "Sylvie Koffi", items: 5, total: "61,000", status: "delivered", date: "29 Apr, 11:44" },
      { id: "#ORD-1078", customer: "René Ouédraogo", items: 2, total: "18,000", status: "shipped", date: "29 Apr, 10:20" },
      { id: "#ORD-1077", customer: "Aminata Ba", items: 4, total: "32,500", status: "pending", date: "29 Apr, 09:05" },
      { id: "#ORD-1076", customer: "Ismaïla Faye", items: 1, total: "15,000", status: "cancelled", date: "28 Apr, 17:50" },
    ],
  },
};

// Make available globally
window.ErpisData = ErpisData;
