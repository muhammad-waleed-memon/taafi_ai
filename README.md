# Taafi.ai: Automated SRE Database Incident Remediation Platform

Taafi.ai is a cloud-native, automated database SRE autopilot agent designed to detect, analyze, sandbox, and hot-patch database deadlock and lock contention incidents in real-time. Built specifically for high-throughput transactional databases running on **Alibaba Cloud ACK**.

---

## 1. Problem Statement

Database deadlocks (circular dependency lock-waits) and query contention are leading causes of application degradation, database connection pool exhaustion, and SLA breaches. Traditional remediation involves paging an on-call SRE, performing manual query analysis, and running risky queries in production.

**Taafi.ai** automates this entire pipeline:
1. **Traps** deadlock alerts in real-time.
2. **Compresses** SQL lock contexts to minimize LLM token footprints.
3. **Retrieves** past historical repairs using a **RAG Memory Search** mechanism.
4. **Queries** Alibaba's Qwen LLM using **Structured Tool Calling** for diagnosis and patch SQL formulation.
5. **Validates** patches in an isolated in-memory SQLite sandbox dry-run.
6. **Classifies Risk**: Auto-deploys safe operations (such as creating missing indexes) and escalates destructive actions (such as backend PID terminations or transaction reordering) to a **Human-in-the-Loop** checkpoint queue.

---

## 2. Architecture Diagram

The system operates as a set of decoupled services communicate via a Pub/Sub event bus:

```
                  ┌──────────────────────┐
                  │  Alibaba DashScope   │ (Qwen-max LLM API)
                  └──────────▲───────────┘
                             │ (Structured Tools)
                             ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  PostgreSQL  ├─►  │   Core Engine    ├─►  │     Valkey      ├─►  │   Orchestrator  │
│  (Database)  │    │ (FastAPI Backend)│    │   (Pub/Sub)     │    │ (Autopilot SRE) │
└──────────────┘    └────────▲─────────┘    └────────▲────────┘    └────────┬────────┘
                             │                       │                      │
                             ▼                       ▼                      │ (RAG Lookup &
                    ┌──────────────────┐    ┌─────────────────┐             │  Sandbox validation)
                    │  React Dashboard │◄───┤ Telemetry logs  │◄────────────┘
                    │   (SPA Web UI)   │    │  Stream (SSE)   │
                    └──────────────────┘    └─────────────────┘
```

For more details, see the Mermaid source file [docs/ARCHITECTURE.mmd](file:///c:/Users/S.A%20COMPUTER/Desktop/taafi_ai/docs/ARCHITECTURE.mmd).

---

## 3. Local Sandbox Quick-Start (Docker Compose)

You can launch a complete local sandbox mimicking the production stack including PostgreSQL, Valkey, Backend APIs, the Autopilot worker daemon, and the Web UI.

1. **Start the containers**:
   ```bash
   docker-compose up --build -d
   ```
2. **Access the Web Dashboard**:
   Open your browser and navigate to `http://localhost`.
3. **Simulate a Database Deadlock**:
   - Click the **"Trigger DB Deadlock Simulation"** button in the top right of the dashboard.
   - This sends a simulated deadlock to `POST /api/incidents/simulate`.
   - The autopilot agent will trap it, perform compression, execute a dry-run in the sandbox, classify its risk, and either apply the hot-patch (e.g. `CREATE INDEX`) or queue it for operator confirmation inside the **Human-in-the-Loop Gate** panel!
4. **Shut down the sandbox**:
   ```bash
   docker-compose down -v
   ```

---

## 4. Production Deployment

To run in production on Alibaba Cloud ACK, refer to the [README-CLOUD.md](file:///c:/Users/S.A%20COMPUTER/Desktop/taafi_ai/README-CLOUD.md) guide.

---

## 5. Team Metadata

- **Authors**: Muhammad Waleed & Areeba
- **Version**: 2.0.0 (Production-Ready)
- **License**: Apache 2.0
