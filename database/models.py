from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Hospital(Base):
    __tablename__ = "hospitals"
    id       = Column(Integer, primary_key=True)
    name     = Column(String(150), nullable=False)
    address  = Column(String(250), nullable=False)
    lat      = Column(Float, nullable=False)
    lng      = Column(Float, nullable=False)
    phone    = Column(String(30), nullable=True)
    is_main  = Column(Boolean, default=False)

    wards      = relationship("Ward",           back_populates="hospital")
    staff      = relationship("Staff",          back_populates="hospital")
    machines   = relationship("ImagingMachine", back_populates="hospital")
    ambulances = relationship("Ambulance",      back_populates="hospital")


class Ward(Base):
    __tablename__ = "wards"
    id             = Column(Integer, primary_key=True)
    hospital_id    = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    name           = Column(String(50),  nullable=False)
    total_beds     = Column(Integer, default=0)
    available_beds = Column(Integer, default=0)

    hospital = relationship("Hospital", back_populates="wards")
    beds     = relationship("Bed",      back_populates="ward")
    patients = relationship("Patient",  back_populates="ward")
    staff    = relationship("Staff",    back_populates="ward")


class Bed(Base):
    __tablename__ = "beds"
    id          = Column(Integer, primary_key=True)
    ward_id     = Column(Integer, ForeignKey("wards.id"),     nullable=False)
    room_number = Column(String(20), nullable=False)
    status      = Column(String(20), default="available")
    patient_id  = Column(Integer, ForeignKey("patients.id"),  nullable=True)

    ward    = relationship("Ward",    back_populates="beds")
    patient = relationship("Patient", back_populates="bed", foreign_keys=[patient_id])


class Patient(Base):
    __tablename__ = "patients"
    id          = Column(Integer, primary_key=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True)
    name        = Column(String(100), nullable=False)
    age         = Column(Integer,     nullable=False)
    condition   = Column(String(500), nullable=False)
    severity    = Column(Integer,     nullable=False)
    status      = Column(String(20),  default="waiting")
    ward_id     = Column(Integer, ForeignKey("wards.id"), nullable=True)
    bed_id      = Column(Integer, ForeignKey("beds.id"),  nullable=True)
    admitted_at = Column(DateTime, default=datetime.now)
    notes       = Column(Text, nullable=True)

    ward   = relationship("Ward",    back_populates="patients")
    bed    = relationship("Bed",     back_populates="patient", foreign_keys=[Bed.patient_id])
    vitals = relationship("PatientVitals", back_populates="patient",
                          order_by="PatientVitals.recorded_at.desc()")


class Staff(Base):
    __tablename__ = "staff"
    id           = Column(Integer, primary_key=True)
    hospital_id  = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    name         = Column(String(100), nullable=False)
    role         = Column(String(50),  nullable=False)
    specialty    = Column(String(100), nullable=True)
    shift        = Column(String(20),  default="morning")
    ward_id      = Column(Integer, ForeignKey("wards.id"), nullable=True)
    is_available = Column(Boolean, default=True)

    hospital = relationship("Hospital", back_populates="staff")
    ward     = relationship("Ward",     back_populates="staff")


class ImagingMachine(Base):
    __tablename__ = "imaging_machines"
    id           = Column(Integer, primary_key=True)
    hospital_id  = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    machine_type = Column(String(50),  nullable=False)  # X-Ray|MRI|CT Scanner|Ultrasound|ECG
    name         = Column(String(100), nullable=False)
    is_available = Column(Boolean, default=True)
    notes        = Column(String(200), nullable=True)

    hospital = relationship("Hospital", back_populates="machines")


class ImagingRequest(Base):
    __tablename__ = "imaging_requests"
    id           = Column(Integer, primary_key=True)
    patient_id   = Column(Integer, ForeignKey("patients.id"),        nullable=False)
    hospital_id  = Column(Integer, ForeignKey("hospitals.id"),       nullable=False)
    machine_type = Column(String(50),  nullable=False)
    machine_id   = Column(Integer, ForeignKey("imaging_machines.id"), nullable=True)
    reason       = Column(Text, nullable=True)
    status       = Column(String(20), default="pending")
    requested_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)

    patient = relationship("Patient")
    machine = relationship("ImagingMachine")


class Ambulance(Base):
    __tablename__ = "ambulances"
    id           = Column(Integer, primary_key=True)
    hospital_id  = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    call_sign    = Column(String(20),  nullable=False)
    driver_name  = Column(String(100), nullable=False)
    is_available = Column(Boolean, default=True)

    hospital   = relationship("Hospital",         back_populates="ambulances")
    dispatches = relationship("AmbulanceDispatch", back_populates="ambulance")


class AmbulanceDispatch(Base):
    __tablename__ = "ambulance_dispatches"
    id                = Column(Integer, primary_key=True)
    ambulance_id      = Column(Integer, ForeignKey("ambulances.id"),  nullable=False)
    patient_name      = Column(String(100), nullable=False)
    patient_condition = Column(Text,        nullable=True)
    pickup_lat        = Column(Float, nullable=False)
    pickup_lng        = Column(Float, nullable=False)
    pickup_address    = Column(String(250), nullable=True)
    destination_id    = Column(Integer, ForeignKey("hospitals.id"),   nullable=False)
    distance_km       = Column(Float,   nullable=False)
    eta_minutes       = Column(Integer, nullable=False)
    specialist_needed = Column(String(100), nullable=True)
    imaging_needed    = Column(String(50),  nullable=True)
    routing_reason    = Column(Text, nullable=True)
    status            = Column(String(20), default="dispatched")
    dispatched_at     = Column(DateTime, default=datetime.now)
    completed_at      = Column(DateTime, nullable=True)

    ambulance   = relationship("Ambulance", back_populates="dispatches")
    destination = relationship("Hospital",  foreign_keys=[destination_id])


class PatientVitals(Base):
    __tablename__ = "patient_vitals"
    id           = Column(Integer, primary_key=True)
    patient_id   = Column(Integer, ForeignKey("patients.id"), nullable=False)
    temperature  = Column(Float,   nullable=True)   # Celsius
    bp_systolic  = Column(Integer, nullable=True)   # mmHg
    bp_diastolic = Column(Integer, nullable=True)   # mmHg
    heart_rate   = Column(Integer, nullable=True)   # bpm
    height_cm    = Column(Float,   nullable=True)
    weight_kg    = Column(Float,   nullable=True)
    bmi          = Column(Float,   nullable=True)   # auto-calculated
    spo2         = Column(Integer, nullable=True)   # % SpO2
    recorded_at  = Column(DateTime, default=datetime.now)
    recorded_by  = Column(String(100), nullable=True)

    patient = relationship("Patient", back_populates="vitals")


class InterHospitalReferral(Base):
    __tablename__ = "inter_hospital_referrals"
    id                    = Column(Integer, primary_key=True)
    patient_id            = Column(Integer, ForeignKey("patients.id"),       nullable=True)
    patient_name          = Column(String(100), nullable=False)
    from_hospital_id      = Column(Integer, ForeignKey("hospitals.id"),      nullable=False)
    to_hospital_id        = Column(Integer, ForeignKey("hospitals.id"),      nullable=False)
    specialist_needed     = Column(String(100), nullable=True)
    imaging_needed        = Column(String(50),  nullable=True)
    reason                = Column(Text, nullable=False)
    ambulance_dispatch_id = Column(Integer, ForeignKey("ambulance_dispatches.id"), nullable=True)
    status                = Column(String(20), default="pending")
    created_at            = Column(DateTime, default=datetime.now)

    from_hospital = relationship("Hospital", foreign_keys=[from_hospital_id])
    to_hospital   = relationship("Hospital", foreign_keys=[to_hospital_id])


class DecisionLog(Base):
    __tablename__ = "decisions_log"
    id             = Column(Integer, primary_key=True)
    hospital_id    = Column(Integer, ForeignKey("hospitals.id"), nullable=True)
    timestamp      = Column(DateTime, default=datetime.now)
    action_type    = Column(String(50),  nullable=False)
    patient_name   = Column(String(100), nullable=True)
    reasoning      = Column(Text, nullable=False)
    action_taken   = Column(Text, nullable=False)
    severity_level = Column(String(20),  default="normal")


class TriageReport(Base):
    __tablename__ = "triage_reports"
    id                 = Column(Integer, primary_key=True)
    patient_id         = Column(Integer, ForeignKey("patients.id"), nullable=False)
    timestamp          = Column(DateTime, default=datetime.now)
    severity_score     = Column(Integer,     nullable=False)
    severity_label     = Column(String(30),  nullable=False)
    first_aid_steps    = Column(Text, nullable=False)
    medicines          = Column(Text, nullable=False)
    doctor_referral    = Column(String(100), nullable=False)
    specialist_needed  = Column(String(100), nullable=True)
    imaging_needed     = Column(String(50),  nullable=True)
    nurse_instructions = Column(Text, nullable=False)
    estimated_wait     = Column(String(50),  nullable=False)
    gemini_reasoning   = Column(Text, nullable=False)

    patient = relationship("Patient", backref="triage_report")
