# ParallelMind: Monad Parallel Execution Profiler

> Lightweight local profiler for identifying Solidity storage patterns that can reduce Monad parallel execution efficiency.

ParallelMind is a hackathon-friendly full-stack application that lets you paste or load Solidity code, analyze it with a local FastAPI profiler, and review parallel-readiness scores, storage conflict traces, refactoring suggestions, and a downloadable optimization report.

---

## What the Application Does

The application helps detect smart contract patterns that can force transactions to serialize instead of executing in parallel. It focuses on lightweight static analysis of Solidity source code and does **not** require Solidity compilation, blockchain execution, Docker, Slither, a database, or external AI frameworks.

The profiler currently detects patterns such as:

- shared global nonce writes
- shared global counters such as `totalVolume`
- unbounded loops over state arrays
- shared mutable state variables in execution paths

For each detected issue, the UI explains:

- the issue
- why it matters
- a suggested before/after refactor
- the expected concurrency benefit

---

## Current Architecture

```text
auto-parallel-orchestrator/
├── dashboard/
│   ├── index.html                         # HTML + vanilla JS frontend
│   └── styles.css                         # Dark cyberpunk UI theme
├── profiler-engine/
│   ├── parser.py                          # Lightweight Python static Solidity profiler
│   ├── server.py                          # FastAPI backend
│   └── requirements.txt                   # Backend Python dependencies
├── contracts/
│   ├── src/
│   │   ├── PreOptimizedOrchestrator.sol    # Example serial/bottlenecked contract
│   │   ├── PostOptimizedOrchestrator.sol   # Example sharded/parallel-ready contract
│   │   ├── AgentStorageShard.sol           # Example isolated storage shard
│   │   └── MockDeFiProtocols.sol           # Mock DeFi protocol contracts
│   ├── scripts/
│   │   └── Deploy.s.sol
│   └── foundry.toml
├── agent-layer/
│   └── orchestrator_agent.js              # Optional ethers-based simulation layer
├── requirements.txt
└── readme.md
```

Core runtime stack:

- Frontend: HTML, CSS, Vanilla JavaScript
- Backend: FastAPI
- Analysis Engine: Python static profiler
- Database: none
- Blockchain dependency for dashboard/profiler: none
- Docker: none

---

## Features

### 1. Parallel Readiness Scorecard

The profiler replaces a single flat score with category-level scores:

```text
Storage Isolation: XX/100
Write Contention: XX/100
Loop Scalability: XX/100
Sharding Readiness: XX/100
```

These categories are combined into an overall:

```text
Parallel Readiness Score: XX/100
```

The overall score is weighted toward storage isolation and write contention because those are the most direct causes of serialized execution.

---

### 2. Smart Refactoring Suggestions

Each detected issue includes structured guidance:

```text
Issue:
Why It Matters:
Suggested Refactor:
  Before:
  After:
Expected Benefit:
```

Reusable suggestion templates are included for:

- Global Counters
- Global Nonces
- Shared State Variables
- Unbounded Array Scans

Example:

```text
Issue:
Global Storage Bottleneck

Why It Matters:
Multiple transactions write to the same storage slot causing serialization.

Suggested Refactor:
Before:
uint256 public totalVolume;

After:
mapping(address => uint256) public shardedVolume;

Expected Benefit:
Reduces storage contention and improves parallel execution.
```

---

### 3. Storage Conflict Map

The dashboard includes a visual section called:

```text
Storage Conflict Map
```

It shows detected storage conflicts as a lightweight dependency tree using only HTML/CSS:

```text
executeWorkflow()
├── globalNonce
├── totalVolume
└── registeredAgents
```

No graph libraries are used.

---

### 4. Downloadable Optimization Report

The dashboard includes:

```text
Download Optimization Report
```

The generated report contains:

- Contract Name
- Overall Parallel Readiness Score
- Category Scores
- Detected Issues
- Severity Levels
- Refactoring Recommendations
- Executive Summary

The existing **Copy report** button also copies the richer report format to the clipboard.

---

### 5. Executive Summary Generator

The backend generates a concise summary for each analysis.

Example:

```text
PreOptimizedOrchestrator contains 3 high-risk serialization bottlenecks that are likely to reduce Monad parallel execution efficiency. The most critical issue is globalNonce in executeWorkflow. Overall Parallel Readiness Score is 44/100. Adopting storage sharding patterns could significantly improve concurrency.
```

---

## Running Locally

### 1. Start the backend

```bash
cd D:\auto-parallel-orchestrator\profiler-engine
python -m pip install -r requirements.txt
python server.py
```

The FastAPI backend runs at:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/api/v2/health
```

Expected response:

```json
{
  "status": "online",
  "service": "Monad Parallel-Native Optimizer Engine Backend",
  "version": "2.2.0"
}
```

---

### 2. Start the frontend

Open a second terminal:

```bash
cd D:\auto-parallel-orchestrator\dashboard
python -m http.server 5500
```

Then open:

```text
http://localhost:5500
```

You can also open `dashboard/index.html` directly in a browser, but serving it with `python -m http.server` is recommended.

---

## Using the Dashboard

1. Start the backend.
2. Start or open the dashboard.
3. Confirm **BACKEND STREAM** shows `ONLINE`.
4. Click **Load vulnerable example** or paste Solidity source code.
5. Click **Run AST Diagnostic Analysis**.
6. Review:
   - Parallel Readiness Score
   - Category Scorecard
   - Storage Conflict Map
   - Conflict Trace
   - Smart Refactoring Suggestions
   - Executive Summary
7. Optionally click **Download Optimization Report**.

Keyboard shortcut:

```text
Ctrl + Enter
```

runs the diagnostic.

---

## Backend API

### Health Check

```http
GET /api/v2/health
```

Returns backend status and version.

---

### Optimize Profile

```http
POST /api/v2/optimize-profile
Content-Type: application/json
```

Request body:

```json
{
  "source_code": "pragma solidity ^0.8.20; contract Example { ... }"
}
```

Response includes:

```json
{
  "contract_name": "PreOptimizedOrchestrator",
  "overall_score": 44,
  "parallel_readiness_score": 44,
  "category_scores": {
    "Storage Isolation": 50,
    "Write Contention": 35,
    "Loop Scalability": 55,
    "Sharding Readiness": 40
  },
  "status": "Serialization Danger Warning",
  "detected_vulnerabilities_count": 3,
  "severity_counts": {
    "CRITICAL": 2,
    "HIGH": 1,
    "MEDIUM": 0,
    "LOW": 0
  },
  "storage_conflict_map": [
    {
      "function": "executeWorkflow",
      "storage_targets": [
        "globalNonce",
        "totalVolume",
        "registeredAgents"
      ]
    }
  ],
  "executive_summary": "...",
  "conflicts": []
}
```

---

## Example Results

### Pre-Optimized Contract

Input:

```text
contracts/src/PreOptimizedOrchestrator.sol
```

Typical result:

```text
Overall Parallel Readiness Score: 44/100
Storage Isolation: 50/100
Write Contention: 35/100
Loop Scalability: 55/100
Sharding Readiness: 40/100
Detected Issues: 3
Status: Serialization Danger Warning
```

Detected conflict map:

```text
executeWorkflow()
├── globalNonce
├── totalVolume
└── registeredAgents
```

---

### Post-Optimized Contract

Input:

```text
contracts/src/PostOptimizedOrchestrator.sol
```

Typical result:

```text
Overall Parallel Readiness Score: 100/100
Storage Isolation: 100/100
Write Contention: 100/100
Loop Scalability: 100/100
Sharding Readiness: 100/100
Detected Issues: 0
Status: Production Parallel Ready
```

---

## What This Project Does Not Do

This project intentionally remains lightweight. It does not:

- compile Solidity
- deploy contracts
- execute blockchain transactions
- require Anvil or a live node for dashboard analysis
- use Docker
- use Slither
- use React
- use a database
- use graph visualization libraries
- use external AI frameworks

The profiler is a static pattern scanner designed for fast feedback and demonstration purposes.

---

## Optional Agent Layer

The `agent-layer/orchestrator_agent.js` file contains an optional ethers-based simulation concept for parallel agent workflows. It is not required to run the dashboard or profiler.

The main profiler workflow only requires:

```text
profiler-engine/server.py
dashboard/index.html
```

---

## Troubleshooting

### Backend stream shows OFFLINE

Make sure the backend is running:

```bash
cd D:\auto-parallel-orchestrator\profiler-engine
python server.py
```

Then check:

```text
http://localhost:8000/api/v2/health
```

---

### Frontend does not load

Start the local static server:

```bash
cd D:\auto-parallel-orchestrator\dashboard
python -m http.server 5500
```

Open:

```text
http://localhost:5500
```

---

### Port 8000 is already in use

Stop the process using port `8000`, or change the port in `profiler-engine/server.py`:

```python
uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
```

---

### Port 5500 is already in use

Use another frontend port:

```bash
python -m http.server 5501
```

Then open:

```text
http://localhost:5501
```
