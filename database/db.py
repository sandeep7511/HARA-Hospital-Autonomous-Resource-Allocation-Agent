import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

SERVER = os.getenv("SQL_SERVER",   "localhost")
DB     = os.getenv("SQL_DATABASE", "HospitalDB")
DRIVER = os.getenv("SQL_DRIVER",   "ODBC Driver 17 for SQL Server")

CONNECTION_STRING = (
    f"mssql+pyodbc://@{SERVER}/{DB}"
    f"?driver={DRIVER.replace(' ', '+')}"
    f"&Trusted_Connection=yes"
)

engine       = create_engine(CONNECTION_STRING, echo=False, fast_executemany=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_session():
    return SessionLocal()
