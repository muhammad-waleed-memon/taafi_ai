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
  const [metrics, setMetrics] = useState({
    trapped: 0,
    unresolved: 0,
    resolved: 0
  });

  const fetchIncidents = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/incidents');
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

        // Dedup count for simulation logic
        setMetrics({ trapped, unresolved, resolved });
      }
    } catch (err) {
      console.error('Failed to pull incidents list:', err);
    }
  };

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 3000);
    return () => clearInterval(interval);
  }, []);

  const triggerDeadlockSimulation = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/incidents/simulate', {
        method: 'POST'
      });
      if (res.ok) {
        fetchIncidents();
      }
    } catch (err) {
      console.error('Failed to trigger deadlock simulation:', err);
    }
  };

  return (
    <div className="dashboard-container">
      {/* SRE Top Navigation Header */}
      <header className="header">
        <div className="brand-section">
          <h1 className="brand-title">Taafi.ai</h1>
          <span className="brand-badge">Autopilot SRE Agent v1.0</span>
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
            <h2 className="panel-title">🛡️ Trapped Database Lock Graphs</h2>
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

        {/* Right Side - Autopilot Console Terminal */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">🤖 Autopilot SRE Agent Telemetry</h2>
          </div>
          <ConsoleTerminal />
        </section>
      </main>
    </div>
  );
}
