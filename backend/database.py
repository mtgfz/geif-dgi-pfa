"""
GEIF - Modèles de base de données
====================================
SQLAlchemy ORM. Fonctionne en SQLite par défaut (zéro config, idéal pour
développer/tester), et bascule sur PostgreSQL si la variable d'environnement
DATABASE_URL est définie (déploiement cible : postgresql://user:pass@host/db).
"""
import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./geif.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DocumentRecord(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    predicted_type = Column(String, index=True)
    prediction_confidence = Column(Float)
    extracted_fields = Column(JSON)
    missing_fields = Column(JSON)
    anomalies = Column(JSON)
    is_flagged = Column(Boolean, default=False)
    processed_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
