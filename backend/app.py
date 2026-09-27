from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    jobs = Job.query.all()

    result = []

    for job in jobs:
        result.append({
            "id": job.id,
            "company": job.company,
            "role": job.role,
            "status": job.status
        })

    return jsonify(result)

@app.route("/api/jobs", methods=["POST"])
def create_job():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    if "company" not in data or "role" not in data or "status" not in data:
        return jsonify({
        "error": "company, role and status are required"
    }), 400

    job = Job(
        company=data["company"],
        role=data["role"],
        status=data["status"]
    )

    db.session.add(job)
    db.session.commit()

    return jsonify({
        "message": "Job application created",
        "job": {
            "id": job.id,
            "company": job.company,
            "role": job.role,
            "status": job.status
        }
    }), 201
@app.route("/api/jobs/<int:id>", methods=["PUT"])
def update_job(id):
    job = Job.query.get(id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    data = request.get_json()

    if "status" in data:
        job.status = data["status"]

    db.session.commit()

    return jsonify({
        "message": "Job status updated successfully",
        "job": {
            "id": job.id,
            "company": job.company,
            "role": job.role,
            "status": job.status
        }
    })
@app.route("/api/jobs/<int:id>", methods=["DELETE"])
def delete_job(id):
    job = Job.query.get(id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    db.session.delete(job)
    db.session.commit()

    return jsonify({
        "message": "Job deleted successfully"
    })

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)