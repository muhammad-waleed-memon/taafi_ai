/* Copyright 2026 Muhammad Waleed & Areeba
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * 
 *     http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React, { useEffect, useState } from 'react';
import ConsoleTerminal from './components/ConsoleTerminal';

export default function App() {
  const [incidents, setIncidents] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [comments, setComments] = useState({});
  const [metrics, setMetrics] = useState({
    trapped: 0,
    unresolved: 0,
    resolved: 0
  });

  const fetchIncidents = async () => {
    try {
      const res = await fetch('/api/incidents');
      if (res.ok) {
        const data = await res.json();
        setIncidents(data);
        
        // Calculate metrics from structured incident log
        let trapped = 0;
        let unresolved = 0;
        let resolved = 0;
        
        data.forEach(item => {
          const details = item.details || {};
          trapped++;
          if (details.status === 'RESOLVED' || item.category === 'REMEDIATION_COMPLETED') {
            resolved++;
          } else if (details.status === 'UNRESOLVED' || details.status === 'QUEUED_FOR_REMEDIATION') {
            unresolved++;
          }
        });

        setMetrics({ trapped, unresolved, resolved });
      }
    } catch (err) {
      console.error('Failed to pull incidents list:', err);
    }
  };

  const fetchApprovals = async () => {
    try {
      const res = await fetch('/api/approvals');
      if (res.ok) {
        const data = await res.json();
        setApprovals(data);
      }
    } catch (err) {
      console.error('Failed to pull approvals list:', err);
    }
  };

  useEffect(() => {
    fetchIncidents();
    fetchApprovals();
    const interval = setInterval(() => {
      fetchIncidents();
      fetchApprovals();
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const triggerDeadlockSimulation = async () => {
    try {
      const res = await fetch('/api/incidents/simulate', {
        method: 'POST'
      });
      if (res.ok) {
        fetchIncidents();
        fetchApprovals();
      }
    } catch (err) {
      console.error('Failed to trigger deadlock simulation:', err);
    }
  };

  const handleApprove = async (approvalId) => {
    const comment = comments[approvalId] || '';
    try {
      const res = await fetch(`/api/approvals/${approvalId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment })
      });
      if (res.ok) {
        fetchApprovals();
        fetchIncidents();
        // Clear comment
        setComments(prev => ({ ...prev, [approvalId]: '' }));
      }
    } catch (err) {
      console.error('Failed to approve patch:', err);
    }
  };

  const handleReject = async (approvalId) => {
    const comment = comments[approvalId] || '';
    try {
      const res = await fetch(`/api/approvals/${approvalId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment })
      });
      if (res.ok) {
        fetchApprovals();
        fetchIncidents();
        // Clear comment
        setComments(prev => ({ ...prev, [approvalId]: '' }));
      }
    } catch (err) {
      console.error('Failed to reject patch:', err);
    }
  };

  const handleCommentChange = (approvalId, text) => {
    setComments(prev => ({ ...prev, [approvalId]: text }));
  };

  return (
    <div className="dashboard-container">
      {/* SRE Top Navigation Header */}
      <header className="header">
        <div className="brand-section">
          <h1 className="brand-title">Taafi.ai</h1>
          <span className="brand-badge">Autopilot SRE Agent v2.0</span>
        </div>
        <button className="btn-simulate" onClick={triggerDeadlockSimulation}>
          ⚡ Trigger DB Deadlock Simulation
        </button>
      </header>

      {/* SRE Metrics Row */}
      <section className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">Deadlocks Trapped</div>
          <div className="metric-value" style={{ color: 'var(--amber)' }}>{metrics.trapped}</div>
          <div className="metric-indicator indicator-active"></div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Active Waiting Collisions</div>
          <div className="metric-value" style={{ color: 'var(--rose)' }}>{metrics.unresolved}</div>
          <div className="metric-indicator" style={{ backgroundColor: 'var(--rose)', boxShadow: '0 0 10px var(--rose)' }}></div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Patches Hot-Deployed</div>
          <div className="metric-value" style={{ color: 'var(--emerald)' }}>{metrics.resolved}</div>
          <div className="metric-indicator indicator-success"></div>
        </div>
        <div className="metric-card">
          <div className="metric-label">SLA Remediation Speed</div>
          <div className="metric-value" style={{ color: 'var(--cyan)' }}>&lt; 2.5s</div>
          <div className="metric-indicator indicator-active"></div>
        </div>
      </section>

      {/* SRE Main Grid Area */}
      <main className="main-grid">
        {/* Left Side - Trapped Lock Incidents */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">🛡️ Trapped Deadlock Graphs</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Polling Live</span>
          </div>
          <div className="incidents-list">
            {incidents.filter(inc => inc.category === 'DEADLOCK_TRAPPED').length === 0 ? (
              <div style={{ color: 'var(--text-secondary)', textAlign: 'center', marginTop: '3rem' }}>
                No active deadlock lock circular waits trapped in connection pool. Click simulation button to start.
              </div>
            ) : (
              incidents
                .filter(inc => inc.category === 'DEADLOCK_TRAPPED')
                .map((incident, index) => {
                  const details = incident.details || {};
                  const isResolved = !incidents.some(i => i.category === 'DEADLOCK_TRAPPED' && (i.details?.status === 'UNRESOLVED' || i.details?.status === 'QUEUED_FOR_REMEDIATION') && i.details?.incident_id === details.incident_id);

                  return (
                    <div key={index} className={`incident-card ${isResolved ? 'resolved' : 'unresolved'}`}>
                      <div className="incident-card-header">
                        <span className="incident-id">{details.incident_id}</span>
                        <span className={`status-badge ${isResolved ? 'resolved' : 'unresolved'}`}>
                          {isResolved ? 'RESOLVED' : 'WAITING_COLLISION'}
                        </span>
                      </div>
                      
                      <div className="query-label">Target DB Instance</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', marginBottom: '0.75rem', color: 'var(--cyan)' }}>
                        {details.database_name}
                      </div>

                      <div className="query-label">Blocking Query (Holding transaction lock)</div>
                      <div className="query-dump">{details.blocking_query}</div>

                      <div className="query-label">Blocked Query (Waiting for resource)</div>
                      <div className="query-dump">{details.blocked_query}</div>
                    </div>
                  );
                })
            )}
          </div>
        </section>

        {/* Middle - Human-in-the-Loop Gate */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">🎛️ Human-in-the-Loop Gate</h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Requires Action</span>
          </div>
          <div className="approvals-list">
            {approvals.length === 0 ? (
              <div style={{ color: 'var(--text-secondary)', textAlign: 'center', marginTop: '3rem' }}>
                No high-risk operations queued. Auto-approved actions (CREATE INDEX) bypass this queue.
              </div>
            ) : (
              approvals.map((appr, index) => {
                const isPending = appr.status === 'PENDING';
                return (
                  <div key={index} className={`approval-card ${!isPending ? 'resolved' : 'pending'}`}>
                    <div className="incident-card-header">
                      <span className="incident-id">{appr.approval_id} ({appr.incident_id})</span>
                      <span className={`status-badge ${appr.status.toLowerCase()}`}>
                        {appr.status}
                      </span>
                    </div>

                    <div className="query-label">Selected SRE Action Tool</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', marginBottom: '0.5rem', color: 'var(--amber)', fontWeight: '600' }}>
                      {appr.tool} (Risk: {appr.risk_level})
                    </div>

                    <div className="query-label">Reasoning Diagnostic</div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
                      {appr.reasoning}
                    </div>

                    <div className="query-label">Proposed Patch SQL</div>
                    <div className="query-dump" style={{ border: '1px solid rgba(242, 166, 5, 0.3)' }}>{appr.patch_sql}</div>

                    {isPending ? (
                      <div className="approval-actions">
                        <input
                          type="text"
                          className="approval-comment-input"
                          placeholder="Provide approval / rejection notes..."
                          value={comments[appr.approval_id] || ''}
                          onChange={(e) => handleCommentChange(appr.approval_id, e.target.value)}
                        />
                        <div className="approval-buttons">
                          <button className="btn-approve" onClick={() => handleApprove(appr.approval_id)}>Approve Patch</button>
                          <button className="btn-reject" onClick={() => handleReject(appr.approval_id)}>Reject</button>
                        </div>
                      </div>
                    ) : (
                      appr.comment && (
                        <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                          <strong>Notes:</strong> {appr.comment}
                        </div>
                      )
                    )}
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* Right Side - Autopilot Console Terminal */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">🤖 Autopilot Telemetry</h2>
          </div>
          <ConsoleTerminal />
        </section>
      </main>
    </div>
  );
}
