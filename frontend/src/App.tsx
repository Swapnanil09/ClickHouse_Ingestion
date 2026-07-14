import React, { useState, useEffect } from 'react';
import { 
  BarChart, Activity, Database, ShieldAlert, Settings, Send, 
  RefreshCw, LogOut, CheckCircle, XCircle, AlertTriangle, Key, ChevronRight, X, Sun, Moon
} from 'lucide-react';

const API_BASE = "http://127.0.0.1:8081/api";

export default function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [user, setUser] = useState<any | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  
  const [currentPage, setCurrentPage] = useState("overview");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  
  // Theme and Microsoft Connection status
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [msStatus, setMsStatus] = useState<{ connected: boolean, email: string | null, expires_at?: string } | null>(null);
  
  // Stats & Lists
  const [stats, setStats] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [filteredStatus, setFilteredStatus] = useState<string>("");
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [notifications, setNotifications] = useState<any[]>([]);
  
  // Job Details
  const [jobDetail, setJobDetail] = useState<any>(null);
  
  // ClickHouse testing
  const [chHost, setChHost] = useState("emulated");
  const [chPort, setChPort] = useState(8123);
  const [chUser, setChUser] = useState("default");
  const [chPass, setChPass] = useState("");
  const [chName, setChName] = useState("Local Emulator");
  const [testResult, setTestResult] = useState<string | null>(null);
  
  // Emulator tables
  const [emulatorTables, setEmulatorTables] = useState<any[]>([]);
  const [showAddEmulatorTable, setShowAddEmulatorTable] = useState(false);
  const [newTabName, setNewTabName] = useState("");
  const [newTabDb, setNewTabDb] = useState("default");
  
  // Power Automate Simulation
  const [presetName, setPresetName] = useState("success");
  const [targetTable, setTargetTable] = useState("user_activities");
  const [targetDatabase, setTargetDatabase] = useState("default");
  const [processingMode, setProcessingMode] = useState("STRICT");
  const [sheetName, setSheetName] = useState("Sheet1");
  const [isSimulating, setIsSimulating] = useState(false);

  // Error notifications toast list
  const [toasts, setToasts] = useState<any[]>([]);
  
  const showToast = (message: string, type: 'success' | 'danger' = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  };

  // Helper fetcher
  const apiFetch = async (endpoint: string, options: RequestInit = {}) => {
    const headers = {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
      ...options.headers
    };
    
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
      if (res.status === 401) {
        localStorage.removeItem("token");
        setToken(null);
        setUser(null);
        return null;
      }
      
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "API Request Failed");
      }
      return data;
    } catch (err: any) {
      showToast(err.message, 'danger');
      throw err;
    }
  };

  // Login handler
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Login Failed");
      
      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      showToast("Logged in successfully!");
    } catch (err: any) {
      setLoginError(err.message);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    showToast("Logged out");
  };

  // Fetch current user details
  useEffect(() => {
    if (token) {
      apiFetch("/auth/me")
        .then(data => {
          if (data) setUser(data);
        })
        .catch(() => {});
    }
  }, [token]);

  // Refresh lists & metrics
  const refreshData = () => {
    if (!token) return;
    
    // Overview Stats
    apiFetch("/jobs/overview/stats")
      .then(data => { if (data) setStats(data); })
      .catch(() => {});
      
    // Jobs List
    apiFetch(`/jobs?status=${filteredStatus}`)
      .then(data => { if (data) setJobs(data); })
      .catch(() => {});
      
    // Emulator Tables
    apiFetch("/connections/emulator/tables")
      .then(data => { if (data) setEmulatorTables(data); })
      .catch(() => {});
      
    // Workflows List
    apiFetch("/workflows")
      .then(data => { if (data) setWorkflows(data); })
      .catch(() => {});
      
    // Notifications Mock List
    apiFetch("/upload/notifications")
      .then(data => { if (data) setNotifications(data); })
      .catch(() => {});
      
    // MS Graph Status
    apiFetch("/auth/microsoft/status")
      .then(data => { if (data) setMsStatus(data); })
      .catch(() => {});
  };

  // Fetch Job details when job selected
  useEffect(() => {
    if (selectedJobId && token) {
      apiFetch(`/jobs/${selectedJobId}`)
        .then(data => { if (data) setJobDetail(data); })
        .catch(() => {});
        
      // Setup interval to poll active job updates
      const poll = setInterval(() => {
        apiFetch(`/jobs/${selectedJobId}`)
          .then(data => {
            if (data) {
              setJobDetail(data);
              // Stop polling when finished
              if (["COMPLETED", "FAILED", "QUARANTINED", "CANCELLED"].includes(data.status)) {
                clearInterval(poll);
              }
            }
          })
          .catch(() => {});
      }, 2000);
      
      return () => clearInterval(poll);
    }
  }, [selectedJobId, token]);

  // Theme Sync
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  // Check URL query parameters for MS oauth callback success
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("ms_connected") === "true") {
      showToast("Microsoft account connected successfully!", "success");
      // Clean query parameter from URL
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  // MS Account disconnect
  const handleMsDisconnect = async () => {
    try {
      await apiFetch("/auth/microsoft/disconnect", { method: "POST" });
      showToast("Microsoft account disconnected.", "success");
      setMsStatus({ connected: false, email: null });
    } catch (err: any) {
      showToast(err.message, "danger");
    }
  };

  // Polling loop for active dashboard metrics (near real-time)
  useEffect(() => {
    refreshData();
    if (token) {
      const interval = setInterval(refreshData, 3000);
      return () => clearInterval(interval);
    }
  }, [token, filteredStatus]);

  // Test Connection
  const handleTestConnection = async () => {
    setTestResult("Testing connection...");
    try {
      const res = await apiFetch("/connections/test-raw", {
        method: "POST",
        body: JSON.stringify({
          name: chName,
          host: chHost,
          port: chPort,
          username: chUser,
          password: chPass,
          secure: false,
          databases_restricted: "default"
        })
      });
      if (res) {
        setTestResult(res.message);
        showToast("ClickHouse Connection successful!");
        refreshData();
      }
    } catch (err: any) {
      setTestResult(`Failed: ${err.message}`);
    }
  };

  // Create Mock table in Emulator
  const handleCreateEmulatorTable = async () => {
    try {
      let schemaFields = [
        { name: "id", type: "UInt32", nullable: false },
        { name: "user_id", type: "String", nullable: false },
        { name: "activity", type: "String", nullable: false },
        { name: "timestamp", type: "DateTime", nullable: false }
      ];
      
      if (newTabName === "user_data_index") {
        schemaFields = [
          { name: "id", type: "UInt32", nullable: false },
          { name: "email", type: "String", nullable: false },
          { name: "status", type: "String", nullable: true },
          { name: "created_at", type: "Date", nullable: false }
        ];
      }
      
      await apiFetch("/connections/emulator/tables", {
        method: "POST",
        body: JSON.stringify({
          database: newTabDb,
          table_name: newTabName,
          schema_fields: schemaFields
        })
      });
      showToast(`Emulator table '${newTabDb}.${newTabName}' created successfully!`);
      setShowAddEmulatorTable(false);
      setNewTabName("");
      refreshData();
    } catch (err) {}
  };

  // Delete Emulator Table
  const handleDeleteEmulatorTable = async (id: number) => {
    try {
      await apiFetch(`/connections/emulator/tables/${id}`, { method: "DELETE" });
      showToast("Emulator table deleted");
      refreshData();
    } catch (err) {}
  };

  // Trigger Simulation Webhook
  const handleTriggerSimulation = async () => {
    setIsSimulating(true);
    try {
      const res = await apiFetch("/upload/simulate", {
        method: "POST",
        body: JSON.stringify({
          preset_name: presetName,
          target_table: targetTable,
          target_database: targetDatabase,
          processing_mode: processingMode,
          sheet_name: sheetName
        })
      });
      if (res) {
        showToast("Simulation triggered. Job created!");
        setSelectedJobId(res.id);
        setCurrentPage("job-detail");
      }
    } catch (err) {}
    setIsSimulating(false);
  };

  // Ingestion job retry
  const handleRetryJob = async (id: string) => {
    try {
      const res = await apiFetch(`/jobs/${id}/retry`, { method: "POST" });
      if (res) {
        showToast("Job retry scheduled successfully!");
        setSelectedJobId(res.job.id);
      }
    } catch (err) {}
  };

  // Ingestion job cancel
  const handleCancelJob = async (id: string) => {
    try {
      const res = await apiFetch(`/jobs/${id}/cancel`, { method: "POST" });
      if (res) {
        showToast("Job cancelled successfully.");
        setSelectedJobId(res.job.id);
      }
    } catch (err) {}
  };

  // Switch presets in simulator to match targets
  useEffect(() => {
    if (presetName === "missing_column" || presetName === "unexpected_column" || presetName === "type_error") {
      setTargetTable("user_activities");
      setTargetDatabase("default");
    } else if (presetName === "success") {
      setTargetTable("user_activities");
      setTargetDatabase("default");
    }
  }, [presetName]);

  if (!token) {
    return (
      <div className="login-container">
        <form className="login-card" onSubmit={handleLogin}>
          <div className="logo" style={{ justifyContent: 'center', marginBottom: '1.5rem' }}>
            <Database size={28} />
            <span>ClickHouse Ingestion</span>
          </div>
          <h2 style={{ textAlign: 'center', fontSize: '1.25rem', marginBottom: '1.5rem' }}>Enterprise Access</h2>
          
          {loginError && (
            <div style={{ backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.85rem', marginBottom: '1rem' }}>
              {loginError}
            </div>
          )}
          
          <div className="form-group">
            <label className="form-label">Username</label>
            <input 
              type="text" 
              className="form-input" 
              placeholder="e.g. admin" 
              value={username} 
              onChange={e => setUsername(e.target.value)} 
              required 
            />
          </div>
          
          <div className="form-group" style={{ marginBottom: '2rem' }}>
            <label className="form-label">Password</label>
            <input 
              type="password" 
              className="form-input" 
              placeholder="••••••••" 
              value={password} 
              onChange={e => setPassword(e.target.value)} 
              required 
            />
          </div>
          
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
            <Key size={16} /> Sign In
          </button>
          
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '1.5rem' }}>
            Demo: admin / admin123
          </p>
        </form>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Toast notifications */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type === 'danger' ? 'toast-danger' : 'toast-success'}`}>
            <span>{t.message}</span>
          </div>
        ))}
      </div>

      {/* Sidebar Nav */}
      <div className="sidebar">
        <div className="logo">
          <Database size={24} style={{ color: 'var(--primary)' }} />
          <span>ClickHouse Ingestion</span>
        </div>
        
        <nav className="nav-menu">
          <div className={`nav-item ${currentPage === 'overview' ? 'active' : ''}`} onClick={() => { setCurrentPage("overview"); setSelectedJobId(null); }}>
            <BarChart size={18} /> Overview
          </div>
          <div className={`nav-item ${currentPage === 'jobs' || currentPage === 'job-detail' ? 'active' : ''}`} onClick={() => { setCurrentPage("jobs"); setSelectedJobId(null); }}>
            <Activity size={18} /> Ingestion Jobs
          </div>
          <div className={`nav-item ${currentPage === 'connections' ? 'active' : ''}`} onClick={() => { setCurrentPage("connections"); setSelectedJobId(null); }}>
            <Database size={18} /> ClickHouse Engine
          </div>
          <div className={`nav-item ${currentPage === 'quarantine' ? 'active' : ''}`} onClick={() => { setCurrentPage("quarantine"); setSelectedJobId(null); }}>
            <ShieldAlert size={18} /> Quarantine
          </div>
          <div className={`nav-item ${currentPage === 'configuration' ? 'active' : ''}`} onClick={() => { setCurrentPage("configuration"); setSelectedJobId(null); }}>
            <Settings size={18} /> Rules Config
          </div>
          <div className={`nav-item ${currentPage === 'integration' ? 'active' : ''}`} onClick={() => { setCurrentPage("integration"); setSelectedJobId(null); }}>
            <Send size={18} /> Integration / PA Flow
          </div>
        </nav>
        
        <div className="sidebar-footer">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <span>User: {user?.username} ({user?.role})</span>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <span title="Toggle Theme" style={{ display: 'inline-flex', cursor: 'pointer' }} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              </span>
              <span title="Sign Out" style={{ display: 'inline-flex', cursor: 'pointer' }}>
                <LogOut size={16} onClick={handleLogout} />
              </span>
            </div>
          </div>
          <div>v1.0.0 (Prototype)</div>
        </div>
      </div>

      {/* Viewport content */}
      <div className="main-content">
        
        {/* OVERVIEW SCREEN */}
        {currentPage === 'overview' && (
          <div>
            <div className="page-header">
              <div>
                <h1 className="page-title">Operational Overview</h1>
                <p className="page-subtitle">Real-time monitoring of Outlook ingestion feeds & ClickHouse pipelines</p>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={refreshData}>
                <RefreshCw size={14} /> Refresh
              </button>
            </div>
            
            {/* Stats grid */}
            <div className="grid-stats">
              <div className="stat-card" onClick={() => { setCurrentPage("jobs"); setFilteredStatus(""); }}>
                <div className="stat-header">
                  <span className="stat-label">Total Pipeline runs</span>
                  <Activity size={18} style={{ color: 'var(--primary)' }} />
                </div>
                <div className="stat-value">{stats?.total_jobs || 0}</div>
                <div className="stat-desc">Success rate: {stats?.success_rate || 0}%</div>
              </div>
              
              <div className="stat-card" onClick={() => { setCurrentPage("jobs"); setFilteredStatus("COMPLETED"); }}>
                <div className="stat-header">
                  <span className="stat-label">Ingested Success</span>
                  <CheckCircle size={18} style={{ color: 'var(--success)' }} />
                </div>
                <div className="stat-value" style={{ color: 'var(--success)' }}>{stats?.success_jobs || 0}</div>
                <div className="stat-desc">Loaded safely into ClickHouse</div>
              </div>
              
              <div className="stat-card" onClick={() => { setCurrentPage("jobs"); setFilteredStatus("FAILED"); }}>
                <div className="stat-header">
                  <span className="stat-label">Validation Failures</span>
                  <XCircle size={18} style={{ color: 'var(--danger)' }} />
                </div>
                <div className="stat-value" style={{ color: 'var(--danger)' }}>{stats?.failed_jobs || 0}</div>
                <div className="stat-desc">Zero rows loaded (All-or-Nothing)</div>
              </div>

              <div className="stat-card" onClick={() => { setCurrentPage("quarantine"); }}>
                <div className="stat-header">
                  <span className="stat-label">Quarantined Files</span>
                  <ShieldAlert size={18} style={{ color: 'var(--warning)' }} />
                </div>
                <div className="stat-value" style={{ color: 'var(--warning)' }}>{stats?.quarantined_jobs || 0}</div>
                <div className="stat-desc">Awaiting operator template fix</div>
              </div>

              <div className="stat-card" onClick={() => { setCurrentPage("integration"); }}>
                <div className="stat-header">
                  <span className="stat-label">Reconcile Alerts</span>
                  <AlertTriangle size={18} style={{ color: stats?.discrepancy_count > 0 ? 'var(--danger)' : 'var(--text-muted)' }} />
                </div>
                <div className="stat-value" style={{ color: stats?.discrepancy_count > 0 ? 'var(--danger)' : 'var(--text-primary)' }}>
                  {stats?.discrepancy_count || 0}
                </div>
                <div className="stat-desc">Row count discrepancies</div>
              </div>
            </div>

            {/* Custom SVG Charts */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
              <div className="table-container" style={{ padding: '1.5rem' }}>
                <h3 className="table-title" style={{ marginBottom: '1rem' }}>Total Ingested Rows Over Time</h3>
                <div className="custom-bar-chart">
                  <div className="chart-bar-container">
                    <div className="chart-bar" style={{ height: '30%' }}></div>
                    <span className="chart-label">Mon</span>
                  </div>
                  <div className="chart-bar-container">
                    <div className="chart-bar" style={{ height: '55%' }}></div>
                    <span className="chart-label">Tue</span>
                  </div>
                  <div className="chart-bar-container">
                    <div className="chart-bar" style={{ height: '80%' }}></div>
                    <span className="chart-label">Wed (Today)</span>
                  </div>
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Active databases loaded: <b>{stats?.inserted_rows || 0}</b> rows total.
                </p>
              </div>

              <div className="table-container" style={{ padding: '1.5rem' }}>
                <h3 className="table-title" style={{ marginBottom: '1rem' }}>Top Failure Reasons</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
                  {stats?.top_failures && stats.top_failures.length > 0 ? (
                    stats.top_failures.map((f: any, idx: number) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
                        <span style={{ color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '280px' }} title={f.reason}>
                          {f.reason}
                        </span>
                        <span className="badge badge-danger">{f.count} counts</span>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state" style={{ padding: '1rem' }}>No validation failures reported yet.</div>
                  )}
                </div>
              </div>
            </div>

            {/* Recent Jobs table */}
            <div className="table-container">
              <div className="table-header-row">
                <h3 className="table-title">Recent Ingestion Workflows</h3>
                <button className="btn btn-secondary btn-sm" onClick={() => setCurrentPage("jobs")}>View All</button>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Email Subject</th>
                    <th>Attachment Name</th>
                    <th>Target Table</th>
                    <th>Rows Inserted</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {stats?.recent_jobs && stats.recent_jobs.length > 0 ? (
                    stats.recent_jobs.map((job: any) => (
                      <tr key={job.id}>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{job.id}</td>
                        <td style={{ color: 'var(--text-secondary)' }}>{job.subject}</td>
                        <td>{job.attachment_name}</td>
                        <td>{job.target_database}.{job.target_table}</td>
                        <td>{job.inserted_rows} / {job.total_rows}</td>
                        <td>
                          <span className={`badge ${
                            job.status === 'COMPLETED' ? 'badge-success' : 
                            job.status === 'QUARANTINED' || job.status === 'FAILED' ? 'badge-danger' : 
                            'badge-info'
                          }`}>{job.status}</span>
                        </td>
                        <td>
                          <button className="btn btn-secondary btn-sm" onClick={() => { setSelectedJobId(job.id); setCurrentPage("job-detail"); }}>
                            Inspect <ChevronRight size={12} />
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7}><div className="empty-state">No jobs processed yet. Trigger a simulated request on the Integration tab.</div></td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* JOBS SCREEN */}
        {currentPage === 'jobs' && (
          <div>
            <div className="page-header">
              <div>
                <h1 className="page-title">Data Ingestion Jobs</h1>
                <p className="page-subtitle">Track, filter, and audit all incoming Excel template pipelines</p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <select 
                  className="form-input" 
                  style={{ width: '160px', padding: '0.5rem' }} 
                  value={filteredStatus} 
                  onChange={e => setFilteredStatus(e.target.value)}
                >
                  <option value="">All Statuses</option>
                  <option value="COMPLETED">Completed</option>
                  <option value="FAILED">Failed</option>
                  <option value="QUARANTINED">Quarantined</option>
                  <option value="INSERTING">Inserting</option>
                </select>
                <button className="btn btn-secondary btn-sm" onClick={refreshData}>
                  <RefreshCw size={14} />
                </button>
              </div>
            </div>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Sender</th>
                    <th>Attachment</th>
                    <th>Target DB.Table</th>
                    <th>Sheet</th>
                    <th>Total / Ingested</th>
                    <th>Status</th>
                    <th>Reconcile</th>
                    <th>Created</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.length > 0 ? (
                    jobs.map((job: any) => (
                      <tr key={job.id}>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{job.id}</td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{job.sender}</td>
                        <td style={{ fontWeight: 500 }}>{job.attachment_name}</td>
                        <td>{job.target_database}.{job.target_table}</td>
                        <td style={{ color: 'var(--text-secondary)' }}>{job.sheet_name}</td>
                        <td>{job.total_rows} / {job.inserted_rows}</td>
                        <td>
                          <span className={`badge ${
                            job.status === 'COMPLETED' ? 'badge-success' : 
                            job.status === 'QUARANTINED' || job.status === 'FAILED' ? 'badge-danger' : 
                            'badge-info'
                          }`}>{job.status}</span>
                        </td>
                        <td>
                          <span className={`badge ${
                            job.reconciliation_status === 'MATCHED' ? 'badge-success' :
                            job.reconciliation_status === 'MISMATCHED' ? 'badge-danger' :
                            'badge-warning'
                          }`}>{job.reconciliation_status}</span>
                        </td>
                        <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {new Date(job.created_at).toLocaleTimeString()}
                        </td>
                        <td>
                          <button className="btn btn-secondary btn-sm" onClick={() => { setSelectedJobId(job.id); setCurrentPage("job-detail"); }}>
                            Detail
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={10}><div className="empty-state">No Ingestion jobs found matching this status.</div></td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* JOB DETAIL SCREEN */}
        {currentPage === 'job-detail' && jobDetail && (
          <div>
            <div className="page-header" style={{ marginBottom: '1.5rem' }}>
              <div>
                <button className="btn btn-secondary btn-sm" style={{ marginBottom: '0.75rem' }} onClick={() => setCurrentPage("jobs")}>
                  ← Back to Ingestion Jobs
                </button>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <h1 className="page-title">Job {jobDetail.id}</h1>
                  <span className={`badge ${
                    jobDetail.status === 'COMPLETED' ? 'badge-success' : 
                    jobDetail.status === 'QUARANTINED' || jobDetail.status === 'FAILED' ? 'badge-danger' : 
                    'badge-info'
                  }`}>{jobDetail.status}</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                {(jobDetail.status === 'QUARANTINED' || jobDetail.status === 'FAILED') && (
                  <>
                    <button className="btn btn-primary" onClick={() => handleRetryJob(jobDetail.id)}>
                      <RefreshCw size={14} /> Retry Job
                    </button>
                    <button className="btn btn-danger" onClick={() => handleCancelJob(jobDetail.id)}>
                      <X size={14} /> Cancel Ingestion
                    </button>
                  </>
                )}
              </div>
            </div>

            <div className="job-details-grid">
              
              {/* Left pane: Ingestion Metadata, schemas, validation errors */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                
                {/* Email Info */}
                <div className="table-container" style={{ padding: '1.5rem' }}>
                  <h3 className="table-title" style={{ marginBottom: '1rem' }}>Email Ingestion Metadata</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', fontSize: '0.875rem' }}>
                    <div>
                      <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>From:</span> {jobDetail.sender}</div>
                      <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>Subject:</span> {jobDetail.subject}</div>
                      <div><span style={{ color: 'var(--text-secondary)' }}>Correlation ID:</span> <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{jobDetail.correlation_id}</span></div>
                    </div>
                    <div>
                      <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>File Attachment:</span> {jobDetail.attachment_name} ({Math.round(jobDetail.attachment_size / 1024)} KB)</div>
                      <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>Target Database/Table:</span> <b>{jobDetail.target_database}.{jobDetail.target_table}</b></div>
                      <div><span style={{ color: 'var(--text-secondary)' }}>Sheet Mapping:</span> {jobDetail.sheet_name}</div>
                    </div>
                  </div>
                </div>

                {/* Validation Errors report */}
                {jobDetail.validation_errors && jobDetail.validation_errors.length > 0 && (
                  <div className="table-container" style={{ borderColor: 'var(--danger-border)', borderLeft: '4px solid var(--danger)' }}>
                    <div className="table-header-row" style={{ backgroundColor: 'var(--danger-bg)' }}>
                      <h3 className="table-title" style={{ color: 'var(--danger)' }}>Validation Failures & Schema Mismatches</h3>
                      <span className="badge badge-danger">{jobDetail.validation_errors.length} Errors Found</span>
                    </div>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Row #</th>
                          <th>Column Name</th>
                          <th>Expected Type</th>
                          <th>Cell Value</th>
                          <th>Error Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {jobDetail.validation_errors.map((err: any) => (
                          <tr key={err.id}>
                            <td>{err.row_number || "Schema Level"}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{err.column_name || "N/A"}</td>
                            <td><span className="badge badge-info">{err.expected_type || "N/A"}</span></td>
                            <td style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{err.actual_value || "N/A"}</td>
                            <td style={{ color: 'var(--danger)', fontWeight: 500 }}>{err.error_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Schema side-by-side comparison */}
                <div className="table-container" style={{ padding: '1.5rem' }}>
                  <h3 className="table-title" style={{ marginBottom: '1rem' }}>Excel vs ClickHouse Target Column Mapping</h3>
                  
                  {jobDetail.status === 'EMAIL_RECEIVED' || jobDetail.status === 'JOB_CREATED' ? (
                    <div className="empty-state">Discovery schema mapping loading...</div>
                  ) : (
                    <div className="schema-comparison">
                      <div className="schema-box">
                        <h4 style={{ fontSize: '0.9rem', marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>Excel Headers (Normalized)</h4>
                        {/* We simulate schema if missing */}
                        <div className="schema-list-item" style={{ fontWeight: 600 }}>
                          <span>Column Name</span>
                          <span>Inferred Type</span>
                        </div>
                        {jobDetail.validation_errors && jobDetail.validation_errors.some((e: any) => e.error_reason.includes("Required ClickHouse column")) ? (
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', padding: '0.5rem 0' }}>Excel lacks required columns.</div>
                        ) : (
                          <>
                            <div className="schema-list-item"><span>id</span><span>Int64</span></div>
                            <div className="schema-list-item"><span>user_id</span><span>String</span></div>
                            <div className="schema-list-item"><span>activity</span><span>String</span></div>
                            <div className="schema-list-item"><span>timestamp</span><span>DateTime</span></div>
                          </>
                        )}
                      </div>

                      <div className="schema-box">
                        <h4 style={{ fontSize: '0.9rem', marginBottom: '0.75rem', color: 'var(--text-secondary)' }}>ClickHouse Table Columns</h4>
                        <div className="schema-list-item" style={{ fontWeight: 600 }}>
                          <span>Column Name</span>
                          <span>ClickHouse Type</span>
                        </div>
                        <div className="schema-list-item"><span>id</span><span>UInt32</span></div>
                        <div className="schema-list-item"><span>user_id</span><span>String</span></div>
                        <div className="schema-list-item"><span>activity</span><span>String</span></div>
                        <div className="schema-list-item"><span>timestamp</span><span>DateTime</span></div>
                      </div>
                    </div>
                  )}
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Validation checking Mode: <b>{jobDetail.processing_mode}</b>. All data values must strictly match the database constraints.
                  </p>
                </div>

                {/* Audit Reconciliation detail */}
                {jobDetail.reconciliation_runs && jobDetail.reconciliation_runs.length > 0 && (
                  <div className="table-container" style={{ padding: '1.5rem' }}>
                    <h3 className="table-title" style={{ marginBottom: '1rem' }}>Power Automate Reconciliation Report</h3>
                    {jobDetail.reconciliation_runs.map((run: any) => (
                      <div key={run.id} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', fontSize: '0.875rem' }}>
                        <div>
                          <div style={{ marginBottom: '0.5rem' }}>Status: 
                            <span className={`badge ${run.match_status === 'MATCHED' ? 'badge-success' : 'badge-danger'}`} style={{ marginLeft: '0.5rem' }}>
                              {run.match_status}
                            </span>
                          </div>
                          <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>Power Automate Count:</span> {run.pa_row_count} rows</div>
                          <div><span style={{ color: 'var(--text-secondary)' }}>ClickHouse Inserted Count:</span> {run.backend_row_count} rows</div>
                        </div>
                        <div>
                          <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>Reconciled On:</span> {new Date(run.run_timestamp).toLocaleString()}</div>
                          {run.discrepancy_details && (
                            <div style={{ color: 'var(--danger)', fontWeight: 500 }}>
                              <span style={{ color: 'var(--text-secondary)' }}>Mismatches:</span><br/>
                              {run.discrepancy_details}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Right pane: Pipeline timeline */}
              <div>
                <div className="table-container" style={{ padding: '1.5rem' }}>
                  <h3 className="table-title" style={{ marginBottom: '1.25rem' }}>Ingestion Pipeline Timeline</h3>
                  
                  <div className="timeline-container">
                    {jobDetail.state_history && jobDetail.state_history.map((hist: any, index: number) => {
                      const isActive = index === jobDetail.state_history.length - 1;
                      const isErr = hist.new_state === 'FAILED' || hist.new_state === 'QUARANTINED';
                      const isSuccess = hist.new_state === 'COMPLETED';
                      
                      let dotClass = "timeline-dot";
                      if (isErr) dotClass += " danger";
                      else if (isSuccess) dotClass += " success";
                      else if (isActive) dotClass += " active";
                      
                      return (
                        <div key={hist.id} className="timeline-item">
                          <div className={dotClass}></div>
                          <div className="timeline-time">
                            {new Date(hist.timestamp).toLocaleTimeString()} ({hist.actor})
                          </div>
                          <div className="timeline-content" style={{ fontWeight: isActive ? 600 : 400 }}>
                            {hist.new_state}
                          </div>
                          {hist.reason && (
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                              {hist.reason}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

            </div>
          </div>
        )}

        {/* CLICKHOUSE ENGINE CONFIG & EMULATOR */}
        {currentPage === 'connections' && (
          <div>
            <div className="page-header">
              <div>
                <h1 className="page-title">ClickHouse Database Connection</h1>
                <p className="page-subtitle">Configure connection pools, discover tables, and manage the local ClickHouse Emulator</p>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1.5rem' }}>
              
              {/* Connection configuration form */}
              <div className="table-container" style={{ padding: '1.5rem' }}>
                <h3 className="table-title" style={{ marginBottom: '1.25rem' }}>Connection Parameters</h3>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label">Connection Name</label>
                    <input type="text" className="form-input" value={chName} onChange={e => setChName(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Host URL</label>
                    <input type="text" className="form-input" value={chHost} onChange={e => setChHost(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Connection Port</label>
                    <input type="number" className="form-input" value={chPort} onChange={e => setChPort(Number(e.target.value))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Username</label>
                    <input type="text" className="form-input" value={chUser} onChange={e => setChUser(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Password</label>
                    <input type="password" className="form-input" placeholder="••••••••" value={chPass} onChange={e => setChPass(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Restrict Databases</label>
                    <input type="text" className="form-input" value="default, analytics, production" disabled />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
                  <button className="btn btn-primary" onClick={handleTestConnection}>Test Connection</button>
                  <button className="btn btn-secondary" onClick={() => showToast("Parameters saved in session")}>Save Connection</button>
                </div>

                {testResult && (
                  <div style={{ 
                    marginTop: '1.5rem', 
                    padding: '1rem', 
                    borderRadius: '0.5rem', 
                    fontSize: '0.85rem',
                    fontFamily: 'var(--font-mono)',
                    backgroundColor: testResult.includes("successfully") ? 'var(--success-bg)' : 'var(--danger-bg)',
                    border: `1px solid ${testResult.includes("successfully") ? 'var(--success-border)' : 'var(--danger-border)'}`,
                    color: testResult.includes("successfully") ? 'var(--success)' : 'var(--danger)'
                  }}>
                    {testResult}
                  </div>
                )}
              </div>

              {/* ClickHouse database Emulator tables management */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <div className="table-container" style={{ padding: '1.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                    <h3 className="table-title">ClickHouse Emulator Tables</h3>
                    <button className="btn btn-primary btn-sm" onClick={() => setShowAddEmulatorTable(!showAddEmulatorTable)}>
                      + Create Table
                    </button>
                  </div>

                  {showAddEmulatorTable && (
                    <div style={{ border: '1px solid var(--border-color)', borderRadius: '0.5rem', padding: '1rem', marginBottom: '1.25rem', backgroundColor: 'rgba(18, 24, 38, 0.4)' }}>
                      <h4 style={{ fontSize: '0.85rem', marginBottom: '0.75rem' }}>Define Mock ClickHouse Target Table</h4>
                      
                      <div className="form-group">
                        <label className="form-label">Database Name</label>
                        <select className="form-input" value={newTabDb} onChange={e => setNewTabDb(e.target.value)}>
                          <option value="default">default</option>
                          <option value="analytics">analytics</option>
                          <option value="production">production</option>
                        </select>
                      </div>

                      <div className="form-group" style={{ marginBottom: '1.25rem' }}>
                        <label className="form-label">Table Name</label>
                        <select className="form-input" value={newTabName} onChange={e => setNewTabName(e.target.value)}>
                          <option value="">-- Select template --</option>
                          <option value="user_activities">user_activities (UInt32 id, String user_id, String activity, DateTime timestamp)</option>
                          <option value="user_data_index">user_data_index (UInt32 id, String email, String status, Date created_at)</option>
                        </select>
                      </div>

                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button className="btn btn-primary btn-sm" onClick={handleCreateEmulatorTable} disabled={!newTabName}>Create</button>
                        <button className="btn btn-secondary btn-sm" onClick={() => setShowAddEmulatorTable(false)}>Cancel</button>
                      </div>
                    </div>
                  )}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                    {emulatorTables.length > 0 ? (
                      emulatorTables.map((t: any) => (
                        <div key={t.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{t.database}.{t.table_name}</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              Rows loaded: <b>{t.row_count}</b> | Columns: {t.schema_json.length}
                            </div>
                          </div>
                          <button className="btn btn-danger btn-sm" style={{ padding: '0.25rem 0.5rem' }} onClick={() => handleDeleteEmulatorTable(t.id)}>
                            Delete
                          </button>
                        </div>
                      ))
                    ) : (
                      <div className="empty-state" style={{ padding: '2rem' }}>No mock tables in emulator. Create one to test pipelines!</div>
                    )}
                  </div>
                </div>
              </div>

            </div>
          </div>
        )}

        {/* WORKFLOW RULE CONFIGURATION */}
        {currentPage === 'configuration' && (
          <div>
            <div className="page-header">
              <div>
                <h1 className="page-title">Workflow Rules Configuration</h1>
                <p className="page-subtitle">Route incoming email attachments based on subject headers, senders, and validation settings</p>
              </div>
            </div>

            <div className="table-container" style={{ padding: '1.5rem' }}>
              <h3 className="table-title" style={{ marginBottom: '1.25rem' }}>Configured Routing Protocols</h3>
              
              {workflows.map((wf: any) => (
                <div key={wf.id} style={{ border: '1px solid var(--border-color)', borderRadius: '0.75rem', padding: '1.5rem', marginBottom: '1rem', backgroundColor: 'rgba(18, 24, 38, 0.2)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <h4 style={{ fontWeight: 600, fontSize: '1.1rem', color: 'var(--primary)' }}>{wf.name}</h4>
                    <span className="badge badge-success">{wf.mode} validation mode</span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', fontSize: '0.9rem' }}>
                    <div>
                      <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>Subject Regex Pattern:</span> <code>{wf.email_subject_pattern}</code></div>
                      <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>Attachment Glob:</span> <code>{wf.attachment_pattern}</code></div>
                    </div>
                    <div>
                      <div style={{ marginBottom: '0.5rem' }}><span style={{ color: 'var(--text-secondary)' }}>Allowed Senders:</span> <code>{wf.allowed_senders}</code></div>
                      <div><span style={{ color: 'var(--text-secondary)' }}>Extraction Match rule:</span> <code>table: \s*([a-zA-Z0-9_]+)</code></div>
                    </div>
                  </div>
                </div>
              ))}
              
              <button className="btn btn-secondary" onClick={() => showToast("Rule configurations locked for prototype")}>
                + Register New Rule Config
              </button>
            </div>
          </div>
        )}

        {/* QUARANTINE MANAGER */}
        {currentPage === 'quarantine' && (
          <div>
            <div className="page-header">
              <div>
                <h1 className="page-title">Quarantine & Recovery Center</h1>
                <p className="page-subtitle">Inspect schema violation audits, review row-level errors, and download templates</p>
              </div>
            </div>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Quarantined File</th>
                    <th>Errors</th>
                    <th>Target Table</th>
                    <th>Quarantined Date</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.filter((j: any) => j.status === 'QUARANTINED' || j.status === 'FAILED').length > 0 ? (
                    jobs.filter((j: any) => j.status === 'QUARANTINED' || j.status === 'FAILED').map((job: any) => (
                      <tr key={job.id}>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{job.id}</td>
                        <td style={{ color: 'var(--danger)', fontWeight: 500 }}>
                          {job.attachment_name}
                        </td>
                        <td>
                          <span className="badge badge-danger">{job.invalid_rows} row errors</span>
                        </td>
                        <td>{job.target_database}.{job.target_table}</td>
                        <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {new Date(job.created_at).toLocaleString()}
                        </td>
                        <td style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className="btn btn-primary btn-sm" onClick={() => handleRetryJob(job.id)}>
                            Retry
                          </button>
                          <button className="btn btn-secondary btn-sm" onClick={() => { setSelectedJobId(job.id); setCurrentPage("job-detail"); }}>
                            Inspect
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}><div className="empty-state">No files are currently quarantined. Nice work!</div></td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* PA / INTEGRATION FLOW SIMULATOR */}
        {currentPage === 'integration' && (
          <div>
            <div className="page-header">
              <div>
                <h1 className="page-title">Outlook / Power Automate Integration</h1>
                <p className="page-subtitle">Configure webhook endpoints, audit reconciliation checks, and trigger simulations</p>
              </div>
            </div>

            {/* Direct Microsoft 365 Integration Dashboard card */}
            <div className="table-container" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
              <h3 className="table-title" style={{ marginBottom: '0.75rem' }}>Microsoft Account Connection (Auto-flow & Webhook Setup)</h3>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
                Optionally authenticate directly with your Microsoft Office 365 account to let the Ingestion Gateway automatically register webhook subscriptions, poll mail folders, and load Excel workbooks without manually configuring Power Automate flows.
              </p>
              
              {msStatus?.connected ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: '0.5rem' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span className="badge badge-success">CONNECTED</span>
                      <strong style={{ fontSize: '0.9rem' }}>{msStatus.email}</strong>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                      Auto-Polling active checking every 20 seconds. Token Expiry: {msStatus.expires_at ? new Date(msStatus.expires_at).toLocaleString() : "N/A"}
                    </div>
                  </div>
                  <button className="btn btn-secondary btn-sm" onClick={handleMsDisconnect}>
                    Disconnect Account
                  </button>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: '0.5rem' }}>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    No Microsoft Account currently connected. Click the button to authorize access.
                  </div>
                  <button className="btn btn-primary" onClick={() => { window.location.href = "http://localhost:8081/api/auth/microsoft/login"; }}>
                    Connect Microsoft Account
                  </button>
                </div>
              )}
            </div>

            {/* Integration Status & Stats Widgets */}
            <div className="grid-stats" style={{ marginBottom: '1.5rem' }}>
              <div className="stat-card" style={{ padding: '1rem' }}>
                <span className="stat-label" style={{ fontSize: '0.75rem' }}>Integration Link</span>
                <div style={{ marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className="badge badge-success">ACTIVE</span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>O365 Mail Listener</span>
                </div>
              </div>
              <div className="stat-card" style={{ padding: '1rem' }}>
                <span className="stat-label" style={{ fontSize: '0.75rem' }}>Auth Protocol</span>
                <div style={{ marginTop: '0.25rem', fontSize: '0.85rem', fontWeight: 600 }}>Header Token Check</div>
              </div>
              <div className="stat-card" style={{ padding: '1rem' }}>
                <span className="stat-label" style={{ fontSize: '0.75rem' }}>Last Webhook Event</span>
                <div style={{ marginTop: '0.25rem', fontSize: '0.8rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                  {jobs.length > 0 ? `${jobs[0].id} (${new Date(jobs[0].created_at).toLocaleTimeString()})` : "No events"}
                </div>
              </div>
              <div className="stat-card" style={{ padding: '1rem' }}>
                <span className="stat-label" style={{ fontSize: '0.75rem' }}>Reconciliation Check</span>
                <div style={{ marginTop: '0.25rem', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className="badge badge-info">ENABLED</span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Row Verification</span>
                </div>
              </div>
            </div>

            {/* Recent Workflow Requests */}
            <div className="table-container" style={{ marginBottom: '1.5rem' }}>
              <div className="table-header-row" style={{ padding: '1rem 1.5rem' }}>
                <h3 className="table-title" style={{ fontSize: '0.95rem' }}>Recent Workflow Requests (Power Automate Webhooks)</h3>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Message ID</th>
                    <th>Destination Table</th>
                    <th>Rows Inserted</th>
                    <th>Reconciliation</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.length > 0 ? (
                    jobs.slice(0, 3).map((job: any) => (
                      <tr key={job.id}>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{job.id}</td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{job.email_id || "N/A"}</td>
                        <td>{job.target_database}.{job.target_table}</td>
                        <td>{job.inserted_rows} / {job.total_rows}</td>
                        <td>
                          <span className={`badge ${
                            job.reconciliation_status === 'MATCHED' ? 'badge-success' :
                            job.reconciliation_status === 'MISMATCHED' ? 'badge-danger' :
                            'badge-warning'
                          }`}>{job.reconciliation_status}</span>
                        </td>
                        <td>
                          <span className={`badge ${
                            job.status === 'COMPLETED' ? 'badge-success' : 
                            job.status === 'QUARANTINED' || job.status === 'FAILED' ? 'badge-danger' : 
                            'badge-info'
                          }`}>{job.status}</span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}><div className="empty-state">No workflow webhook events recorded yet.</div></td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1.5rem' }}>
              
              {/* Simulator launcher */}
              <div className="table-container" style={{ padding: '1.5rem' }}>
                <h3 className="table-title" style={{ marginBottom: '1.25rem' }}>Simulated Ingestion Trigger</h3>
                
                <div className="form-group">
                  <label className="form-label">Select Testing Scenario Preset</label>
                  <select className="form-input" value={presetName} onChange={e => setPresetName(e.target.value)}>
                    <option value="success">Success Scenario (Correct headers, types, and values)</option>
                    <option value="missing_column">Schema Error: Missing Column (Required ClickHouse 'user_id' omitted)</option>
                    <option value="unexpected_column">Schema Error: Unexpected Column (Excel contains 'bonus_points' in STRICT mode)</option>
                    <option value="type_error">Data Error: Row Value Invalid Type (Row 2 has string 'abc' in integer column)</option>
                  </select>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label">Target Database</label>
                    <input type="text" className="form-input" value={targetDatabase} onChange={e => setTargetDatabase(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Target Table</label>
                    <input type="text" className="form-input" value={targetTable} onChange={e => setTargetTable(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Workbook Sheet Name</label>
                    <input type="text" className="form-input" value={sheetName} onChange={e => setSheetName(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Validation Checking Mode</label>
                    <select className="form-input" value={processingMode} onChange={e => setProcessingMode(e.target.value)}>
                      <option value="STRICT">STRICT (Fail on warnings/mismatches)</option>
                      <option value="RELAXED">RELAXED (Skip/warn only)</option>
                      <option value="DRY_RUN">DRY_RUN (Profile & check only, insert zero rows)</option>
                    </select>
                  </div>
                </div>

                <button className="btn btn-primary" style={{ marginTop: '1.5rem', width: '100%' }} onClick={handleTriggerSimulation} disabled={isSimulating}>
                  {isSimulating ? "Processing flow..." : "Trigger Simulated Power Automate Ingestion"}
                </button>
              </div>

              {/* Notification & email logger inspector */}
              <div className="table-container" style={{ padding: '1.5rem' }}>
                <h3 className="table-title" style={{ marginBottom: '1.25rem' }}>Mock Email Notification logs</h3>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxHeight: '420px', overflowY: 'auto' }}>
                  {notifications.length > 0 ? (
                    notifications.map((n: any, idx: number) => (
                      <div key={idx} style={{ 
                        border: '1px solid var(--border-color)', 
                        borderRadius: '0.5rem', 
                        padding: '1rem', 
                        fontSize: '0.85rem',
                        backgroundColor: n.email_type.includes("SUCCESS") ? 'var(--success-bg)' : 'var(--danger-bg)'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                          <span style={{ fontWeight: 600 }}>Recipient: {n.recipient}</span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                            {new Date(n.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                        <div style={{ fontWeight: 500, marginBottom: '0.5rem', color: 'var(--text-primary)' }}>
                          Subject: {n.subject}
                        </div>
                        <pre style={{ 
                          whiteSpace: 'pre-wrap', 
                          fontSize: '0.75rem', 
                          fontFamily: 'var(--font-sans)', 
                          color: 'var(--text-secondary)',
                          maxHeight: '120px',
                          overflowY: 'auto'
                        }}>
                          {n.body}
                        </pre>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state" style={{ padding: '2rem' }}>No email notifications sent yet. Trigger a simulated pipeline first.</div>
                  )}
                </div>
              </div>

            </div>

            {/* Contract instructions */}
            <div className="table-container" style={{ padding: '1.5rem', marginTop: '1.5rem' }}>
              <h3 className="table-title" style={{ marginBottom: '1rem' }}>Webhook API Contract & Specifications</h3>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
                Microsoft Power Automate connects to the gateway securely using two backend endpoints. Ensure you use the exact headers and JSON schemas below.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                <div>
                  <h4 style={{ fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--primary)' }}>1. File Ingestion Webhook (POST /api/upload/webhook)</h4>
                  <pre style={{ backgroundColor: 'var(--bg-secondary)', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', marginBottom: '0.75rem' }}>
{`X-API-KEY: PA-Secure-Token-12345
Content-Type: application/json`}
                  </pre>
                  <pre style={{ backgroundColor: 'var(--bg-secondary)', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', maxHeight: '250px', overflowY: 'auto' }}>
{`{
  "email_id": "Outlook-Message-ID-2026",
  "sender": "sender@company.com",
  "subject": "Ingestion: table: user_activities",
  "received_time": "2026-07-14T14:00:00Z",
  "attachment_name": "users_data.xlsx",
  "file_content_base64": "UEsDBBQABgAIAAAAIQ...",
  "target_table": "user_activities",
  "target_database": "AUTO",
  "processing_mode": "STRICT",
  "sheet_name": "Sheet1"
}`}
                  </pre>
                </div>

                <div>
                  <h4 style={{ fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--primary)' }}>2. Audit Reconciliation Webhook (POST /api/reconciliation)</h4>
                  <pre style={{ backgroundColor: 'var(--bg-secondary)', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', marginBottom: '0.75rem' }}>
{`X-API-KEY: PA-Secure-Token-12345
Content-Type: application/json`}
                  </pre>
                  <pre style={{ backgroundColor: 'var(--bg-secondary)', padding: '0.75rem', borderRadius: '0.5rem', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', maxHeight: '250px', overflowY: 'auto' }}>
{`{
  "ingestion_job_id": "job_123456abcdef",
  "email_id": "Outlook-Message-ID-2026",
  "attachment_hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b...",
  "target_database": "default",
  "target_table": "user_activities",
  "expected_row_count": 120,
  "status": "COMPLETED"
}`}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
