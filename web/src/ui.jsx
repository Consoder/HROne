import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, CalendarDays, ChevronDown, Command, Download, Fingerprint, LifeBuoy, LogOut, Search, ShieldCheck, Sparkles, X } from 'lucide-react';
import { GridRise, LuminousType, MeshLettering } from './landing-effects.jsx';

const api = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json' }, ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Request failed. Please try again.');
  return payload;
};
// Attendance dates follow the API's business timezone, not the viewer's machine timezone.
const indiaDate = (date = new Date()) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
const lastDayOfMonth = month => new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0)).getUTCDate();
const todayMonth = () => indiaDate().slice(0, 7);
const asMillis = value => new Date(value).getTime();
const timeLabel = value => value == null ? '—' : new Date(value).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' });

function BlurReveal({ children }) {
  // React Bits Blur Text idea: resolve the title from soft blur as the app appears.
  return <span className="blur-reveal">{children}</span>;
}

function SpotlightCard({ children, className = '' }) {
  // React Bits spotlight-card idea: pointer position controls a subtle card glow.
  return <section className={`spotlight-card ${className}`} onPointerMove={event => {
    const box = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--px', `${event.clientX - box.left}px`);
    event.currentTarget.style.setProperty('--py', `${event.clientY - box.top}px`);
  }}>{children}</section>;
}

function PeopleGlyph({ kind }) {
  // Small original CSS marks keep the main navigation and KPI cards on-brand without icon-font dependencies.
  return <span className={`people-glyph glyph-${kind}`} aria-hidden="true"><i /><i /><i /></span>;
}

function App() {
  const [employees, setEmployees] = useState([]);
  const [attendance, setAttendance] = useState([]);
  const [employee, setEmployee] = useState('');
  const [summary, setSummary] = useState(null);
  const [month, setMonth] = useState(todayMonth());
  const [today, setToday] = useState(indiaDate());
  const [departments, setDepartments] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const refreshSequence = useRef(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('Overview');

  const refresh = async (code = employee, selectedMonth = month) => {
    const sequence = ++refreshSequence.current;
    setLoading(true);
    try {
      const dateRange = `date_from=${selectedMonth}-01&date_to=${selectedMonth}-${String(lastDayOfMonth(selectedMonth)).padStart(2, '0')}`;
      const [people, firstPage] = await Promise.all([api('/employees?page=1&page_size=100'), api(`/attendance?${dateRange}&page=1&page_size=100`)]);
      const remainingPages = Math.ceil(firstPage.total / 100) - 1;
      const remaining = await Promise.all(Array.from({ length: remainingPages }, (_, index) => api(`/attendance?${dateRange}&page=${index + 2}&page_size=100`)));
      if (sequence !== refreshSequence.current) return;
      setEmployees(people.items);
      setAttendance([...firstPage.items, ...remaining.flatMap(page => page.items)]);
      const active = code || people.items[0]?.emp_code || '';
      setEmployee(active);
      if (active) setSummary(await api(`/analytics/employees/${active}/monthly?month=${selectedMonth}`));
      else setSummary(null);
      setNotice('');
    } catch (error) {
      if (sequence !== refreshSequence.current) return;
      // Clear month-scoped data on failure so stale numbers cannot look current.
      setAttendance([]);
      setSummary(null);
      setNotice(error.message);
    } finally { if (sequence === refreshSequence.current) setLoading(false); }
  };

  useEffect(() => { refresh(); }, []);
  useEffect(() => { if (employee) refresh(employee, month); }, [month]);
  useEffect(() => {
    const timer = window.setInterval(() => setToday(indiaDate()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (tab !== 'Analytics') return;
    let current = true;
    Promise.all([api(`/analytics/departments/summary?month=${month}`), api(`/analytics/leaderboard/late?month=${month}&limit=10`)]).then(([dept, late]) => {
      if (current) { setDepartments(dept.items); setLeaderboard(late.items); }
    }).catch(error => { if (current) { setDepartments([]); setLeaderboard([]); setNotice(error.message); } });
    return () => { current = false; };
  }, [tab, month]);

  const selected = employees.find(person => person.emp_code === employee);
  const selectedRows = useMemo(() => attendance.filter(row => row.emp_code === employee), [attendance, employee]);
  const presentToday = attendance.filter(row => row.date === today && ['PRESENT', 'WFH', 'ON_DUTY'].includes(row.status)).length;
  const lateToday = attendance.filter(row => row.date === today && row.late_minutes > 0).length;
  const recordsForPage = tab === 'Attendance' ? attendance : selectedRows;
  const filteredRows = recordsForPage.filter(row => `${row.date} ${row.status} ${row.emp_code} ${employees.find(person => person.emp_code === row.emp_code)?.name || ''}`.toLowerCase().includes(query.trim().toLowerCase()));
  const filteredEmployees = employees.filter(person => `${person.name} ${person.emp_code} ${person.department}`.toLowerCase().includes(query.trim().toLowerCase()));
  const openRecord = selectedRows.find(row => row.date === today && row.punch_in && !row.punch_out);

  async function punch(action) {
    if (!employee) return;
    setBusy(true);
    try {
      await api(`/attendance/punch-${action}`, { method: 'POST', body: JSON.stringify({ emp_code: employee }) });
      setNotice(action === 'in' ? 'You are checked in. Have a great shift.' : 'Your shift is checked out.');
      await refresh(employee, month);
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#top"><span className="brand-mark"><span /></span><span>hrone<span className="brand-dot">.</span></span></a>
      <div className="workspace-label">WORKSPACE</div>
      <div className="workspace-picker"><span className="workspace-icon">H</span><span><strong>HROne Studio</strong><small>People operations</small></span><ChevronDown size={15} /></div>
      <div className="nav-label">MENU</div>
      <nav className="nav-list">
        {[["Overview", 'orbit'], ["Employees", 'people'], ["Attendance", 'ripple'], ["Analytics", 'signal']].map(([label, kind]) => <button key={label} className={`nav-item ${tab === label ? 'active' : ''}`} onClick={() => setTab(label)}><PeopleGlyph kind={kind} /><span>{label}</span>{label === 'Attendance' && <span className="nav-count">{attendance.length}</span>}</button>)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="side-tip"><div className="tip-icon"><Sparkles size={15} /></div><b>People first, always.</b><p>Good work happens when people feel seen.</p></div>
      <a className="nav-item" href="README.md" target="_blank" rel="noreferrer"><LifeBuoy size={18} /><span>Help center</span></a>
      <button className={`nav-item ${tab === 'Settings' ? 'active' : ''}`} onClick={() => setTab('Settings')}><ShieldCheck size={18} /><span>Settings</span></button>
      <div className="user-card"><div className="avatar">KB</div><div className="user-copy"><b>Kartik Bhargava</b><small>Workspace admin</small></div></div>
    </aside>

    <main className="main-area" id="top">
      <header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> <b>{tab}</b></div><div className="top-actions"><div className="today-chip"><span className="online-dot" />Live workspace</div><a className="icon-button" aria-label="Help center" href="README.md" target="_blank" rel="noreferrer"><LifeBuoy size={18} /></a><div className="avatar small-avatar">KB</div></div></header>

      <div className="content-wrap motion-stage" key={tab}>
        <GridRise className="attendance-hero">
          <div className="hero-copy">
            <MeshLettering text="PEOPLE FIRST · EVERY DAY" />
            <h2><LuminousType>Attendance, in rhythm.</LuminousType></h2>
            <p>A calmer way to see your people, their time, and how the day is moving.</p>
            <a className="hero-link" href="#dashboard">Explore your day <ArrowDownRight size={15} /></a>
          </div>
          <div className="hero-note"><span className="online-dot" /><span><b>People operations</b><small>One clear view of today</small></span><CalendarDays size={19} /></div>
        </GridRise>

        <div className="page-heading" id="dashboard"><div><div className="eyebrow"><span className="eyebrow-line" /> {new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Kolkata', weekday: 'long' }).format(new Date()).toUpperCase()}, {new Date(`${today}T12:00:00`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase()}</div><h1><BlurReveal>{tab === 'Overview' ? 'Good morning, Kartik' : tab}</BlurReveal><span className="wave">✳</span></h1><p>{tab === 'Overview' ? 'Here’s what’s happening with your people today.' : `A clear view of ${tab.toLowerCase()} for your workspace.`}</p></div><div className="heading-actions"><button className="button quiet" onClick={() => refresh()}><Activity size={16} /> Refresh</button><button className="button primary" onClick={() => window.print()}><Download size={16} /> Export report</button></div></div>

        {notice && <div className={`notice ${notice.includes('failed') || notice.includes('already') || notice.includes('not found') ? 'notice-error' : ''}`}><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss"><X size={16} /></button></div>}
        {loading && <div className="loading-line"><span /> Loading attendance data…</div>}

        {tab !== 'Employees' && tab !== 'Settings' && <div className="stats-grid">
          <SpotlightCard className="stat-card"><div className="stat-top"><span>TEAM HEADCOUNT</span><span className="stat-icon lilac"><PeopleGlyph kind="people" /></span></div><div className="stat-value">{employees.length || '—'}<small> people</small></div><div className="stat-foot"><span className="stat-trend"><ArrowUpRight size={14} /> Active</span><span>in your workspace</span></div><div className="stat-spark spark-one"><i /><i /><i /><i /><i /><i /><i /></div></SpotlightCard>
          <SpotlightCard className="stat-card"><div className="stat-top"><span>PRESENT TODAY</span><span className="stat-icon mint"><PeopleGlyph kind="checkmark" /></span></div><div className="stat-value">{presentToday}<small> people</small></div><div className="stat-foot"><span className="stat-trend mint-text"><ArrowUpRight size={14} /> On track</span><span>attendance today</span></div><div className="stat-spark spark-two"><i /><i /><i /><i /><i /><i /><i /></div></SpotlightCard>
          <SpotlightCard className="stat-card"><div className="stat-top"><span>LATE ARRIVALS</span><span className="stat-icon peach"><PeopleGlyph kind="flame" /></span></div><div className="stat-value">{lateToday}<small> people</small></div><div className="stat-foot"><span className="stat-trend orange-text"><ArrowDownRight size={14} /> Today</span><span>after grace period</span></div><div className="stat-spark spark-three"><i /><i /><i /><i /><i /><i /><i /></div></SpotlightCard>
          <SpotlightCard className="stat-card"><div className="stat-top"><span>YOUR ATTENDANCE</span><span className="stat-icon blue"><PeopleGlyph kind="bloom" /></span></div><div className="stat-value">{summary?.attendance_pct?.toFixed(1) ?? '—'}<small>%</small></div><div className="stat-foot"><span className="stat-trend blue-text"><CalendarDays size={13} /> {month}</span><span>{summary?.present_days ?? 0} present days</span></div><div className="stat-spark spark-four"><i /><i /><i /><i /><i /><i /><i /></div></SpotlightCard>
        </div>}

        {tab === 'Overview' && <div className="dashboard-grid">
          <section className="panel check-panel"><div className="panel-heading"><div><div className="panel-kicker">YOUR DAY</div><h2>Attendance check-in</h2></div><span className="secure-pill"><ShieldCheck size={14} /> Secure</span></div><div className="check-inner"><div className="check-illustration"><div className="sun-halo" /><div className="clock-face"><div className="clock-hand" /><span className="clock-center" /></div><span className="float-dot dot-a" /><span className="float-dot dot-b" /><span className="float-dot dot-c" /></div><div className="check-copy"><p className="check-date">{new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}</p><h3>{openRecord ? 'You’re on the clock.' : 'Ready when you are.'}</h3><p>{openRecord ? `Checked in at ${timeLabel(openRecord.punch_in)}. Remember to check out before you leave.` : 'Start your day with a quick check-in. Your team will know you’re here.'}</p><div className="check-buttons"><button className="button primary check-button" disabled={busy || !!openRecord} onClick={() => punch('in')}><Fingerprint size={17} /> {busy ? 'Working…' : openRecord ? 'Checked in' : 'Check in'}</button><button className="button outline check-button" disabled={busy || !openRecord} onClick={() => punch('out')}><LogOut size={16} /> Check out</button></div><small className="timezone-note"><span className="online-dot" /> Times recorded in India Standard Time</small></div></div></section>

          <section className="panel summary-panel"><div className="panel-heading"><div><div className="panel-kicker">YOUR SUMMARY</div><h2>Monthly overview</h2></div><label className="month-select"><CalendarDays size={14} /><input type="month" value={month} onChange={event => setMonth(event.target.value)} /></label></div><label className="person-select-label" htmlFor="employee-choice">Choose an employee</label><div className="select-wrap"><select id="employee-choice" value={employee} onChange={event => { setEmployee(event.target.value); refresh(event.target.value, month); }}><option value="">Select employee</option>{employees.map(person => <option key={person.emp_code} value={person.emp_code}>{person.name} · {person.emp_code}</option>)}</select><ChevronDown size={16} /></div>{selected && <div className="person-mini"><div className="avatar person-avatar">{selected.name.split(' ').map(part => part[0]).slice(0, 2).join('')}</div><div><b>{selected.name}</b><small>{selected.department} · Joined {selected.joined_on}</small></div><span className="presence-badge"><i /> Employee</span></div>}<div className="summary-numbers"><div><strong>{summary?.present_days ?? '—'}</strong><span>Present days</span></div><div><strong>{summary?.working_days ?? '—'}</strong><span>Working days</span></div><div><strong>{summary?.late_count ?? '—'}</strong><span>Late arrivals</span></div></div><div className="progress-label"><span>Attendance rate</span><b>{summary?.attendance_pct?.toFixed(1) ?? '—'}%</b></div><div className="progress-track"><span style={{ width: `${Math.min(100, summary?.attendance_pct || 0)}%` }} /></div><div className="summary-foot">Based on working days since joining <span>↗</span></div></section>
        </div>}

        {tab === 'Employees' && <section className="panel records-panel"><div className="records-header"><div><div className="panel-kicker">YOUR PEOPLE</div><h2>Employee directory</h2></div><div className="records-actions"><div className="search-box"><Search size={16} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search name, code, department" /></div><button className="button outline filter-button" onClick={() => setQuery('')}><X size={14} /> Clear</button></div></div><div className="table-scroll"><table><thead><tr><th>EMPLOYEE</th><th>EMPLOYEE CODE</th><th>DEPARTMENT</th><th>JOINED</th><th>STATUS</th></tr></thead><tbody>{filteredEmployees.map(person => <tr key={person.emp_code}><td><b>{person.name}</b></td><td>{person.emp_code}</td><td>{person.department}</td><td>{person.joined_on}</td><td><button className="view-all" onClick={() => { setEmployee(person.emp_code); setTab('Overview'); }}>View summary <ArrowUpRight size={14} /></button></td></tr>)}{!filteredEmployees.length && <tr><td className="empty-state" colSpan="5">No employees match your search.</td></tr>}</tbody></table></div><div className="table-footer"><span><b>{filteredEmployees.length}</b> employees</span></div></section>}

        {tab === 'Analytics' && <div className="analytics-grid"><section className="panel records-panel"><div className="panel-kicker">TEAM BREAKDOWN</div><h2>Department summary · {month}</h2><div className="table-scroll"><table><thead><tr><th>DEPARTMENT</th><th>HEADCOUNT</th><th>PRESENT DAYS</th><th>AVG HOURS</th><th>LATE ARRIVALS</th></tr></thead><tbody>{departments.map(row => <tr key={row.department}><td><b>{row.department}</b></td><td>{row.headcount}</td><td>{row.present_days}</td><td>{row.avg_work_hours == null ? '—' : `${row.avg_work_hours.toFixed(2)}h`}</td><td>{row.late_count}</td></tr>)}{!departments.length && <tr><td colSpan="5" className="empty-state">No department analytics for this month.</td></tr>}</tbody></table></div></section><section className="panel records-panel"><div className="panel-kicker">CONSISTENCY</div><h2>Late arrivals · {month}</h2><div className="table-scroll"><table><thead><tr><th>RANK</th><th>EMPLOYEE</th><th>DEPARTMENT</th><th>LATE MINUTES</th><th>DAYS LATE</th></tr></thead><tbody>{leaderboard.map(row => <tr key={row.emp_code}><td>#{row.rank}</td><td><b>{row.name}</b><small>{row.emp_code}</small></td><td>{row.department}</td><td>{row.total_late_minutes}</td><td>{row.late_count}</td></tr>)}{!leaderboard.length && <tr><td colSpan="5" className="empty-state">No late arrivals recorded for this month.</td></tr>}</tbody></table></div></section></div>}

        {tab === 'Settings' && <section className="panel settings-panel"><div className="panel-kicker">WORKSPACE PREFERENCES</div><h2>Settings</h2><p>Attendance is recorded in India Standard Time (IST). The selected reporting month controls attendance and analytics views.</p><label className="month-select"><CalendarDays size={14} /><input aria-label="Reporting month" type="month" value={month} onChange={event => setMonth(event.target.value)} /></label></section>}

        {(tab === 'Overview' || tab === 'Attendance') && <section className="panel records-panel"><div className="records-header"><div><div className="panel-kicker">A CLEAR VIEW OF YOUR DAYS</div><h2>{tab === 'Attendance' ? 'Attendance records' : 'Recent attendance'}</h2></div><div className="records-actions">{tab === 'Attendance' && <label className="month-select"><CalendarDays size={14} /><input aria-label="Attendance month" type="month" value={month} onChange={event => setMonth(event.target.value)} /></label>}<div className="search-box"><Search size={16} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search date, status or employee" /><kbd><Command size={11} /> K</kbd></div><button className="button outline filter-button" onClick={() => setQuery('')}><X size={14} /> Clear</button></div></div><div className="table-scroll"><table><thead><tr>{tab === 'Attendance' && <th>EMPLOYEE</th>}<th>DATE</th><th>STATUS</th><th>CHECK IN</th><th>CHECK OUT</th><th>HOURS</th><th>DAY</th></tr></thead><tbody>{filteredRows.slice(0, tab === 'Attendance' ? 100 : 8).map(row => <tr key={`${row.emp_code}-${row.date}`}>{tab === 'Attendance' && <td><b>{employees.find(person => person.emp_code === row.emp_code)?.name || row.emp_code}</b><small>{row.emp_code}</small></td>}<td><b>{new Date(`${row.date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</b><small>{new Date(`${row.date}T12:00:00`).toLocaleDateString('en-US', { weekday: 'long' })}</small></td><td><span className={`status-pill ${row.status.toLowerCase()}`}><i />{row.status.replace('_', ' ')}</span></td><td>{timeLabel(row.punch_in)}</td><td>{timeLabel(row.punch_out)}</td><td>{row.work_hours == null ? '—' : `${row.work_hours.toFixed(2)}h`}</td><td>{row.half_day ? <span className="half-day">Half day</span> : row.late_minutes > 0 ? <span className="late-flag">{row.late_minutes} min late</span> : <span className="on-time">On time</span>}</td></tr>)}{!filteredRows.length && <tr><td className="empty-state" colSpan={tab === 'Attendance' ? 7 : 6}>No attendance records found for this selection.</td></tr>}</tbody></table></div><div className="table-footer"><span>Showing <b>{Math.min(filteredRows.length, tab === 'Attendance' ? 100 : 8)}</b> of <b>{filteredRows.length}</b> records</span>{tab === 'Overview' && <button className="view-all" onClick={() => { setTab('Attendance'); setQuery(''); }}>View attendance <ArrowUpRight size={14} /></button>}</div></section>}
        <footer className="page-footer"><span>Made for people, by people <span className="footer-heart">♥</span></span><span>HROne <b>·</b> Attendance workspace</span></footer>
      </div>
    </main>
  </div>;
}

export default App;
