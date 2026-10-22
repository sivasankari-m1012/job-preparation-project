import os
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from models import STATUSES, Job, StatusHistory, db

# <project root>/instance/jobs.db  - same place no matter which folder you start Flask from.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_FILE = PROJECT_ROOT / "instance" / "jobs.db"

SORT_FIELDS = {
    "company": Job.company,
    "role": Job.role,
    "status": Job.status,
    "deadline": Job.deadline,
    "created_at": Job.created_at,
}


def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        DEFAULT_DB_FILE.parent.mkdir(exist_ok=True)
        return f"sqlite:///{DEFAULT_DB_FILE.as_posix()}"
    # Some hosts still hand out the old "postgres://" scheme.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if test_config:
        app.config.update(test_config)
    if "SQLALCHEMY_DATABASE_URI" not in app.config:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url()

    db.init_app(app)
    with app.app_context():
        db.create_all()

    register_routes(app)
    register_error_handlers(app)
    return app


# ---------------------------------------------------------------- validation

def _clean_text(data, field, max_len, required, errors):
    """Return a trimmed string (or None) and record any validation error."""
    if field not in data:
        if required:
            errors[field] = "is required"
        return None
    value = data[field]
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            errors[field] = "cannot be blank"
        return None
    if not isinstance(value, str):
        errors[field] = "must be text"
        return None
    value = value.strip()
    if len(value) > max_len:
        errors[field] = f"must be at most {max_len} characters"
        return None
    return value


def _clean_date(data, field, errors):
    value = data.get(field)
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors[field] = "must be a date in YYYY-MM-DD format"
        return None


def validate_job(data, partial=False):
    """Validate a job payload. Returns (clean_fields, errors).

    partial=True (PATCH): only fields that were sent are validated.
    partial=False (POST/PUT): company, role and status are required.
    """
    errors = {}
    clean = {}

    for field, max_len in (("company", 100), ("role", 100)):
        if not partial or field in data:
            value = _clean_text(data, field, max_len, True, errors)
            if field not in errors:
                clean[field] = value

    if not partial or "status" in data:
        status = data.get("status")
        if status is None:
            errors["status"] = "is required"
        elif status not in STATUSES:
            errors["status"] = "must be one of: " + ", ".join(STATUSES)
        else:
            clean["status"] = status

    for field, max_len in (("location", 100), ("url", 500), ("notes", 2000)):
        if not partial or field in data:
            value = _clean_text(data, field, max_len, False, errors)
            if field not in errors:
                clean[field] = value

    if clean.get("url") and not clean["url"].lower().startswith(("http://", "https://")):
        errors["url"] = "must start with http:// or https://"

    if not partial or "deadline" in data:
        deadline = _clean_date(data, "deadline", errors)
        if "deadline" not in errors:
            clean["deadline"] = deadline

    return clean, errors


def read_json_object():
    """Return the request body as a dict, or None if it is missing/invalid."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def bad_request(errors=None, message="Validation failed"):
    body = {"error": message}
    if errors:
        body["details"] = errors
    return jsonify(body), 400


def commit_or_500():
    """Commit the session; roll back and return a JSON error if it fails."""
    try:
        db.session.commit()
        return None
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database error, nothing was saved"}), 500


# -------------------------------------------------------------------- routes

def register_routes(app):
    @app.route("/")
    def home():
        return render_template("index.html")

    @app.get("/api/jobs")
    def list_jobs():
        query = db.select(Job)

        status = request.args.get("status", "").strip()
        if status:
            if status not in STATUSES:
                return bad_request({"status": "unknown status filter"})
            query = query.where(Job.status == status)

        search = request.args.get("q", "").strip()
        if search:
            like = f"%{search}%"
            query = query.where(or_(Job.company.ilike(like), Job.role.ilike(like)))

        sort = request.args.get("sort", "created_at")
        if sort not in SORT_FIELDS:
            return bad_request({"sort": "must be one of: " + ", ".join(SORT_FIELDS)})
        column = SORT_FIELDS[sort]
        descending = request.args.get("order", "desc").lower() != "asc"
        query = query.order_by(column.desc() if descending else column.asc(), Job.id.desc())

        jobs = db.session.scalars(query).all()
        return jsonify([job.to_dict() for job in jobs])

    @app.post("/api/jobs")
    def create_job():
        data = read_json_object()
        if data is None:
            return bad_request(message="A JSON object body is required")

        clean, errors = validate_job(data)
        if errors:
            return bad_request(errors)

        job = Job(**clean)
        job.history.append(StatusHistory(from_status=None, to_status=job.status))
        db.session.add(job)
        failure = commit_or_500()
        if failure:
            return failure
        return jsonify({"message": "Job application created", "job": job.to_dict()}), 201

    @app.get("/api/jobs/<int:job_id>")
    def get_job(job_id):
        job = db.get_or_404(Job, job_id, description="Job not found")
        return jsonify(job.to_dict(include_history=True))

    def update_job(job_id, partial):
        job = db.get_or_404(Job, job_id, description="Job not found")
        data = read_json_object()
        if data is None:
            return bad_request(message="A JSON object body is required")

        clean, errors = validate_job(data, partial=partial)
        if errors:
            return bad_request(errors)

        new_status = clean.pop("status", None)
        for field, value in clean.items():
            setattr(job, field, value)
        if new_status is not None:
            job.set_status(new_status)

        failure = commit_or_500()
        if failure:
            return failure
        return jsonify({"message": "Job updated successfully", "job": job.to_dict()})

    @app.patch("/api/jobs/<int:job_id>")
    def patch_job(job_id):
        return update_job(job_id, partial=True)

    @app.put("/api/jobs/<int:job_id>")
    def replace_job(job_id):
        return update_job(job_id, partial=False)

    @app.delete("/api/jobs/<int:job_id>")
    def delete_job(job_id):
        job = db.get_or_404(Job, job_id, description="Job not found")
        db.session.delete(job)
        failure = commit_or_500()
        if failure:
            return failure
        return jsonify({"message": "Job deleted successfully"})

    @app.get("/api/stats")
    def stats():
        rows = db.session.execute(
            db.select(Job.status, func.count(Job.id)).group_by(Job.status)
        ).all()
        by_status = {status: 0 for status in STATUSES}
        by_status.update({status: count for status, count in rows})
        return jsonify({"total": sum(by_status.values()), "by_status": by_status})


# ------------------------------------------------------------ error handling

def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": error.description}), error.code
        return error

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled error")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return "Internal server error", 500


if __name__ == "__main__":
    # Debug is OFF unless you ask for it:  set FLASK_DEBUG=1
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
