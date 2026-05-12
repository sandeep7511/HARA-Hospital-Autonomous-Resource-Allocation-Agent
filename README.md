# 🏥 HARA — Hospital Autonomous Resource Allocation Agent

An autonomous AI agent that manages hospital resources in real time using
**Gemini AI · n8n · Flask · SQL Server · Streamlit**.

---

## Architecture

```
┌──────────────────┐     ┌──────────────────┐
│  Streamlit       │     │  React Web App   │
│  Clinical :8501  │     │  hara-web/       │
│  Ops      :8502  │     │  GitHub Pages    │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         ▼                        ▼
┌──────────────────────────────────────────┐
│           Flask REST API  :5001          │
│   Gemini AI · Routing Engine · Triage   │
└──────────────────┬───────────────────────┘
                   │ SQLAlchemy
                   ▼
┌──────────────────────────────────────────┐
│         SQL Server — HospitalDB          │
│  12 tables: hospitals, wards, beds,      │
│  patients, staff, imaging_machines,      │
│  imaging_requests, ambulances,           │
│  ambulance_dispatches, patient_vitals,   │
│  inter_hospital_referrals, decisions_log │
└──────────────────────────────────────────┘
         ▲
         │ POST /api/run-cycle every 30s
┌────────┴─────────┐
│   n8n  :5678     │
│  Autonomous loop │
└──────────────────┘
```

---

## Hospitals

| Hospital | Location | Role |
|---|---|---|
| National Hospital of Sri Lanka | Colombo (6.9271, 79.8612) | Main |
| Colombo South Teaching Hospital | Kalubowila (6.8561, 79.8741) | Partner |

---

## Setup — Step by Step

### Step 1 — Create the database in SSMS

Open SSMS, connect to your server, open a New Query and run:
```sql
CREATE DATABASE HospitalDB;
```

### Step 2 — Set up Python environment

```bash
cd hospital-agent
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

> If pyodbc fails, install [ODBC Driver 17 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) first.

### Step 3 — Configure environment

```bash
copy .env.example .env
```

Edit `.env`:
```
GEMINI_API_KEY=your_key_here
SQL_SERVER=localhost            # or .\SQLEXPRESS or DESKTOP-XXXX\SQLEXPRESS
SQL_DATABASE=HospitalDB
API_PORT=5001
```

### Step 4 — Seed the database

```bash
python setup_db.py
```

Creates all 12 tables and seeds both hospitals with wards, beds, staff,
imaging machines, ambulances, and demo patients.

### Step 5 — Start everything (3 terminals)

**Terminal 1 — Flask API:**
```bash
venv\Scripts\activate
python api/api.py
```
Test: http://localhost:5001/api/health

**Terminal 2 — Clinical Dashboard:**
```bash
venv\Scripts\activate
streamlit run app.py
```
Opens: http://localhost:8501

**Terminal 3 — Operations Dashboard:**
```bash
venv\Scripts\activate
streamlit run ops.py --server.port 8502
```
Opens: http://localhost:8502

**Terminal 4 — n8n (no venv needed):**
```bash
npm install -g n8n
n8n start
```
Opens: http://localhost:5678
→ Import `n8n_workflow.json` → Activate

---

## Docker (alternative to manual setup)

```bash
copy .env.example .env   # fill in your Gemini key
docker-compose up --build
```

| Service | URL |
|---|---|
| Flask API | http://localhost:5001 |
| Clinical Streamlit | http://localhost:8501 |
| Ops Streamlit | http://localhost:8502 |
| n8n | http://localhost:5678 |

> SQL Server stays on your laptop. Docker containers connect via `host.docker.internal`.

---

## Streamlit Dashboards

### Clinical (app.py — port 8501)
For doctors and nurses:
- **Dashboard** — Live patient table, ward occupancy, staff availability chart, discharge
- **Triage & Intake** — Register patient with optional vitals (temp/BP/HR/SpO₂/height/weight/BMI), Gemini produces full triage report with first aid, medicines, specialist referral, imaging needed, nurse instructions
- **Patient Queue** — Waiting patients with triage summaries, manual allocation trigger
- **Resource Control** — Adjust bed counts per ward, toggle staff availability
- **Agent Log** — Full audit trail of every AI decision with reasoning

### Operations (ops.py — port 8502)
For admin and dispatch:
- **Ambulance Dispatch** — AI routing engine scores every hospital simultaneously (distance + specialist + imaging + beds), dispatches to best match, shows comparison table
- **Imaging Control** — Toggle each machine on/off, view imaging requests, manually request scans
- **Hospital Network** — Both hospitals overview, imaging availability grid, distance matrix, ambulance fleet
- **Referrals** — Inter-hospital referral log

---

## Key API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/hospitals` | Both hospitals with full status |
| GET | `/api/status` | Ward + staff snapshot |
| POST | `/api/patients/add` | Register new patient |
| POST | `/api/triage` | Gemini triage with optional vitals |
| POST | `/api/run-cycle` | Autonomous allocation cycle |
| POST | `/api/ambulance/dispatch` | Smart ambulance routing |
| POST | `/api/imaging/machines/{id}/toggle` | Toggle machine availability |
| GET | `/api/decisions` | Agent decision log |
| GET | `/api/debug` | Database + Gemini health check |

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI | Google Gemini 2.0 Flash (with rule-based fallback) |
| Orchestration | n8n (self-hosted, free) |
| Backend | Flask + Flask-CORS |
| Database | SQL Server via SQLAlchemy + pyodbc |
| Frontend 1 | Streamlit (clinical) |
| Frontend 2 | Streamlit (operations) |
| Frontend 3 | React + Tailwind (hara-web/) |
| Containers | Docker + docker-compose |
| Language | Python 3.12 |

---

## Severity Scale

| Level | Label | Ward | Staff |
|---|---|---|---|
| 5 | Critical | ICU | Surgeon |
| 4 | Serious | Emergency | ER Doctor |
| 3 | Moderate | Emergency / General | Doctor |
| 2 | Minor | General | Nurse |
| 1 | Trivial | General | Nurse |

---

## Ambulance Routing Score

The routing engine scores each hospital with:
```
score = distance_km
      + 50  (if required specialist unavailable)
      + 30  (if required imaging unavailable)
      + 100 (if no beds available)
```
Lower score = better hospital. The ambulance is dispatched to the lowest-scoring hospital.

---

*Built for KDU — BSc Applied Data Science Communication — Assignment II*
*HARA v5 — Intake 41, 3rd Year 1st Semester, LB3114*
