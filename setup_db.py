"""
Run ONCE (or to reset):  python setup_db.py
Creates all tables and seeds two hospitals with full data.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database.db import engine, get_session
from database.models import (Base, Hospital, Ward, Bed, Staff,
                              ImagingMachine, Ambulance, Patient, DecisionLog,
                              TriageReport, PatientVitals, ImagingRequest,
                              AmbulanceDispatch, InterHospitalReferral)
from datetime import datetime, timedelta
import random

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("✅  Tables created.")

db = get_session()

# ── HOSPITALS ─────────────────────────────────────────────────────────────────
h1 = Hospital(
    name    = "National Hospital of Sri Lanka",
    address = "Regent St, Colombo 00700",
    lat     = 6.9271, lng = 79.8612,
    phone   = "+94 11 269 1111",
    is_main = True,
)
h2 = Hospital(
    name    = "Colombo South Teaching Hospital",
    address = "Galle Rd, Kalubowila, Dehiwala",
    lat     = 6.8561, lng = 79.8741,
    phone   = "+94 11 271 5111",
    is_main = False,
)
db.add_all([h1, h2])
db.flush()
print(f"✅  Hospitals: {h1.name} (ID {h1.id}), {h2.name} (ID {h2.id})")

# ── WARDS ─────────────────────────────────────────────────────────────────────
ward_configs = [
    ("ICU",       10, 4),
    ("Emergency", 20, 8),
    ("General",   40, 18),
    ("Pediatric", 15, 7),
    ("Cardiology", 12, 5),
]
prefix_map = {"ICU": "I", "Emergency": "E", "General": "G",
              "Pediatric": "P", "Cardiology": "C"}

wards = {}   # (hospital_id, ward_name) -> Ward object
for hosp in [h1, h2]:
    for wname, total, avail in ward_configs:
        # H2 has slightly fewer beds
        t = total if hosp.is_main else max(5, total - 5)
        a = avail if hosp.is_main else max(2, avail - 3)
        w = Ward(hospital_id=hosp.id, name=wname, total_beds=t, available_beds=a)
        db.add(w)
        db.flush()
        wards[(hosp.id, wname)] = w

        # Create beds
        pfx = prefix_map.get(wname, wname[0])
        occupied_count = t - a
        for i in range(1, t + 1):
            status = "occupied" if i <= occupied_count else "available"
            db.add(Bed(ward_id=w.id,
                       room_number=f"H{hosp.id}-{pfx}-{i:02d}",
                       status=status))

print("✅  Wards and beds created.")

# ── STAFF ─────────────────────────────────────────────────────────────────────
staff_h1 = [
    # Doctors
    ("Dr. Samantha Perera",    "Doctor",    "General Physician",   "morning", "General"),
    ("Dr. Kamal Fernando",     "Doctor",    "General Physician",   "evening", "General"),
    ("Dr. Nisha Rajapaksa",    "Doctor",    "Paediatrician",       "morning", "Pediatric"),
    ("Dr. Arjun Mendis",       "Doctor",    "General Physician",   "night",   "General"),
    # ER Doctors
    ("Dr. Roshan Silva",       "ER Doctor", "Emergency Medicine",  "morning", "Emergency"),
    ("Dr. Priya Wijesinghe",   "ER Doctor", "Emergency Medicine",  "evening", "Emergency"),
    ("Dr. Tharaka Jayasena",   "ER Doctor", "Emergency Medicine",  "night",   "Emergency"),
    # Nurses
    ("Nurse Dilini Kumari",    "Nurse",     None,                  "morning", "ICU"),
    ("Nurse Sachini Abeywickrama","Nurse",  None,                  "morning", "General"),
    ("Nurse Harsha Bandara",   "Nurse",     None,                  "evening", "Emergency"),
    ("Nurse Ruwani Tissera",   "Nurse",     None,                  "night",   "Pediatric"),
    ("Nurse Malika Senarath",  "Nurse",     None,                  "morning", "General"),
    # Surgeons
    ("Dr. Chaminda Herath",    "Surgeon",   "Cardiothoracic",      "morning", "ICU"),
    ("Dr. Gayani Peiris",      "Surgeon",   "General Surgery",     "evening", "ICU"),
    # Specialists
    ("Dr. Lahiru Abeysekara",  "Specialist","Cardiologist",        "morning", "Cardiology"),
    ("Dr. Madhavi Sooriyabandara","Specialist","Neurologist",      "morning", "General"),
    ("Dr. Ravi Gunasekara",    "Specialist","Radiologist",         "morning", "General"),
    # On-Call
    ("Dr. Buddhika Rathnayake","On-Call",   None,                  "night",   None),
    ("Dr. Anoma Dissanayake",  "On-Call",   None,                  "night",   None),
    ("Nurse Kasun Pathirana",  "On-Call",   None,                  "night",   None),
]
staff_h2 = [
    ("Dr. Thilina Weerasinghe","Doctor",    "General Physician",   "morning", "General"),
    ("Dr. Sanduni Jayawardena","Doctor",    "General Physician",   "evening", "General"),
    ("Dr. Nuwan Bandara",      "ER Doctor", "Emergency Medicine",  "morning", "Emergency"),
    ("Dr. Amali Perera",       "ER Doctor", "Emergency Medicine",  "night",   "Emergency"),
    ("Nurse Chathura Silva",   "Nurse",     None,                  "morning", "General"),
    ("Nurse Nimali Fernando",  "Nurse",     None,                  "evening", "ICU"),
    ("Dr. Prasad Gunasekara",  "Surgeon",   "General Surgery",     "morning", "ICU"),
    ("Dr. Sachini De Silva",   "Specialist","Cardiologist",        "morning", "Cardiology"),
    ("Dr. Kasun Rajapaksa",    "Specialist","Orthopaedic Surgeon", "morning", "General"),
    ("Dr. Isuru Madushanka",   "On-Call",   None,                  "night",   None),
]

for hosp, staff_list in [(h1, staff_h1), (h2, staff_h2)]:
    for name, role, spec, shift, ward_name in staff_list:
        ward_obj = wards.get((hosp.id, ward_name)) if ward_name else None
        db.add(Staff(
            hospital_id  = hosp.id,
            name         = name,
            role         = role,
            specialty    = spec,
            shift        = shift,
            ward_id      = ward_obj.id if ward_obj else None,
            is_available = True,
        ))

print("✅  Staff seeded.")

# ── IMAGING MACHINES ─────────────────────────────────────────────────────────
imaging_h1 = [
    ("X-Ray",      "XR-1",   True),
    ("X-Ray",      "XR-2",   True),
    ("MRI",        "MRI-1",  True),
    ("MRI",        "MRI-2",  False),   # under maintenance
    ("CT Scanner", "CT-A",   True),
    ("CT Scanner", "CT-B",   True),
    ("Ultrasound", "US-1",   True),
    ("Ultrasound", "US-2",   True),
    ("ECG",        "ECG-1",  True),
    ("ECG",        "ECG-2",  True),
]
imaging_h2 = [
    ("X-Ray",      "XR-A",   True),
    ("MRI",        "MRI-A",  False),   # under maintenance — forces referrals to H1
    ("CT Scanner", "CT-1",   True),
    ("Ultrasound", "US-A",   True),
    ("ECG",        "ECG-A",  True),
]

for hosp, machines in [(h1, imaging_h1), (h2, imaging_h2)]:
    for mtype, mname, avail in machines:
        db.add(ImagingMachine(
            hospital_id  = hosp.id,
            machine_type = mtype,
            name         = mname,
            is_available = avail,
        ))

print("✅  Imaging machines seeded.")

# ── AMBULANCES ────────────────────────────────────────────────────────────────
ambs_h1 = [
    ("AMB-01", "Kasun Perera"),
    ("AMB-02", "Chamara Silva"),
    ("AMB-03", "Niroshan Fernando"),
]
ambs_h2 = [
    ("AMB-A1", "Pradeep Bandara"),
    ("AMB-A2", "Ruwan Jayasena"),
]
for hosp, ambs in [(h1, ambs_h1), (h2, ambs_h2)]:
    for call_sign, driver in ambs:
        db.add(Ambulance(hospital_id=hosp.id, call_sign=call_sign,
                         driver_name=driver, is_available=True))

print("✅  Ambulances seeded.")

# ── PRE-EXISTING PATIENTS (Hospital 1) ───────────────────────────────────────
admitted_data = [
    ("Pradeep Gunasekara",    45, "Cardiac arrest – post-resuscitation",      5, "ICU"),
    ("Malini Wickramasinghe", 62, "Type 2 diabetes – hyperglycaemic crisis",  3, "General"),
    ("Randika Jayawardena",    8, "Acute asthma attack",                      4, "Pediatric"),
    ("Sujeewa Samarasinghe",  38, "Severe appendicitis – pre-op",             4, "Emergency"),
    ("Kumari Dissanayake",    55, "Fractured femur – post-op recovery",       2, "General"),
]
for name, age, cond, sev, ward_name in admitted_data:
    ward = wards[(h1.id, ward_name)]
    bed  = db.query(Bed).filter(
        Bed.ward_id == ward.id,
        Bed.status  == "occupied",
        Bed.patient_id == None
    ).first()
    p = Patient(hospital_id=h1.id, name=name, age=age, condition=cond,
                severity=sev, status="admitted", ward_id=ward.id,
                bed_id=bed.id if bed else None,
                admitted_at=datetime.now() - timedelta(hours=random.randint(1, 48)))
    db.add(p)
    db.flush()
    if bed:
        bed.patient_id = p.id

# Waiting patients (Hospital 1)
# Waiting patients (Hospital 1)
waiting_data = [
    ("Thilak Senanayake",  72, "Chest pain – possible MI",          5),
    ("Amara Bandara",       6, "High fever – suspected meningitis",  4),
    ("Sanjeewa Rathnayake",33, "Laceration – deep wound, bleeding",  3),
    # ── Newly Added Patients ──
    ("Alex Mercer",        26, "Twisted right ankle, painful weight-bearing", 2),
    ("Malith Jayawardena", 34, "High fever for 3 days, myalgia, retro-orbital pain", 3),
    ("Priyantha Fernando", 58, "Severe sudden abdominal pain, rigid abdomen", 4),
    ("Dinesh Gunawardena", 41, "Migraine with aura, photophobia", 2),
    ("Nethmi Silva",       22, "Mild sore throat and runny nose", 1),
]
for name, age, cond, sev in waiting_data:
    db.add(Patient(hospital_id=h1.id, name=name, age=age,
                   condition=cond, severity=sev, status="waiting"))

db.commit()
db.close()
print("✅  Patients seeded.")
print()
print("════════════════════════════════════════")
print("  HospitalDB is ready!")
print("  Hospital 1 (Main):    National Hospital, Colombo")
print("  Hospital 2 (Partner): Colombo South Teaching Hospital")
print()
print("  Run:  python api/api.py          (Terminal 1)")
print("  Run:  streamlit run app.py       (Terminal 2)")
print("  Run:  streamlit run ops.py --server.port 8502  (Terminal 3)")
print("════════════════════════════════════════")