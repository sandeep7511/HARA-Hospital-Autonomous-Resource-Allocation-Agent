# 🏥 HARA — Hospital Autonomous Resource Allocation Agent

An autonomous, AI-driven hospital management system designed to eliminate emergency room bottlenecks. HARA manages clinical triage, regional ambulance dispatching, and live resource allocation in real-time using **Gemini AI, n8n, Flask, SQL Server, and Streamlit**.

---

## 🚀 Project Vision

In high-stress medical environments, delays in triage and inefficient bed management cost valuable time. I built HARA to automate the logistical and preliminary clinical reasoning of hospital admissions. 

By integrating an intelligent backend with a live hospital database, HARA evaluates patient vitals, active ward capacities, and staff availability to make instantaneous, transparent routing decisions. It transitions hospital operations from reactive to proactive, freeing up medical staff to focus on direct patient care.

### Core Capabilities
- **🧠 AI-Powered Clinical Triage:** Gemini analyzes symptoms and vitals to generate severity scores, first-aid steps, required imaging, and specialist referrals.
- **🛏️ Autonomous Allocation:** A continuous n8n background cycle assigns waiting patients to the correct ward and staff member based on severity and live capacity.
- **🚑 Smart Ambulance Dispatching:** An algorithmic routing engine scores regional hospitals based on distance, specialist availability, and bed counts to dispatch ambulances to the *right* facility, not just the closest one.
- **📜 Transparent Auditing:** Every automated action—from trivial triage to critical ICU escalation—is recorded with its AI reasoning in an immutable decision log.

---

## 🗺️ System Architecture

HARA is built on a distributed, multi-service architecture:

```text
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
│  patients, staff, imaging_machines...    │
└──────────────────────────────────────────┘
         ▲
         │ POST /api/run-cycle every 30s
┌────────┴─────────┐
│   n8n  :5678     │
│  Autonomous loop │
└──────────────────┘

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
