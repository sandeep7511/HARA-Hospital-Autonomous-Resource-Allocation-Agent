"""
HARA Flask API  —  http://localhost:5001
"""
import os, sys, json, re, math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

from database.db import get_session
from database.models import (
    Hospital, Ward, Bed, Patient, Staff,
    ImagingMachine, ImagingRequest, Ambulance, AmbulanceDispatch,
    PatientVitals, InterHospitalReferral, DecisionLog, TriageReport,
)

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model_flash = genai.GenerativeModel("gemini-2.5-flash")
model_pro = genai.GenerativeModel("gemini-2.5-flash-lite")

app = Flask(__name__)
CORS(app)


# ═══════════════════════════════════════════════════════════════════
#  GEMINI HELPERS
# ═══════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0).strip() if m else text.strip()


def call_gemini(prompt: str) -> dict:
    for mdl, label in [(model_flash, "flash"), (model_pro, "pro")]:
        for attempt in range(1, 3):
            try:
                resp = mdl.generate_content(prompt)
                raw  = resp.text
                if not raw or not raw.strip():
                    continue
                return json.loads(_extract_json(raw))
            except Exception as e:
                print(f"[Gemini-{label}] attempt {attempt}: {e}")
    raise ValueError("All Gemini attempts failed.")


# ═══════════════════════════════════════════════════════════════════
#  DISTANCE & ROUTING ENGINE
# ═══════════════════════════════════════════════════════════════════

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Real-world distance between two GPS coordinates in km."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def eta_minutes(distance_km: float) -> int:
    """Estimate ambulance travel time (avg 40 km/h in city traffic)."""
    return max(5, int((distance_km / 40.0) * 60))


def score_hospital(db, hospital, pickup_lat, pickup_lng,
                   specialist_needed=None, imaging_needed=None) -> dict:
    """
    Score a hospital for ambulance routing. Lower score = better choice.
    Factors: distance (1km = 1pt) + missing specialist (50pt)
           + missing imaging (30pt) + no beds (100pt)
    """
    dist = haversine_km(pickup_lat, pickup_lng, hospital.lat, hospital.lng)
    score = dist

    # Check specialist
    has_specialist = False
    if specialist_needed:
        has_specialist = db.query(Staff).filter(
            Staff.hospital_id == hospital.id,
            Staff.specialty.ilike(f"%{specialist_needed}%"),
            Staff.is_available == True,
        ).first() is not None
        if not has_specialist:
            score += 50

    # Check imaging
    has_imaging = True
    if imaging_needed:
        has_imaging = db.query(ImagingMachine).filter(
            ImagingMachine.hospital_id == hospital.id,
            ImagingMachine.machine_type == imaging_needed,
            ImagingMachine.is_available == True,
        ).first() is not None
        if not has_imaging:
            score += 30

    # Check beds
    total_free = sum(
        w.available_beds for w in
        db.query(Ward).filter(Ward.hospital_id == hospital.id).all()
    )
    if total_free == 0:
        score += 100

    return {
        "hospital":        hospital,
        "distance_km":     round(dist, 2),
        "eta_minutes":     eta_minutes(dist),
        "score":           round(score, 2),
        "has_specialist":  has_specialist,
        "has_imaging":     has_imaging,
        "beds_available":  total_free,
    }


def find_best_hospital(db, pickup_lat, pickup_lng,
                       specialist_needed=None, imaging_needed=None) -> list:
    """Return all hospitals ranked by routing score."""
    hospitals = db.query(Hospital).all()
    ranked = [
        score_hospital(db, h, pickup_lat, pickup_lng,
                       specialist_needed, imaging_needed)
        for h in hospitals
    ]
    return sorted(ranked, key=lambda x: x["score"])


# ═══════════════════════════════════════════════════════════════════
#  RULE FALLBACKS
# ═══════════════════════════════════════════════════════════════════

def rule_based_allocation(patient: dict) -> dict:
    sev, age = patient["severity"], patient["age"]
    if sev == 5:   ward, role, level = "ICU",       "Surgeon",   "critical"
    elif sev == 4: ward, role, level = "Emergency", "ER Doctor", "warning"
    elif sev == 3: ward, role, level = "Emergency", "Doctor",    "warning"
    elif age < 16: ward, role, level = "Pediatric", "Doctor",    "normal"
    else:          ward, role, level = "General",   "Nurse",     "normal"
    return {"ward": ward, "staff_role": role,
            "action": "ESCALATE" if sev == 5 else "ADMIT",
            "reasoning": f"Rule-based: severity {sev} -> {ward}.",
            "severity_level": level}


def rule_based_triage(patient) -> dict:
    sev = patient.severity
    labels = {1:"Trivial",2:"Minor",3:"Moderate",4:"Serious",5:"Critical"}
    waits  = {1:"60+ min",2:"30-60 min",3:"15-30 min",4:"5-15 min",5:"Immediate"}
    refs   = {1:"General Physician",2:"General Physician",3:"General Physician",
              4:"Emergency Physician",5:"Emergency Physician / Surgeon"}
    return {
        "severity_score":     sev,
        "severity_label":     labels.get(sev, "Moderate"),
        "estimated_wait":     waits.get(sev, "15-30 min"),
        "doctor_referral":    refs.get(sev, "General Physician"),
        "specialist_needed":  "Cardiologist" if sev >= 4 else None,
        "imaging_needed":     "CT Scanner"   if sev == 5 else None,
        "gemini_reasoning":   f"Rule-based triage: {patient.condition}. Severity {sev}.",
        "first_aid_steps":    [
            "Record vital signs immediately",
            "Ensure clear airway and adequate ventilation",
            "Establish IV access if severity >= 4",
            "Apply oxygen if SpO2 < 94%",
            "Notify attending physician",
        ],
        "medicines": [
            {"name":"Paracetamol","dose":"500-1000mg","route":"oral","purpose":"Pain/fever relief"},
            {"name":"Normal Saline","dose":"500ml","route":"IV","purpose":"Fluid support"},
        ],
        "nurse_instructions": [
            "Vitals every 5 minutes for severity >= 4, every 15 minutes otherwise",
            "Cardiac monitor and pulse oximeter attached",
            "IV line established, blood drawn for baseline investigations",
            "Family informed of status and estimated wait",
        ],
    }


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def hospital_snapshot(db, hospital_id=None):
    q = db.query(Ward)
    if hospital_id:
        q = q.filter(Ward.hospital_id == hospital_id)
    wards = q.all()
    ward_info = [{"name": w.name, "hospital_id": w.hospital_id,
                  "available_beds": w.available_beds,
                  "total_beds": w.total_beds} for w in wards]
    roles = ["Doctor", "ER Doctor", "Nurse", "Surgeon", "On-Call", "Specialist"]
    sq = db.query(Staff)
    if hospital_id:
        sq = sq.filter(Staff.hospital_id == hospital_id)
    staff_info = {
        r: {"total":     sq.filter(Staff.role == r).count(),
            "available": sq.filter(Staff.role == r,
                                   Staff.is_available == True).count()}
        for r in roles
    }
    return {"wards": ward_info, "staff": staff_info}


def ask_gemini_allocation(patient: dict, snapshot: dict) -> dict:
    prompt = (
        "Task: hospital bed allocation. Reply with JSON only.\n"
        f"Patient age {patient['age']}, severity {patient['severity']}/5, "
        f"complaint: {patient['condition']}.\n"
        f"Wards: { {w['name']: w['available_beds'] for w in snapshot['wards']} }\n"
        "Severity 5->ICU, 4->Emergency, 3->Emergency/General, 1-2->General, <16->Pediatric.\n"
        "Staff: 5->Surgeon, 4->ER Doctor, 3->Doctor, 1-2->Nurse.\n"
        'Reply: {"ward":"General","staff_role":"Nurse","action":"ADMIT",'
        '"reasoning":"reason","severity_level":"normal"}'
    )
    try:
        return call_gemini(prompt)
    except Exception as e:
        print(f"[Allocation] fallback: {e}")
        return rule_based_allocation(patient)


def ask_gemini_triage(patient, waiting_count, snap, vitals=None) -> dict:
    vitals_str = ""
    if vitals:
        vitals_str = (
            f"Vitals: Temp {vitals.get('temperature','N/A')}°C, "
            f"BP {vitals.get('bp_systolic','N/A')}/{vitals.get('bp_diastolic','N/A')} mmHg, "
            f"HR {vitals.get('heart_rate','N/A')} bpm, "
            f"SpO2 {vitals.get('spo2','N/A')}%, "
            f"Weight {vitals.get('weight_kg','N/A')}kg, "
            f"Height {vitals.get('height_cm','N/A')}cm, "
            f"BMI {vitals.get('bmi','N/A')}. "
        )
    ward_summary = " | ".join(
        f"{w['name']}: {w['available_beds']} free" for w in snap["wards"]
    )
    prompt = (
        "Task: Conduct a comprehensive clinical triage. Reply with JSON only.\n"
        f"Patient age {patient.age}, complaint: {patient.condition}. "
        f"Notes: {patient.notes or 'none'}. Severity estimate: {patient.severity}/5. "
        f"{vitals_str}"
        f"Queue ahead: {max(0,waiting_count-1)}. Wards: {ward_summary}.\n"
        "Instructions:\n"
        "1. Adjust severity (1-5) based on vitals and condition.\n"
        "2. Determine specialist and imaging needs.\n"
        "3. Generate 3-4 specific, actionable first aid steps.\n"
        "4. Prescribe 1-3 appropriate emergency medicines with accurate dose, route, and purpose.\n"
        "5. Provide 2-3 specific nurse monitoring instructions.\n"
        "Reply EXACTLY with this JSON structure:\n"
        "{\n"
        '  "severity_score": 3,\n'
        '  "severity_label": "Moderate",\n'
        '  "estimated_wait": "15-30 min",\n'
        '  "doctor_referral": "General Physician",\n'
        '  "specialist_needed": "Cardiologist or null",\n'
        '  "imaging_needed": "CT Scanner or null",\n'
        '  "gemini_reasoning": "Clinical reasoning here...",\n'
        '  "first_aid_steps": ["step 1", "step 2"],\n'
        '  "medicines": [{"name":"Aspirin","dose":"300mg","route":"oral","purpose":"Anti-platelet"}],\n'
        '  "nurse_instructions": ["instruction 1", "instruction 2"]\n'
        "}"
    )
    try:
        result = call_gemini(prompt)
        result["severity_score"] = max(1, min(5, int(result.get("severity_score", patient.severity))))
        for k in ["first_aid_steps","medicines","nurse_instructions"]:
            if k not in result or not result[k]:
                result[k] = rule_based_triage(patient)[k]
        return result
    except Exception as e:
        print(f"[Triage] fallback: {e}")
        return rule_based_triage(patient)


def ask_gemini_ambulance(condition: str, age: int) -> dict:
    """Determine what specialist and imaging a patient needs based on symptoms."""
    prompt = (
        "Task: determine hospital requirements for ambulance routing. JSON only.\n"
        f"Patient age {age}, condition: {condition}.\n"
        "Determine specialist and imaging needed.\n"
        "Specialists: Cardiologist, Neurologist, Orthopaedic Surgeon, "
        "General Physician, Paediatrician, Emergency Physician, Radiologist.\n"
        "Imaging: X-Ray, MRI, CT Scanner, Ultrasound, ECG, null.\n"
        '{"specialist_needed":"Cardiologist","imaging_needed":"ECG",'
        '"urgency":"emergency","reasoning":"brief reason"}'
    )
    try:
        return call_gemini(prompt)
    except Exception:
        return {"specialist_needed": "Emergency Physician",
                "imaging_needed": None, "urgency": "urgent",
                "reasoning": "Rule-based assessment."}


# ═══════════════════════════════════════════════════════════════════
#  ROUTES — BASIC
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


@app.route("/api/hospitals", methods=["GET"])
def get_hospitals():
    db = get_session()
    try:
        hospitals = db.query(Hospital).all()
        result = []
        for h in hospitals:
            snap = hospital_snapshot(db, h.id)
            total_free = sum(w["available_beds"] for w in snap["wards"])
            machines   = db.query(ImagingMachine).filter(
                ImagingMachine.hospital_id == h.id).all()
            ambs_avail = db.query(Ambulance).filter(
                Ambulance.hospital_id == h.id,
                Ambulance.is_available == True).count()
            result.append({
                "id": h.id, "name": h.name, "address": h.address,
                "lat": h.lat, "lng": h.lng, "phone": h.phone,
                "is_main": h.is_main, "beds_available": total_free,
                "ambulances_available": ambs_avail,
                "imaging": [{"id": m.id, "type": m.machine_type,
                             "name": m.name, "available": m.is_available}
                            for m in machines],
            })
        return jsonify(result)
    finally:
        db.close()


@app.route("/api/status", methods=["GET"])
def get_status():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        snap = hospital_snapshot(db, hospital_id)
        snap["waiting_count"]  = db.query(Patient).filter(
            Patient.status == "waiting",
            *([Patient.hospital_id == hospital_id] if hospital_id else [])).count()
        snap["admitted_count"] = db.query(Patient).filter(
            Patient.status == "admitted",
            *([Patient.hospital_id == hospital_id] if hospital_id else [])).count()
        snap["critical_count"] = db.query(Patient).filter(
            Patient.severity == 5, Patient.status != "discharged",
            *([Patient.hospital_id == hospital_id] if hospital_id else [])).count()
        snap["timestamp"] = datetime.now().isoformat()
        return jsonify(snap)
    finally:
        db.close()


@app.route("/api/wards", methods=["GET"])
def get_wards():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(Ward)
        if hospital_id:
            q = q.filter(Ward.hospital_id == hospital_id)
        return jsonify([
            {"id": w.id, "name": w.name, "hospital_id": w.hospital_id,
             "total_beds": w.total_beds, "available_beds": w.available_beds}
            for w in q.all()
        ])
    finally:
        db.close()


@app.route("/api/wards/update", methods=["POST"])
def update_ward_beds():
    data = request.json
    db   = get_session()
    try:
        w = db.query(Ward).filter(Ward.id == int(data["ward_id"])).first()
        if w:
            w.available_beds = int(data["available_beds"])
            db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/staff", methods=["GET"])
def get_staff():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(Staff)
        if hospital_id:
            q = q.filter(Staff.hospital_id == hospital_id)
        return jsonify([
            {"id": s.id, "name": s.name, "role": s.role,
             "specialty": s.specialty, "shift": s.shift,
             "is_available": s.is_available, "hospital_id": s.hospital_id}
            for s in q.order_by(Staff.role, Staff.name).all()
        ])
    finally:
        db.close()


@app.route("/api/staff/update", methods=["POST"])
def update_staff():
    data = request.json
    db   = get_session()
    try:
        for item in data["staff"]:
            s = db.query(Staff).filter(Staff.id == int(item["id"])).first()
            if s:
                s.is_available = item["is_available"]
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  IMAGING
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/imaging/machines", methods=["GET"])
def get_imaging_machines():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(ImagingMachine)
        if hospital_id:
            q = q.filter(ImagingMachine.hospital_id == hospital_id)
        return jsonify([
            {"id": m.id, "hospital_id": m.hospital_id,
             "machine_type": m.machine_type, "name": m.name,
             "is_available": m.is_available, "notes": m.notes}
            for m in q.order_by(ImagingMachine.hospital_id,
                                 ImagingMachine.machine_type).all()
        ])
    finally:
        db.close()


@app.route("/api/imaging/machines/<int:machine_id>/toggle", methods=["POST"])
def toggle_imaging_machine(machine_id):
    db = get_session()
    try:
        m = db.query(ImagingMachine).filter(ImagingMachine.id == machine_id).first()
        if not m:
            return jsonify({"success": False, "error": "Machine not found"}), 404
        m.is_available = not m.is_available
        db.commit()
        return jsonify({"success": True, "is_available": m.is_available,
                        "machine": m.name})
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/imaging/request", methods=["POST"])
def request_imaging():
    data = request.json
    db   = get_session()
    try:
        patient    = db.query(Patient).filter(
            Patient.id == int(data["patient_id"])).first()
        mtype      = data["machine_type"]
        hospital_id = int(data.get("hospital_id", patient.hospital_id or 1))

        # Find available machine of this type
        machine = db.query(ImagingMachine).filter(
            ImagingMachine.hospital_id  == hospital_id,
            ImagingMachine.machine_type == mtype,
            ImagingMachine.is_available == True,
        ).first()

        req = ImagingRequest(
            patient_id  = patient.id,
            hospital_id = hospital_id,
            machine_type = mtype,
            machine_id  = machine.id if machine else None,
            reason      = data.get("reason", ""),
            status      = "in-progress" if machine else "pending",
        )
        db.add(req)
        db.commit()
        return jsonify({
            "success":   True,
            "machine":   machine.name if machine else None,
            "available": machine is not None,
            "status":    req.status,
        })
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/imaging/requests", methods=["GET"])
def get_imaging_requests():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(ImagingRequest)
        if hospital_id:
            q = q.filter(ImagingRequest.hospital_id == hospital_id)
        reqs = q.order_by(ImagingRequest.requested_at.desc()).limit(50).all()
        return jsonify([{
            "id":          r.id,
            "patient":     r.patient.name if r.patient else "N/A",
            "machine_type":r.machine_type,
            "machine":     r.machine.name if r.machine else "Unassigned",
            "status":      r.status,
            "reason":      r.reason,
            "requested":   r.requested_at.strftime("%d %b %H:%M"),
        } for r in reqs])
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  AMBULANCE DISPATCH  —  smart routing engine
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/ambulance/dispatch", methods=["POST"])
def dispatch_ambulance():
    """
    Smart ambulance dispatch:
    1. Gemini determines specialist + imaging needed from symptoms
    2. Score ALL hospitals on distance + specialist + imaging + beds
    3. Dispatch ambulance from nearest available hospital
    4. Create referral log if non-nearest hospital chosen
    """
    data = request.json
    db   = get_session()
    try:
        patient_name  = data["patient_name"]
        condition     = data["condition"]
        age           = int(data.get("age", 30))
        pickup_lat    = float(data["pickup_lat"])
        pickup_lng    = float(data["pickup_lng"])
        pickup_addr   = data.get("pickup_address", "")

        # Step 1 — Gemini determines needs
        needs = ask_gemini_ambulance(condition, age)
        specialist = needs.get("specialist_needed")
        imaging    = needs.get("imaging_needed")
        ai_reason  = needs.get("reasoning", "")

        # Step 2 — Score all hospitals
        ranked = find_best_hospital(db, pickup_lat, pickup_lng, specialist, imaging)
        best   = ranked[0]
        dest_hospital = best["hospital"]

        # Build routing explanation
        routing_parts = [f"Routed to {dest_hospital.name} (score {best['score']})."]
        if specialist:
            routing_parts.append(
                f"Specialist needed: {specialist} — "
                f"{'Available' if best['has_specialist'] else 'NOT available (nearest option)'}."
            )
        if imaging:
            routing_parts.append(
                f"Imaging needed: {imaging} — "
                f"{'Available' if best['has_imaging'] else 'NOT available at this hospital'}."
            )
        routing_parts.append(
            f"Distance: {best['distance_km']} km, ETA: {best['eta_minutes']} min. "
            f"Beds available: {best['beds_available']}."
        )
        routing_reason = " ".join(routing_parts) + f" AI assessment: {ai_reason}"

        # Step 3 — Find available ambulance (prefer nearest hospital)
        nearest_hosp_dist = min(ranked, key=lambda x: x["distance_km"])
        ambulance = db.query(Ambulance).filter(
            Ambulance.hospital_id == nearest_hosp_dist["hospital"].id,
            Ambulance.is_available == True,
        ).first()
        if not ambulance:
            # Try any available ambulance
            ambulance = db.query(Ambulance).filter(
                Ambulance.is_available == True).first()
        if not ambulance:
            return jsonify({"success": False,
                            "error": "No ambulances available."}), 503

        ambulance.is_available = False

        dispatch = AmbulanceDispatch(
            ambulance_id      = ambulance.id,
            patient_name      = patient_name,
            patient_condition = condition,
            pickup_lat        = pickup_lat,
            pickup_lng        = pickup_lng,
            pickup_address    = pickup_addr,
            destination_id    = dest_hospital.id,
            distance_km       = best["distance_km"],
            eta_minutes       = best["eta_minutes"],
            specialist_needed = specialist,
            imaging_needed    = imaging,
            routing_reason    = routing_reason,
            status            = "dispatched",
        )
        db.add(dispatch)
        db.flush()

        # Step 4 — Create referral if destination is not the main/nearest
        from_hospital = db.query(Hospital).filter(Hospital.is_main == True).first()
        if from_hospital and from_hospital.id != dest_hospital.id:
            db.add(InterHospitalReferral(
                patient_name          = patient_name,
                from_hospital_id      = from_hospital.id,
                to_hospital_id        = dest_hospital.id,
                specialist_needed     = specialist,
                imaging_needed        = imaging,
                reason                = routing_reason,
                ambulance_dispatch_id = dispatch.id,
                status                = "en-route",
            ))

        # Log decision
        db.add(DecisionLog(
            hospital_id    = dest_hospital.id,
            action_type    = "AMBULANCE_DISPATCH",
            patient_name   = patient_name,
            reasoning      = routing_reason,
            action_taken   = (
                f"Dispatched {ambulance.call_sign} to {pickup_addr or 'pickup location'}. "
                f"Destination: {dest_hospital.name}. ETA: {best['eta_minutes']} min."
            ),
            severity_level = "critical" if needs.get("urgency") == "emergency" else "warning",
        ))

        db.commit()

        return jsonify({
            "success":         True,
            "ambulance":       ambulance.call_sign,
            "driver":          ambulance.driver_name,
            "destination":     dest_hospital.name,
            "destination_lat": dest_hospital.lat,
            "destination_lng": dest_hospital.lng,
            "distance_km":     best["distance_km"],
            "eta_minutes":     best["eta_minutes"],
            "specialist":      specialist,
            "imaging":         imaging,
            "routing_reason":  routing_reason,
            "all_hospitals":   [
                {"name":          r["hospital"].name,
                 "distance_km":   r["distance_km"],
                 "eta_minutes":   r["eta_minutes"],
                 "score":         r["score"],
                 "has_specialist":r["has_specialist"],
                 "has_imaging":   r["has_imaging"],
                 "beds":          r["beds_available"]}
                for r in ranked
            ],
        })
    except Exception as e:
        db.rollback()
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/ambulance/dispatches", methods=["GET"])
def get_dispatches():
    db = get_session()
    try:
        dispatches = db.query(AmbulanceDispatch).order_by(
            AmbulanceDispatch.dispatched_at.desc()).limit(50).all()
        return jsonify([{
            "id":           d.id,
            "ambulance":    d.ambulance.call_sign,
            "patient":      d.patient_name,
            "condition":    d.patient_condition,
            "pickup":       d.pickup_address or f"{d.pickup_lat:.4f},{d.pickup_lng:.4f}",
            "destination":  d.destination.name,
            "distance_km":  d.distance_km,
            "eta_minutes":  d.eta_minutes,
            "specialist":   d.specialist_needed,
            "imaging":      d.imaging_needed,
            "status":       d.status,
            "dispatched":   d.dispatched_at.strftime("%d %b %H:%M"),
            "reason":       d.routing_reason,
        } for d in dispatches])
    finally:
        db.close()


@app.route("/api/ambulance/<int:dispatch_id>/complete", methods=["POST"])
def complete_dispatch(dispatch_id):
    db = get_session()
    try:
        d = db.query(AmbulanceDispatch).filter(
            AmbulanceDispatch.id == dispatch_id).first()
        if not d:
            return jsonify({"success": False, "error": "Dispatch not found"}), 404
        d.status       = "completed"
        d.completed_at = datetime.now()
        if d.ambulance:
            d.ambulance.is_available = True
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/ambulances", methods=["GET"])
def get_ambulances():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(Ambulance)
        if hospital_id:
            q = q.filter(Ambulance.hospital_id == hospital_id)
        return jsonify([{
            "id": a.id, "call_sign": a.call_sign, "driver": a.driver_name,
            "is_available": a.is_available, "hospital_id": a.hospital_id,
        } for a in q.all()])
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  VITALS
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/vitals/add", methods=["POST"])
def add_vitals():
    data = request.json
    db   = get_session()
    try:
        h  = data.get("height_cm")
        w  = data.get("weight_kg")
        bmi = round(w / ((h / 100) ** 2), 1) if h and w and h > 0 else None
        v = PatientVitals(
            patient_id   = int(data["patient_id"]),
            temperature  = data.get("temperature"),
            bp_systolic  = data.get("bp_systolic"),
            bp_diastolic = data.get("bp_diastolic"),
            heart_rate   = data.get("heart_rate"),
            height_cm    = h,
            weight_kg    = w,
            bmi          = bmi,
            spo2         = data.get("spo2"),
            recorded_by  = data.get("recorded_by", "Triage Nurse"),
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        return jsonify({"success": True, "bmi": bmi, "vitals_id": v.id})
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/vitals/<int:patient_id>", methods=["GET"])
def get_vitals(patient_id):
    db = get_session()
    try:
        v = db.query(PatientVitals).filter(
            PatientVitals.patient_id == patient_id
        ).order_by(PatientVitals.recorded_at.desc()).first()
        if not v:
            return jsonify({"success": False}), 404
        return jsonify({
            "success":     True,
            "temperature": v.temperature,
            "bp_systolic": v.bp_systolic,
            "bp_diastolic":v.bp_diastolic,
            "heart_rate":  v.heart_rate,
            "height_cm":   v.height_cm,
            "weight_kg":   v.weight_kg,
            "bmi":         v.bmi,
            "spo2":        v.spo2,
            "recorded_at": v.recorded_at.strftime("%d %b %Y %H:%M"),
            "recorded_by": v.recorded_by,
        })
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  PATIENTS
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/patients/add", methods=["POST"])
def add_patient():
    data = request.json
    db   = get_session()
    try:
        p = Patient(
            hospital_id = int(data.get("hospital_id", 1)),
            name        = data["name"],
            age         = int(data["age"]),
            condition   = data["condition"],
            severity    = int(data["severity"]),
            status      = "waiting",
            notes       = data.get("notes", ""),
            admitted_at = datetime.now(),
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return jsonify({"success": True, "patient_id": p.id, "name": p.name})
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/patients/waiting", methods=["GET"])
def get_waiting():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(Patient).filter(Patient.status == "waiting")
        if hospital_id:
            q = q.filter(Patient.hospital_id == hospital_id)
        patients = q.order_by(Patient.severity.desc()).all()
        return jsonify({"count": len(patients), "patients": [
            {"id": p.id, "name": p.name, "age": p.age,
             "condition": p.condition, "severity": p.severity,
             "hospital_id": p.hospital_id}
            for p in patients
        ]})
    finally:
        db.close()


@app.route("/api/patients/all", methods=["GET"])
def get_all_patients():
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(Patient)
        if hospital_id:
            q = q.filter(Patient.hospital_id == hospital_id)
        rows = []
        for p in q.order_by(Patient.severity.desc()).all():
            ward_obj = db.query(Ward).filter(Ward.id == p.ward_id).first()
            bed_obj  = db.query(Bed).filter(Bed.id == p.bed_id).first()
            rows.append({
                "id": p.id, "name": p.name, "age": p.age,
                "condition": p.condition, "severity": p.severity,
                "status": p.status,
                "ward":  ward_obj.name if ward_obj else "",
                "bed":   bed_obj.room_number if bed_obj else "",
                "hospital_id": p.hospital_id,
                "admitted": p.admitted_at.strftime("%d %b %H:%M") if p.admitted_at else "",
            })
        return jsonify({"patients": rows})
    finally:
        db.close()


@app.route("/api/discharge", methods=["POST"])
def discharge():
    data = request.json
    db   = get_session()
    try:
        patient = db.query(Patient).filter(
            Patient.id == int(data["patient_id"])).first()
        if not patient:
            return jsonify({"success": False, "error": "Not found"}), 404
        if patient.bed_id:
            bed = db.query(Bed).filter(Bed.id == patient.bed_id).first()
            if bed: bed.status = "available"; bed.patient_id = None
        if patient.ward_id:
            ward = db.query(Ward).filter(Ward.id == patient.ward_id).first()
            if ward: ward.available_beds += 1
        patient.status = "discharged"; patient.ward_id = None; patient.bed_id = None
        db.add(DecisionLog(
            action_type="DISCHARGE", patient_name=patient.name,
            reasoning="Patient stable, cleared for discharge.",
            action_taken=f"{patient.name} discharged.",
            severity_level="normal",
        ))
        db.commit()
        return jsonify({"success": True, "message": f"{patient.name} discharged."})
    except Exception as e:
        db.rollback(); return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  TRIAGE
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/triage", methods=["POST"])
def run_triage():
    data       = request.json
    patient_id = int(data["patient_id"])
    vitals     = data.get("vitals")   # optional vitals dict
    db         = get_session()
    try:
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            return jsonify({"success": False, "error": "Patient not found"}), 404

        # Save vitals first if provided
        if vitals:
            h   = vitals.get("height_cm")
            w   = vitals.get("weight_kg")
            bmi = round(w / ((h / 100) ** 2), 1) if h and w and h > 0 else None
            db.add(PatientVitals(
                patient_id   = patient.id,
                temperature  = vitals.get("temperature"),
                bp_systolic  = vitals.get("bp_systolic"),
                bp_diastolic = vitals.get("bp_diastolic"),
                heart_rate   = vitals.get("heart_rate"),
                height_cm    = h, weight_kg = w, bmi = bmi,
                spo2         = vitals.get("spo2"),
                recorded_by  = "Triage Nurse",
            ))
            db.flush()

        snap          = hospital_snapshot(db, patient.hospital_id)
        waiting_count = db.query(Patient).filter(Patient.status == "waiting").count()
        triage        = ask_gemini_triage(patient, waiting_count, snap, vitals)

        db.add(TriageReport(
            patient_id         = patient.id,
            severity_score     = triage["severity_score"],
            severity_label     = str(triage["severity_label"]),
            first_aid_steps    = json.dumps(triage["first_aid_steps"]),
            medicines          = json.dumps(triage["medicines"]),
            doctor_referral    = str(triage["doctor_referral"]),
            specialist_needed  = triage.get("specialist_needed"),
            imaging_needed     = triage.get("imaging_needed"),
            nurse_instructions = json.dumps(triage["nurse_instructions"]),
            estimated_wait     = str(triage["estimated_wait"]),
            gemini_reasoning   = str(triage["gemini_reasoning"]),
        ))

        patient.severity = triage["severity_score"]

        db.add(DecisionLog(
            hospital_id    = patient.hospital_id,
            action_type    = "TRIAGE",
            patient_name   = patient.name,
            reasoning      = triage["gemini_reasoning"],
            action_taken   = (
                f"Triaged: {triage['severity_label']} (sev {triage['severity_score']}). "
                f"Referred to {triage['doctor_referral']}. "
                f"Wait: {triage['estimated_wait']}."
                + (f" Specialist: {triage.get('specialist_needed')}." if triage.get('specialist_needed') else "")
                + (f" Imaging: {triage.get('imaging_needed')}." if triage.get('imaging_needed') else "")
            ),
            severity_level = "critical" if triage["severity_score"] == 5 else
                             "warning"  if triage["severity_score"] == 4 else "normal",
        ))
        db.commit()

        return jsonify({
            "success":            True,
            "patient_id":         patient.id,
            "patient_name":       patient.name,
            "severity_score":     triage["severity_score"],
            "severity_label":     triage["severity_label"],
            "estimated_wait":     triage["estimated_wait"],
            "doctor_referral":    triage["doctor_referral"],
            "specialist_needed":  triage.get("specialist_needed"),
            "imaging_needed":     triage.get("imaging_needed"),
            "first_aid_steps":    triage["first_aid_steps"],
            "medicines":          triage["medicines"],
            "nurse_instructions": triage["nurse_instructions"],
            "gemini_reasoning":   triage["gemini_reasoning"],
        })
    except Exception as e:
        db.rollback()
        print(f"[TRIAGE ERROR] {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/triage/<int:patient_id>", methods=["GET"])
def get_triage_report(patient_id):
    db = get_session()
    try:
        r = db.query(TriageReport).filter(
            TriageReport.patient_id == patient_id
        ).order_by(TriageReport.timestamp.desc()).first()
        if not r:
            return jsonify({"success": False}), 404
        return jsonify({
            "success":            True,
            "severity_score":     r.severity_score,
            "severity_label":     r.severity_label,
            "estimated_wait":     r.estimated_wait,
            "doctor_referral":    r.doctor_referral,
            "specialist_needed":  r.specialist_needed,
            "imaging_needed":     r.imaging_needed,
            "first_aid_steps":    json.loads(r.first_aid_steps),
            "medicines":          json.loads(r.medicines),
            "nurse_instructions": json.loads(r.nurse_instructions),
            "gemini_reasoning":   r.gemini_reasoning,
            "timestamp":          r.timestamp.strftime("%d %b %Y %H:%M"),
        })
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  ALLOCATION CYCLE
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/run-cycle", methods=["POST"])
def run_allocation_cycle():
    hospital_id = request.json.get("hospital_id") if request.json else None
    db      = get_session()
    results = []
    try:
        q = db.query(Patient).filter(Patient.status == "waiting")
        if hospital_id:
            q = q.filter(Patient.hospital_id == hospital_id)
        patients = q.order_by(Patient.severity.desc()).all()

        print(f"[Cycle] {len(patients)} waiting patient(s)")
        if not patients:
            return jsonify({"message": "No waiting patients.", "actions": []})

        for patient in patients:
            hosp_id = patient.hospital_id or 1
            snap    = hospital_snapshot(db, hosp_id)
            p_dict  = {"id": patient.id, "name": patient.name,
                       "age": patient.age, "condition": patient.condition,
                       "severity": patient.severity}
            decision   = ask_gemini_allocation(p_dict, snap)
            ward_name  = decision.get("ward", "General")
            staff_role = decision.get("staff_role", "Nurse")
            reasoning  = decision.get("reasoning", "")
            sev_level  = decision.get("severity_level", "normal")

            if patient.severity == 5:
                db.add(DecisionLog(
                    hospital_id=hosp_id, action_type="ESCALATE", patient_name=patient.name,
                    reasoning=reasoning,
                    action_taken=f"EMERGENCY escalation for {patient.name}.",
                    severity_level="critical",
                ))

            # Find ward in patient's hospital
            ward = db.query(Ward).filter(
                Ward.hospital_id == hosp_id,
                Ward.name        == ward_name,
                Ward.available_beds > 0,
            ).first()
            if not ward:
                for fn in ["General","Emergency","ICU","Pediatric","Cardiology"]:
                    ward = db.query(Ward).filter(
                        Ward.hospital_id    == hosp_id,
                        Ward.name           == fn,
                        Ward.available_beds >  0,
                    ).first()
                    if ward: break

            if not ward:
                db.add(DecisionLog(
                    hospital_id=hosp_id, action_type="NO_BED",
                    patient_name=patient.name,
                    reasoning=f"All wards full. {reasoning}",
                    action_taken="Patient remains in queue.",
                    severity_level="critical",
                ))
                db.commit()
                results.append({"patient": patient.name,
                                 "action": "NO_BED", "reason": "All wards full"})
                continue

            bed = db.query(Bed).filter(
                Bed.ward_id == ward.id, Bed.status == "available").first()
            if not bed:
                results.append({"patient": patient.name, "action": "NO_BED",
                                 "reason": f"No free bed in {ward.name}"})
                continue

            patient.ward_id = ward.id; patient.bed_id = bed.id
            patient.status  = "admitted"
            bed.status      = "occupied"; bed.patient_id = patient.id
            ward.available_beds -= 1

            staff = db.query(Staff).filter(
                Staff.hospital_id == hosp_id,
                Staff.role        == staff_role,
                Staff.is_available == True,
            ).first()
            if not staff:
                staff = db.query(Staff).filter(
                    Staff.hospital_id == hosp_id,
                    Staff.is_available == True,
                ).first()
            staff_name = "None available"
            if staff:
                staff.is_available = False; staff.ward_id = ward.id
                staff_name = f"{staff.name} ({staff.role})"

            action_taken = (f"Admitted to {ward.name}, bed {bed.room_number}. "
                            f"Assigned: {staff_name}.")
            db.add(DecisionLog(
                hospital_id    = hosp_id,
                action_type    = "ADMIT",
                patient_name   = patient.name,
                reasoning      = reasoning,
                action_taken   = action_taken,
                severity_level = sev_level,
            ))
            db.commit()
            results.append({"patient": patient.name, "action": "ADMITTED",
                             "ward": ward.name, "bed": bed.room_number,
                             "staff": staff_name, "reasoning": reasoning})

        return jsonify({"message": f"Cycle complete. {len(patients)} processed.",
                        "actions": results, "timestamp": datetime.now().isoformat()})
    except Exception as e:
        db.rollback(); import traceback; traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════
#  REFERRALS & DECISIONS
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/referrals", methods=["GET"])
def get_referrals():
    db = get_session()
    try:
        refs = db.query(InterHospitalReferral).order_by(
            InterHospitalReferral.created_at.desc()).limit(50).all()
        return jsonify([{
            "id":           r.id,
            "patient":      r.patient_name,
            "from":         r.from_hospital.name,
            "to":           r.to_hospital.name,
            "specialist":   r.specialist_needed,
            "imaging":      r.imaging_needed,
            "reason":       r.reason,
            "status":       r.status,
            "created":      r.created_at.strftime("%d %b %H:%M"),
        } for r in refs])
    finally:
        db.close()


@app.route("/api/decisions", methods=["GET"])
def get_decisions():
    limit       = int(request.args.get("limit", 50))
    hospital_id = request.args.get("hospital_id", type=int)
    db = get_session()
    try:
        q = db.query(DecisionLog)
        if hospital_id:
            q = q.filter(DecisionLog.hospital_id == hospital_id)
        logs = q.order_by(DecisionLog.timestamp.desc()).limit(limit).all()
        return jsonify([{
            "id":             l.id,
            "time":           l.timestamp.strftime("%d %b %H:%M:%S"),
            "action_type":    l.action_type,
            "patient_name":   l.patient_name,
            "reasoning":      l.reasoning,
            "action_taken":   l.action_taken,
            "severity_level": l.severity_level,
        } for l in logs])
    finally:
        db.close()


@app.route("/api/decisions/clear", methods=["POST"])
def clear_decisions():
    db = get_session()
    try:
        db.query(DecisionLog).delete(); db.commit()
        return jsonify({"success": True})
    finally:
        db.close()


@app.route("/api/debug", methods=["GET"])
def debug():
    db = get_session()
    try:
        gemini_ok, gemini_msg = False, ""
        try:
            r = model_flash.generate_content("Reply OK only.")
            gemini_ok = True; gemini_msg = r.text.strip()
        except Exception as e:
            gemini_msg = str(e)
        return jsonify({
            "gemini_flash_ok": gemini_ok,
            "gemini_response": gemini_msg,
            "waiting":  db.query(Patient).filter(Patient.status=="waiting").count(),
            "admitted": db.query(Patient).filter(Patient.status=="admitted").count(),
            "hospitals":db.query(Hospital).count(),
            "machines": db.query(ImagingMachine).count(),
            "ambulances":db.query(Ambulance).count(),
        })
    finally:
        db.close()


if __name__ == "__main__":
    port = int(os.getenv("API_PORT", 5001))
    print(f"🏥 HARA API  →  http://localhost:{port}")
    print(f"   Debug     →  http://localhost:{port}/api/debug")
    app.run(host="0.0.0.0", port=port, debug=True)
