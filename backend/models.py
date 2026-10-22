"""Database layer for AI Job Interview Platform.

Two related tables:

    job (1) ───< status_history (many)

* ``job``            one row per job application (current state)
* ``status_history`` one row per status change (audit trail / timeline)

The ORM is SQLAlchemy, so the same models run on SQLite (local default)
and PostgreSQL (set the DATABASE_URL environment variable).
"""
import sqlite3
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Index, event
from sqlalchemy.engine import Engine

db = SQLAlchemy()

# Single source of truth for allowed statuses (same list as the UI dropdown).
STATUSES = (
    "Applied",
    "Online Assessment",
    "Technical Interview",
    "HR Interview",
    "Selected",
    "Rejected",
)


def utcnow():
    return datetime.now(timezone.utc)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite ignores FOREIGN KEY constraints unless this pragma is set."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Job(db.Model):
    __tablename__ = "job"

    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(100), nullable=False, index=True)
    role = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="Applied")

    # Added in the upgrade (all optional)
    location = db.Column(db.String(100))
    url = db.Column(db.String(500))
    notes = db.Column(db.Text)
    deadline = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    history = db.relationship(
        "StatusHistory",
        back_populates="job",
        cascade="all, delete-orphan",   # deleting a job deletes its history
        order_by="StatusHistory.id",
    )

    __table_args__ = (
        Index("ix_job_status", "status"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
            name="ck_job_status_valid",
        ),
    )

    def to_dict(self, include_history=False):
        data = {
            "id": self.id,
            "company": self.company,
            "role": self.role,
            "status": self.status,
            "location": self.location,
            "url": self.url,
            "notes": self.notes,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_history:
            data["history"] = [h.to_dict() for h in self.history]
        return data

    def set_status(self, new_status):
        """Change status and record it in status_history (only if it changed)."""
        if new_status == self.status:
            return False
        self.history.append(StatusHistory(from_status=self.status, to_status=new_status))
        self.status = new_status
        return True


class StatusHistory(db.Model):
    __tablename__ = "status_history"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(
        db.Integer,
        db.ForeignKey("job.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status = db.Column(db.String(50))          # NULL for the first entry
    to_status = db.Column(db.String(50), nullable=False)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    job = db.relationship("Job", back_populates="history")

    def to_dict(self):
        return {
            "from_status": self.from_status,
            "to_status": self.to_status,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
        }
