"""
HARA Clinical Dashboard  —  streamlit run app.py
Requires: python api/api.py  (Terminal 1)
"""
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

API = "http://localhost:5001/api"

st.set_page_config(
    page_title="HARA – Clinical",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    .sev-card {border-radius:10px;padding:14px 18px;margin:8px 0;}
</style>
""", unsafe_allow_html=True)

# ── Helpers ─────────────────────────────────────────────────────────
def get(ep, params=None):
    try:
        r = requests.get(f"{API}/{ep}", params=params, timeout=5)
        return r.json()
    except: return None

def post(ep, payload=None):
    try:
        r = requests.post(f"{API}/{ep}", json=payload or {}, timeout=60)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

SEV_ICON  = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴"}
SEV_LABEL = {1:"Trivial",2:"Minor",3:"Moderate",4:"Serious",5:"CRITICAL"}
SEV_COLOR = {1:"#dbeafe",2:"#dcfce7",3:"#fef9c3",4:"#ffedd5",5:"#fee2e2"}
ROLE_ICON = {"Doctor":"👨‍⚕️","ER Doctor":"🚨","Nurse":"👩‍⚕️",
             "Surgeon":"🔪","On-Call":"📟","Specialist":"🔬"}

# ── API health ───────────────────────────────────────────────────────
if not get("health"):
    st.error("⚠️ Flask API offline.  Start it:  python api/api.py")
    st.stop()

# ── Hospital selector ────────────────────────────────────────────────
hospitals   = get("hospitals") or []
hosp_map    = {h["name"]: h["id"] for h in hospitals}
hosp_names  = list(hosp_map.keys())

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏥 HARA Clinical")
    st.caption("Hospital Autonomous Resource Allocation Agent")
    st.divider()

    sel_hosp_name = st.selectbox("Active Hospital", hosp_names)
    sel_hosp_id   = hosp_map.get(sel_hosp_name, 1)

    status     = get("status",    {"hospital_id": sel_hosp_id}) or {}
    wards      = get("wards",     {"hospital_id": sel_hosp_id}) or []
    staff_data = status.get("staff", {})

    st.subheader("Ward Capacity")
    for w in wards:
        pct   = w["available_beds"]/w["total_beds"] if w["total_beds"] else 0
        color = "🟢" if pct > 0.4 else ("🟠" if pct > 0.15 else "🔴")
        st.markdown(f"**{color} {w['name']}**")
        st.progress(pct, text=f"{w['available_beds']}/{w['total_beds']} free")

    st.divider()
    st.subheader("Staff on Duty")
    for role, counts in staff_data.items():
        a, t = counts["available"], counts["total"]
        c1, c2 = st.columns([3,1])
        c1.markdown(f"{ROLE_ICON.get(role,'')} **{role}**")
        c2.markdown(f"`{a}/{t}`")

    st.divider()
    st.caption(f"API  → http://localhost:5001")
    st.caption(f"Ops  → http://localhost:8502")
    st.caption(f"n8n  → http://localhost:5678")
    st.caption(f"Last refresh: {datetime.now().strftime('%H:%M:%S')}")
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ── Main tabs ────────────────────────────────────────────────────────
st.title("🏥 HARA — Clinical Dashboard")
st.markdown(f"**Active hospital:** {sel_hosp_name} &nbsp;·&nbsp; "
            f"Powered by **Gemini AI · n8n · Flask · SQL Server**")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard",
    "🩺 Triage & Intake",
    "🚑 Patient Queue",
    "🛏️ Resource Control",
    "🤖 Agent Log",
])


# ════════════════════════════════════════════════════════════════════
#  TAB 1  —  DASHBOARD
# ════════════════════════════════════════════════════════════════════
with tab1:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("⏳ Waiting",         status.get("waiting_count",  0))
    k2.metric("🛏️ Admitted",       status.get("admitted_count", 0))
    k3.metric("🔴 Critical",        status.get("critical_count", 0))
    k4.metric("👩‍⚕️ Staff avail",
              sum(v["available"] for v in staff_data.values()))

    st.divider()

    all_p = (get("patients/all", {"hospital_id": sel_hosp_id}) or {}).get("patients", [])

    col_l, col_r = st.columns([2,1])

    with col_l:
        st.subheader("All Patients")
        if all_p:
            df = pd.DataFrame(all_p)
            df[""] = df["severity"].map(SEV_ICON)
            df["Severity"] = df["severity"].map(SEV_LABEL)
            st.dataframe(
                df[["","name","age","condition","Severity","status","ward","bed","admitted"]]
                  .rename(columns={"name":"Name","age":"Age","condition":"Condition",
                                   "status":"Status","ward":"Ward","bed":"Bed",
                                   "admitted":"Admitted"}),
                hide_index=True, use_container_width=True,
            )
        else:
            st.info("No patients on record.")

    with col_r:
        st.subheader("Ward Occupancy")
        for w in wards:
            occ = w["total_beds"] - w["available_beds"]
            pct = (occ/w["total_beds"]*100) if w["total_beds"] else 0
            st.markdown(f"**{w['name']}**")
            a, b, c = st.columns(3)
            a.metric("Free",    w["available_beds"])
            b.metric("Occupied", occ)
            c.metric("% Full",  f"{pct:.0f}%")

    st.divider()
    st.subheader("🚪 Discharge Patient")
    admitted = [p for p in all_p if p["status"]=="admitted"]
    if admitted:
        opts = {f"{p['name']} — {p['ward']} / {p['bed']}": p["id"] for p in admitted}
        sel  = st.selectbox("Select patient", list(opts.keys()))
        if st.button("Discharge", type="secondary"):
            r = post("discharge", {"patient_id": opts[sel]})
            st.success(r["message"]) if r.get("success") else st.error(r.get("error"))
            st.rerun()
    else:
        st.info("No admitted patients to discharge.")


# ════════════════════════════════════════════════════════════════════
#  TAB 2  —  TRIAGE & INTAKE
# ════════════════════════════════════════════════════════════════════
with tab2:
    if "triage_result" not in st.session_state:
        st.session_state.triage_result = None

    # ── Show existing report if one is stored ─────────────────────────
    if st.session_state.triage_result:
        r      = st.session_state.triage_result
        t      = r["triage"]
        sev    = t["severity_score"]
        icon   = SEV_ICON.get(sev, "⚪")
        spec   = t.get("specialist_needed")
        img    = t.get("imaging_needed")

        # Pastel backgrounds — black text so it reads on any theme
        bg = {1:"#dbeafe",2:"#dcfce7",3:"#fef9c3",4:"#ffedd5",5:"#fee2e2"}.get(sev,"#f3f4f6")

        col_hdr, col_clr = st.columns([6, 1])
        with col_hdr:
            st.markdown("### 📋 Triage Report")
        with col_clr:
            if st.button("🗑️ Clear", type="secondary"):
                st.session_state.triage_result = None
                st.rerun()

        # Header card — black text on pastel background
        parts = [f"<b>Referred to:</b> {t['doctor_referral']}"]
        if spec: parts.append(f"<b>Specialist:</b> {spec}")
        if img:  parts.append(f"<b>Imaging:</b> {img}")
        parts.append(f"<b>Est. wait:</b> {t['estimated_wait']}")
        details_line = " &nbsp;·&nbsp; ".join(parts)

        st.markdown(f"""
<div style="background:{bg};border-radius:10px;padding:16px 20px;margin:8px 0;color:#111111;">
<h3 style="margin:0;color:#111111;">{icon} {t['severity_label']} — Severity {sev}/5</h3>
<p style="margin:8px 0 0;color:#222222;">{details_line}</p>
<p style="margin:6px 0 0;color:#444444;font-size:14px;font-style:italic;">
{t['gemini_reasoning']}
</p>
</div>
""", unsafe_allow_html=True)

        if sev == 5:
            st.error("🚨 CRITICAL — Immediate action. All senior staff alerted.")
        elif sev == 4:
            st.warning("⚠️ URGENT — Patient must be seen within 15 minutes.")

        if r.get("allocation_msg"):
            st.success(r["allocation_msg"])

        if r.get("include_vitals"):
            v = r["vitals"]
            st.markdown("#### 📋 Recorded Vitals")
            vc = st.columns(7)
            vc[0].metric("Temp",   f"{v['temp']}°C")
            vc[1].metric("BP",     f"{v['bps']}/{v['bpd']}")
            vc[2].metric("HR",     f"{v['hr']} bpm")
            vc[3].metric("SpO₂",   f"{v['spo2']}%")
            vc[4].metric("Height", f"{v['height']} cm")
            vc[5].metric("Weight", f"{v['weight']} kg")
            vc[6].metric("BMI",    v["bmi"])

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### 🚑 First Aid Steps")
            for i, step in enumerate(t["first_aid_steps"], 1):
                st.markdown(f"**{i}.** {step}")
            st.markdown("#### 👩‍⚕️ Nurse Instructions")
            for inst in t["nurse_instructions"]:
                st.markdown(f"- {inst}")
        with col_b:
            st.markdown("#### 💊 Medicines Ordered")
            for med in t["medicines"]:
                st.markdown(
                    f"**{med['name']}** — {med['dose']} ({med['route']})"
                    f"\n> *{med['purpose']}*"
                )
            if img:
                st.info(f"**{img}** imaging required. Check Ops dashboard.")
        
        st.markdown("---")

    # ── Intake form ───────────────────────────────────────────────────
    st.subheader("🩺 Register New Patient")
    st.caption("Vitals are optional but improve Gemini triage accuracy.")

    with st.form("triage_form", clear_on_submit=True):
        st.markdown("**Patient Details**")
        c1, c2 = st.columns(2)
        with c1:
            t_name = st.text_input("Full Name *")
            t_age  = st.number_input("Age *", 0, 120, 30)
        with c2:
            t_cond = st.text_input("Presenting Condition *",
                                   placeholder="e.g. Severe chest pain radiating to left arm")
            t_sev  = st.slider("Initial Severity (1=Trivial → 5=Critical)", 1, 5, 3)

        t_notes = st.text_area("Additional Notes", height=60,
                               placeholder="Allergies, medications, relevant history...")

        st.markdown("**📋 Vitals (Optional)**")
        v_col1, v_col2, v_col3, v_col4 = st.columns(4)
        with v_col1:
            v_temp = st.number_input("Temp (°C)", 34.0, 42.0, 37.0, 0.1, format="%.1f")
            v_hr   = st.number_input("Heart Rate (bpm)", 30, 220, 80)
        with v_col2:
            v_bps  = st.number_input("BP Systolic", 60, 250, 120)
            v_bpd  = st.number_input("BP Diastolic", 40, 150, 80)
        with v_col3:
            v_spo2   = st.number_input("SpO₂ (%)", 70, 100, 98)
            v_height = st.number_input("Height (cm)", 50.0, 220.0, 165.0, 0.5)
        with v_col4:
            v_weight = st.number_input("Weight (kg)", 2.0, 300.0, 65.0, 0.5)
            bmi_est  = round(v_weight / ((v_height/100)**2), 1) if v_height > 0 else 0
            st.metric("BMI", bmi_est)

        include_vitals = st.checkbox("Include vitals in triage", value=True)
        auto_allocate  = st.checkbox("Auto-allocate bed after triage", value=True)

        submitted = st.form_submit_button("🩺 Register & Triage Patient",
                                          type="primary", use_container_width=True)

    if submitted:
        if not t_name or not t_cond:
            st.error("Name and Condition are required.")
        else:
            with st.spinner("Registering patient..."):
                reg = post("patients/add", {
                    "name": t_name, "age": t_age, "condition": t_cond,
                    "severity": t_sev, "notes": t_notes,
                    "hospital_id": sel_hosp_id,
                })

            if not reg.get("success"):
                st.error(f"Registration failed: {reg.get('error')}")
            else:
                pid = reg["patient_id"]
                vitals_payload = None
                if include_vitals:
                    vitals_payload = {
                        "temperature": v_temp, "bp_systolic": v_bps,
                        "bp_diastolic": v_bpd, "heart_rate": v_hr,
                        "spo2": v_spo2, "height_cm": v_height, "weight_kg": v_weight,
                    }

                with st.spinner("🧠 Gemini triaging..."):
                    triage = post("triage", {"patient_id": pid, "vitals": vitals_payload})

                if not triage.get("success"):
                    st.error(f"Triage failed: {triage.get('error')}")
                else:
                    allocation_msg = None
                    if auto_allocate:
                        with st.spinner("Allocating bed and staff..."):
                            cycle = post("run-cycle", {"hospital_id": sel_hosp_id})
                        for a in cycle.get("actions", []):
                            if a.get("action") == "ADMITTED" and a.get("patient") == t_name:
                                allocation_msg = (
                                    f"🛏️ Allocated to **{a['ward']}** / bed **{a['bed']}**"
                                    f" | Staff: **{a['staff']}**"
                                )

                    st.session_state.triage_result = {
                        "triage": triage, "include_vitals": include_vitals,
                        "vitals": {
                            "temp": v_temp, "bps": v_bps, "bpd": v_bpd,
                            "hr": v_hr, "spo2": v_spo2,
                            "height": v_height, "weight": v_weight, "bmi": bmi_est,
                        },
                        "allocation_msg": allocation_msg,
                    }
                    st.rerun()

    # ── Lookup existing report ────────────────────────────────────────
    st.divider()
    st.subheader("🔍 View Existing Triage Report")
    all_p_lookup = (get("patients/all", {"hospital_id": sel_hosp_id}) or {}).get("patients", [])
    if all_p_lookup:
        lookup_opts = {f"{p['name']} (ID {p['id']})": p["id"] for p in all_p_lookup}
        lookup_sel  = st.selectbox("Select patient", list(lookup_opts.keys()),
                                   key="triage_lookup")
        if st.button("Load Report"):
            report = get(f"triage/{lookup_opts[lookup_sel]}")
            if report and report.get("success"):
                sev2  = report["severity_score"]
                icon2 = SEV_ICON.get(sev2, "⚪")
                bg2   = {1:"#dbeafe",2:"#dcfce7",3:"#fef9c3",4:"#ffedd5",5:"#fee2e2"}.get(sev2,"#f3f4f6")
                spec2 = report.get("specialist_needed")
                img2  = report.get("imaging_needed")

                parts2 = [f"<b>Referral:</b> {report['doctor_referral']}"]
                if spec2: parts2.append(f"<b>Specialist:</b> {spec2}")
                if img2:  parts2.append(f"<b>Imaging:</b> {img2}")
                parts2.append(f"<b>Wait:</b> {report['estimated_wait']}")
                parts2.append(f"<b>Time:</b> {report['timestamp']}")
                details2 = " &nbsp;·&nbsp; ".join(parts2)

                st.markdown(f"""
<div style="background:{bg2};border-radius:10px;padding:14px 18px;
            margin:10px 0;color:#111111;">
  <h4 style="margin:0;color:#111111;">{icon2} {report['severity_label']} — Severity {sev2}/5</h4>
  <p style="margin:4px 0;color:#222222;">{details2}</p>
  <p style="color:#444444;font-size:13px;font-style:italic;">{report['gemini_reasoning']}</p>
</div>
""", unsafe_allow_html=True)
                
                vitals = get(f"vitals/{lookup_opts[lookup_sel]}")
                if vitals and vitals.get("success"):
                    vc = st.columns(7)
                    vc[0].metric("Temp",   f"{vitals.get('temperature','—')}°C")
                    vc[1].metric("BP",     f"{vitals.get('bp_systolic','—')}/{vitals.get('bp_diastolic','—')}")
                    vc[2].metric("HR",     f"{vitals.get('heart_rate','—')} bpm")
                    vc[3].metric("SpO₂",   f"{vitals.get('spo2','—')}%")
                    vc[4].metric("Height", f"{vitals.get('height_cm','—')} cm")
                    vc[5].metric("Weight", f"{vitals.get('weight_kg','—')} kg")
                    vc[6].metric("BMI",    vitals.get("bmi","—"))

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**First Aid Steps**")
                    for i, s in enumerate(report["first_aid_steps"], 1):
                        st.markdown(f"{i}. {s}")
                    st.markdown("**Nurse Instructions**")
                    for inst in report["nurse_instructions"]:
                        st.markdown(f"- {inst}")
                with c2:
                    st.markdown("**Medicines**")
                    for med in report["medicines"]:
                        st.markdown(f"**{med['name']}** — {med['dose']} ({med['route']})"
                                    f"\n> *{med['purpose']}*")
            else:
                st.info("No triage report found for this patient.")


# ════════════════════════════════════════════════════════════════════
#  TAB 3  —  PATIENT QUEUE
# ════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Current Waiting Queue")
    waiting_resp = get("patients/waiting", {"hospital_id": sel_hosp_id}) or {}
    waiting_list = waiting_resp.get("patients", [])

    if waiting_list:
        for p in waiting_list:
            sev = p["severity"]
            with st.expander(
                f"{SEV_ICON[sev]} {p['name']} — Age {p['age']} — "
                f"Severity {sev} ({SEV_LABEL[sev]})"
            ):
                st.markdown(f"**Condition:** {p['condition']}")
                tr = get(f"triage/{p['id']}")
                if tr and tr.get("success"):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Referral:** {tr['doctor_referral']}")
                    c2.markdown(f"**Wait:** {tr['estimated_wait']}")
                    c3.markdown(f"**Imaging:** {tr.get('imaging_needed') or 'None'}")
                    if tr.get("specialist_needed"):
                        st.markdown(f"**Specialist:** {tr['specialist_needed']}")
                    st.markdown(f"*{tr['gemini_reasoning']}*")
                else:
                    st.caption("No triage yet — use Triage & Intake tab.")
    else:
        st.success("✅ No patients waiting.")

    st.divider()
    if st.button("▶ Run Allocation Cycle", type="primary", use_container_width=True):
        with st.spinner("Agent allocating..."):
            cycle = post("run-cycle", {"hospital_id": sel_hosp_id})
        for a in cycle.get("actions", []):
            if a.get("action") == "ADMITTED":
                st.success(
                    f"✅ {a['patient']} → {a['ward']} / {a['bed']} "
                    f"| {a['staff']}\n> {a.get('reasoning','')}"
                )
            elif a.get("action") == "NO_BED":
                st.warning(f"⚠️ {a['patient']} — {a.get('reason','No bed')}")
        if not cycle.get("actions"):
            st.info(cycle.get("message","Done."))
        st.rerun()


# ════════════════════════════════════════════════════════════════════
#  TAB 4  —  RESOURCE CONTROL
# ════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Adjust Bed Availability")
    ward_updates = {}
    cols = st.columns(max(len(wards), 1))
    for i, w in enumerate(wards):
        with cols[i]:
            st.markdown(f"**{w['name']}**")
            new_val = st.number_input(
                "Available beds", 0, w["total_beds"],
                w["available_beds"], key=f"ward_{w['id']}",
            )
            ward_updates[w["id"]] = new_val

    if st.button("💾 Save Bed Changes", type="primary"):
        for wid, avail in ward_updates.items():
            post("wards/update", {"ward_id": wid, "available_beds": avail})
        st.success("Saved."); st.rerun()

    st.divider()
    st.subheader("Staff Availability")
    all_staff   = get("staff", {"hospital_id": sel_hosp_id}) or []
    role_groups: dict = {}
    for s in all_staff:
        role_groups.setdefault(s["role"], []).append(s)

    staff_updates = []
    for role, members in role_groups.items():
        st.markdown(f"**{ROLE_ICON.get(role,'')} {role}**")
        cols = st.columns(min(len(members), 3))
        for i, s in enumerate(members):
            with cols[i % 3]:
                spec_label = f" ({s['specialty']})" if s.get("specialty") else ""
                new_avail  = st.checkbox(
                    f"{s['name']}{spec_label}", value=s["is_available"],
                    key=f"staff_{s['id']}"
                )
                staff_updates.append({"id": s["id"], "is_available": new_avail})

    if st.button("💾 Save Staff Changes", type="primary", key="save_staff"):
        post("staff/update", {"staff": staff_updates})
        st.success("Saved."); st.rerun()


# ════════════════════════════════════════════════════════════════════
#  TAB 5  —  AGENT LOG
# ════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("Agent Decision Log")
    st.caption("Every triage, allocation, escalation, and discharge — with full AI reasoning.")

    logs  = get("decisions", {"limit": 100, "hospital_id": sel_hosp_id}) or []
    badge = {"critical":"🔴 CRITICAL","warning":"🟠 WARNING","normal":"🟢 INFO"}

    if logs:
        for log in logs:
            lvl = log.get("severity_level","normal")
            with st.expander(
                f"{badge.get(lvl,'⚪')}  [{log['action_type']}]  "
                f"{log['patient_name']}  —  {log['time']}"
            ):
                st.markdown(f"**Reasoning:** {log['reasoning']}")
                st.markdown(f"**Action:** {log['action_taken']}")
    else:
        st.info("No decisions yet.")

    if st.button("🗑️ Clear Log", type="secondary"):
        post("decisions/clear"); st.success("Cleared."); st.rerun()
