"""
HARA Operations Dashboard  —  streamlit run ops.py --server.port 8502
"""
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

API = "http://localhost:5001/api"

st.set_page_config(
    page_title="HARA Ops",
    page_icon="🚑",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .hosp-card {border-radius:10px;padding:16px;margin-bottom:12px;}
    .available {color:#16a34a;font-weight:bold;}
    .unavailable {color:#dc2626;font-weight:bold;}
    .score-badge {background:#1e40af;color:white;padding:2px 8px;
                  border-radius:9999px;font-size:12px;}
</style>
""", unsafe_allow_html=True)


def get(ep, params=None):
    try:
        r = requests.get(f"{API}/{ep}", params=params, timeout=5)
        return r.json()
    except: return None

def post(ep, payload=None):
    try:
        r = requests.post(f"{API}/{ep}", json=payload or {}, timeout=30)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

SEV_ICON = {1:"🔵",2:"🟢",3:"🟡",4:"🟠",5:"🔴"}

# ── Health check ───────────────────────────────────────────────────
if not get("health"):
    st.error("⚠️ API offline. Run:  python api/api.py")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────
hospitals = get("hospitals") or []
with st.sidebar:
    st.title("🚑 HARA Operations")
    st.caption("Ambulance · Imaging · Network")
    st.divider()

    for h in hospitals:
        icon = "🏥" if h.get("is_main") else "🏨"
        st.markdown(f"**{icon} {h['name']}**")
        st.caption(h["address"])
        beds = h.get("beds_available", 0)
        ambs = h.get("ambulances_available", 0)
        c1, c2 = st.columns(2)
        c1.metric("Beds free", beds)
        c2.metric("Ambulances", ambs)
        machines = h.get("imaging", [])
        avail_m  = sum(1 for m in machines if m["available"])
        st.caption(f"Imaging: {avail_m}/{len(machines)} available")
        st.divider()

    st.caption(f"Refreshed: {datetime.now().strftime('%H:%M:%S')}")
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ── Main ───────────────────────────────────────────────────────────
st.title("🚑 HARA Operations Centre")
st.markdown("Ambulance dispatch · Imaging control · Hospital network · Inter-hospital referrals")

tab1, tab2, tab3, tab4 = st.tabs([
    "🚑 Ambulance Dispatch",
    "🔬 Imaging Control",
    "🌐 Hospital Network",
    "↔️ Referrals",
])


# ══════════════════════════════════════════════════════════════════
#  TAB 1  —  AMBULANCE DISPATCH
# ══════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("🚑 Smart Ambulance Dispatch")
    st.markdown(
        "The routing engine scores **every hospital** on distance, specialist "
        "availability, imaging availability, and bed count — then dispatches "
        "to the best match automatically."
    )

    with st.form("dispatch_form"):
        c1, c2 = st.columns(2)
        with c1:
            d_name    = st.text_input("Patient Name *")
            d_age     = st.number_input("Age *", 0, 120, 40)
            d_condition = st.text_area("Condition / Symptoms *",
                                       placeholder="e.g. Severe chest pain radiating to left arm, sweating, shortness of breath",
                                       height=90)
        with c2:
            d_address = st.text_input("Pickup Address",
                                      placeholder="e.g. 45 Galle Rd, Colombo 03")
            d_lat     = st.number_input("Pickup Latitude  (Colombo ≈ 6.92)",
                                        value=6.9200, format="%.4f", step=0.0001)
            d_lng     = st.number_input("Pickup Longitude (Colombo ≈ 79.86)",
                                        value=79.8500, format="%.4f", step=0.0001)

        go = st.form_submit_button("🚑 Dispatch Ambulance", type="primary",
                                   use_container_width=True)

    if go:
        if not d_name or not d_condition:
            st.error("Name and condition are required.")
        else:
            with st.spinner("🧠 AI routing engine analysing hospitals..."):
                result = post("ambulance/dispatch", {
                    "patient_name":    d_name,
                    "condition":       d_condition,
                    "age":             d_age,
                    "pickup_lat":      d_lat,
                    "pickup_lng":      d_lng,
                    "pickup_address":  d_address,
                })

            if result.get("success"):
                st.success(
                    f"✅ **{result['ambulance']}** dispatched — "
                    f"Driver: {result['driver']}"
                )
                # Destination card
                dest_color = "#dcfce7"
                st.markdown(f"""
<div style="background:{dest_color};border-radius:10px;padding:16px;margin:10px 0;">
  <h4 style="margin:0">🏥 Destination: {result['destination']}</h4>
  <p style="margin:4px 0">
    📍 <b>{result['distance_km']} km</b> away &nbsp;·&nbsp;
    ⏱️ ETA <b>{result['eta_minutes']} minutes</b>
  </p>
  <p style="margin:4px 0">
    👨‍⚕️ Specialist: <b>{result.get('specialist') or 'General'}</b> &nbsp;·&nbsp;
    🔬 Imaging: <b>{result.get('imaging') or 'Not required'}</b>
  </p>
  <p style="margin:6px 0 0;color:#6b7280;font-size:13px">
    <em>{result.get('routing_reason','')}</em>
  </p>
</div>
""", unsafe_allow_html=True)

                # Hospital comparison table
                st.markdown("#### All Hospital Scores")
                st.caption("Lower score = better choice. Destination is highlighted.")
                hosp_data = result.get("all_hospitals", [])
                if hosp_data:
                    for i, h in enumerate(hosp_data):
                        bg = "#dcfce7" if i == 0 else "#f9fafb"
                        label = "✅ CHOSEN" if i == 0 else f"#{i+1}"
                        spec_icon  = "✅" if h["has_specialist"] else "❌"
                        img_icon   = "✅" if h["has_imaging"]    else "❌"
                        st.markdown(f"""
<div style="background:{bg};border-radius:8px;padding:10px 14px;margin:4px 0;
            border:1px solid #e5e7eb;">
  <b>{label} — {h['name']}</b> &nbsp;
  <span style="font-size:13px;color:#6b7280">
    Score: {h['score']} &nbsp;|&nbsp;
    📍 {h['distance_km']} km &nbsp;|&nbsp;
    ⏱️ {h['eta_minutes']} min &nbsp;|&nbsp;
    👨‍⚕️ Specialist {spec_icon} &nbsp;|&nbsp;
    🔬 Imaging {img_icon} &nbsp;|&nbsp;
    🛏️ {h['beds']} beds free
  </span>
</div>
""", unsafe_allow_html=True)
            else:
                st.error(f"Dispatch failed: {result.get('error')}")

    # ── Active dispatches ──────────────────────────────────────────
    st.divider()
    st.subheader("Active & Recent Dispatches")
    dispatches = get("ambulance/dispatches") or []
    if dispatches:
        for d in dispatches:
            status_color = {"dispatched":"🟡","arrived":"🟠","completed":"🟢"}.get(
                d["status"], "⚪")
            with st.expander(
                f"{status_color} {d['ambulance']} → {d['destination']} "
                f"| {d['patient']} | {d['dispatched']}"
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("Distance", f"{d['distance_km']} km")
                c2.metric("ETA",      f"{d['eta_minutes']} min")
                c3.metric("Status",   d["status"].capitalize())
                st.markdown(f"**Condition:** {d['condition']}")
                st.markdown(f"**Pickup:** {d['pickup']}")
                if d.get("specialist"): st.markdown(f"**Specialist needed:** {d['specialist']}")
                if d.get("imaging"):    st.markdown(f"**Imaging needed:** {d['imaging']}")
                st.markdown(f"**Routing reason:** *{d.get('reason','')[:200]}*")
                if d["status"] == "dispatched":
                    if st.button(f"Mark Arrived/Complete — {d['id']}",
                                 key=f"complete_{d['id']}"):
                        post(f"ambulance/{d['id']}/complete")
                        st.rerun()
    else:
        st.info("No dispatches yet.")


# ══════════════════════════════════════════════════════════════════
#  TAB 2  —  IMAGING CONTROL
# ══════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("🔬 Imaging Machine Control")
    st.caption("Toggle machines on/off. Availability is factored into ambulance routing in real time.")

    machines = get("imaging/machines") or []

    # Group by hospital then type
    hosp_groups: dict = {}
    for m in machines:
        hid = m["hospital_id"]
        hosp_groups.setdefault(hid, {}).setdefault(m["machine_type"], []).append(m)

    MACHINE_ICONS = {"X-Ray":"☢️","MRI":"🧲","CT Scanner":"🖥️",
                     "Ultrasound":"🔊","ECG":"💓"}

    for hosp in hospitals:
        hid   = hosp["id"]
        hname = hosp["name"]
        if hid not in hosp_groups:
            continue
        st.markdown(f"### 🏥 {hname}")
        type_groups = hosp_groups[hid]
        cols = st.columns(len(type_groups))
        for col_idx, (mtype, mlist) in enumerate(type_groups.items()):
            with cols[col_idx]:
                icon = MACHINE_ICONS.get(mtype, "🔬")
                st.markdown(f"**{icon} {mtype}**")
                for machine in mlist:
                    avail = machine["is_available"]
                    label = f"{'🟢' if avail else '🔴'} {machine['name']}"
                    if st.button(label, key=f"toggle_{machine['id']}",
                                 help="Click to toggle availability"):
                        result = post(f"imaging/machines/{machine['id']}/toggle")
                        if result.get("success"):
                            new_status = "available" if result["is_available"] else "offline"
                            st.success(f"{result['machine']} → {new_status}")
                        st.rerun()
        st.divider()

    # ── Imaging requests ───────────────────────────────────────────
    st.subheader("📋 Imaging Requests")
    requests_data = get("imaging/requests") or []
    if requests_data:
        df = pd.DataFrame(requests_data)
        st.dataframe(df[["patient","machine_type","machine","status",
                          "reason","requested"]],
                     hide_index=True, use_container_width=True)
    else:
        st.info("No imaging requests yet.")

    # ── Manual imaging request ─────────────────────────────────────
    st.divider()
    st.subheader("➕ Request Imaging for Patient")
    all_patients = (get("patients/all") or {}).get("patients", [])
    if all_patients:
        admitted_p = [p for p in all_patients if p["status"] == "admitted"]
        if admitted_p:
            with st.form("imaging_req_form"):
                p_opts = {f"{p['name']} ({p['ward']})": p["id"] for p in admitted_p}
                sel_p  = st.selectbox("Patient", list(p_opts.keys()))
                mtype  = st.selectbox("Imaging Type",
                                      ["X-Ray","MRI","CT Scanner","Ultrasound","ECG"])
                reason = st.text_input("Clinical Reason")

                # Show availability for chosen type
                hosp_id = next((p["hospital_id"] for p in admitted_p
                                 if p["id"] == p_opts.get(sel_p)), 1)
                avail_machines = [
                    m for m in machines
                    if m["hospital_id"] == hosp_id
                    and m["machine_type"] == mtype
                    and m["is_available"]
                ]
                if avail_machines:
                    st.success(f"✅ {len(avail_machines)} {mtype} machine(s) available")
                else:
                    st.warning(f"⚠️ No {mtype} available at this hospital — "
                                "dispatch will route to partner hospital")

                if st.form_submit_button("Request Imaging", type="primary"):
                    r = post("imaging/request", {
                        "patient_id":  p_opts[sel_p],
                        "machine_type": mtype,
                        "hospital_id": hosp_id,
                        "reason": reason,
                    })
                    if r.get("success"):
                        if r.get("available"):
                            st.success(f"✅ Assigned to {r['machine']}")
                        else:
                            st.warning("⚠️ No machine available — marked pending")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════
#  TAB 3  —  HOSPITAL NETWORK
# ══════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🌐 Hospital Network Overview")

    for hosp in hospitals:
        badge  = "🏥 MAIN" if hosp.get("is_main") else "🏨 PARTNER"
        bg     = "#eff6ff" if hosp.get("is_main") else "#f0fdf4"
        st.markdown(f"""
<div style="background:{bg};border-radius:10px;padding:16px;margin-bottom:12px;
            border:1px solid #e5e7eb;">
  <h4 style="margin:0">{badge} — {hosp['name']}</h4>
  <p style="margin:4px 0;color:#6b7280">{hosp['address']} · {hosp.get('phone','')}</p>
  <p style="margin:4px 0">
    🛏️ <b>{hosp['beds_available']}</b> beds free &nbsp;·&nbsp;
    🚑 <b>{hosp['ambulances_available']}</b> ambulances available &nbsp;·&nbsp;
    📍 GPS: {hosp['lat']:.4f}, {hosp['lng']:.4f}
  </p>
</div>
""", unsafe_allow_html=True)

        # Imaging summary
        machines_h = hosp.get("imaging", [])
        if machines_h:
            by_type: dict = {}
            for m in machines_h:
                by_type.setdefault(m["type"], []).append(m)
            cols = st.columns(len(by_type))
            for ci, (mtype, mlist) in enumerate(by_type.items()):
                avail = sum(1 for m in mlist if m["available"])
                icon  = MACHINE_ICONS.get(mtype, "🔬")
                color = "#16a34a" if avail > 0 else "#dc2626"
                with cols[ci]:
                    st.markdown(
                        f"{icon} **{mtype}**<br>"
                        f"<span style='color:{color}'>{avail}/{len(mlist)} available</span>",
                        unsafe_allow_html=True
                    )
        st.divider()

    # Distance matrix
    st.subheader("📍 Distance Matrix")
    if len(hospitals) >= 2:
        import math
        def hdist(h1, h2):
            R = 6371.0
            d1 = math.radians(h2["lat"]-h1["lat"])
            d2 = math.radians(h2["lng"]-h1["lng"])
            a  = math.sin(d1/2)**2 + math.cos(math.radians(h1["lat"])) * \
                 math.cos(math.radians(h2["lat"])) * math.sin(d2/2)**2
            return round(R*2*math.atan2(math.sqrt(a),math.sqrt(1-a)), 2)

        rows = []
        for h1 in hospitals:
            row = {"Hospital": h1["name"]}
            for h2 in hospitals:
                d = hdist(h1, h2)
                row[h2["name"]] = f"{d} km" if d > 0 else "—"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows).set_index("Hospital"),
                     use_container_width=True)

    # Ambulance fleet
    st.subheader("🚑 Ambulance Fleet")
    ambs = get("ambulances") or []
    if ambs:
        for hosp in hospitals:
            hosp_ambs = [a for a in ambs if a["hospital_id"] == hosp["id"]]
            if hosp_ambs:
                st.markdown(f"**{hosp['name']}**")
                cols = st.columns(min(len(hosp_ambs), 3))
                for i, a in enumerate(hosp_ambs):
                    with cols[i % 3]:
                        color = "#16a34a" if a["is_available"] else "#dc2626"
                        st.markdown(
                            f"<div style='padding:8px;border-radius:6px;"
                            f"border:1px solid {color};margin:4px'>"
                            f"<b>{a['call_sign']}</b><br>"
                            f"<span style='font-size:13px'>{a['driver']}</span><br>"
                            f"<span style='color:{color};font-size:12px'>"
                            f"{'Available' if a['is_available'] else 'On duty'}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )


# ══════════════════════════════════════════════════════════════════
#  TAB 4  —  REFERRALS
# ══════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("↔️ Inter-Hospital Referrals")
    st.caption("Created automatically when ambulance routing selects a non-local hospital.")

    referrals = get("referrals") or []
    if referrals:
        status_icon = {"pending":"⏳","en-route":"🚑","received":"✅","completed":"🏁"}
        for r in referrals:
            icon = status_icon.get(r["status"], "⚪")
            with st.expander(
                f"{icon} {r['patient']} — {r['from']} → {r['to']} — {r['created']}"
            ):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**From:** {r['from']}")
                c2.markdown(f"**To:** {r['to']}")
                c3.markdown(f"**Status:** {r['status'].capitalize()}")
                if r.get("specialist"): st.markdown(f"**Specialist:** {r['specialist']}")
                if r.get("imaging"):    st.markdown(f"**Imaging:** {r['imaging']}")
                st.markdown(f"**Reason:** *{r.get('reason','')[:300]}*")
    else:
        st.info("No inter-hospital referrals yet. Dispatch an ambulance to generate one.")
