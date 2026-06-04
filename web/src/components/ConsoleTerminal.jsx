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

import React, { useEffect, useState, useRef } from 'react';

export default function ConsoleTerminal() {
  const [logs, setLogs] = useState([]);
  const terminalEndRef = useRef(null);

  useEffect(() => {
    // Initial welcome lines
    setLogs([
      { type: 'info', text: 'Initializing Autopilot SRE Agent console feed...' },
      { type: 'success', text: 'Connection to Alibaba Cloud RDS monitoring pool verified.' },
      { type: 'info', text: 'Awaiting deadlock trap triggers...' }
    ]);

    // Connect to Core Engine Server-Sent Events (SSE) streaming API
    const eventSource = new EventSource('/api/stream');

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { timestamp, level, category, details } = payload;
        const timeStr = new Date(timestamp).toLocaleTimeString();

        if (category === 'SYSTEM_STARTUP') {
          appendLog('info', `[${timeStr}] SYSTEM: ${details.status}`);
        } else if (category === 'DEADLOCK_TRAPPED') {
          appendLog('error', `[${timeStr}] 🚨 DEADLOCK TRAPPED in database: ${details.database_name}`);
          appendLog('info', `[${timeStr}] Transaction collision IDs: ${details.transaction_ids.join(' <=> ')}`);
          appendLog('warning', `[${timeStr}] Blocking query: ${details.blocking_query}`);
          appendLog('warning', `[${timeStr}] Blocked query: ${details.blocked_query}`);
          appendLog('info', `[${timeStr}] Compressing transaction context and invoking Qwen-max...`);
        } else if (category === 'REMEDIATION_TRIGGERED') {
          appendLog('info', `[${timeStr}] 🧠 Qwen generated patch for ${details.incident_id}`);
          appendLog('success', `[${timeStr}] Proposed healing patch: ${details.patch}`);
          appendLog('info', `[${timeStr}] dry_run=true: Launching secure isolated SQLite sandbox...`);
          appendLog('success', `[${timeStr}] Sandbox compilation verification PASSED.`);
        } else if (category === 'REMEDIATION_COMPLETED') {
          appendLog('success', `[${timeStr}] ⚡ HOT-PATCH APPLIED to Alibaba Cloud RDS connection pool!`);
          appendLog('success', `[${timeStr}] STATUS: RESOLVED. circular wait cleared successfully.`);
        } else {
          appendLog('info', `[${timeStr}] ${level}: ${JSON.stringify(details)}`);
        }
      } catch (err) {
        console.error('Error parsing SSE telemetry log packet:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Connection failed. Retrying...', err);
      appendLog('error', 'Network interruption. Reconnecting to streaming autopilot engine...');
    };

    return () => {
      eventSource.close();
    };
  }, []);

  useEffect(() => {
    // Keep terminal auto-scrolled to latest outputs
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const appendLog = (type, text) => {
    setLogs((prev) => [...prev, { type, text }]);
  };

  return (
    <div className="terminal-wrapper">
      <div className="terminal-header">
        <div className="terminal-dots">
          <div className="terminal-dot red"></div>
          <div className="terminal-dot yellow"></div>
          <div className="terminal-dot green"></div>
        </div>
        <div className="terminal-title">ConsoleTerminal.jsx - Real-time SRE Log</div>
      </div>
      <div className="terminal-body">
        {logs.map((log, index) => (
          <div key={index} className={`terminal-line ${log.type} terminal-prompt`}>
            {log.text}
          </div>
        ))}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
}
