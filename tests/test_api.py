import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import create_app  # noqa: E402
from models import StatusHistory, db  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
    })


@pytest.fixture()
def client(app):
    return app.test_client()


def make_job(client, **overrides):
    payload = {"company": "Zoho", "role": "Developer", "status": "Applied"}
    payload.update(overrides)
    return client.post("/api/jobs", json=payload)


# ------------------------------------------------------------------- create

def test_create_job_returns_201_and_history_row(client, app):
    response = make_job(client, location="Chennai", url="https://zoho.com/careers")
    assert response.status_code == 201
    job = response.get_json()["job"]
    assert job["id"] == 1
    assert job["location"] == "Chennai"

    detail = client.get(f"/api/jobs/{job['id']}").get_json()
    assert [(h["from_status"], h["to_status"]) for h in detail["history"]] == [(None, "Applied")]


def test_create_trims_whitespace(client):
    job = make_job(client, company="  TCS  ", role="  SE ").get_json()["job"]
    assert (job["company"], job["role"]) == ("TCS", "SE")


@pytest.mark.parametrize("payload, bad_field", [
    ({"company": "", "role": "Dev", "status": "Applied"}, "company"),
    ({"company": "   ", "role": "Dev", "status": "Applied"}, "company"),
    ({"role": "Dev", "status": "Applied"}, "company"),
    ({"company": "X", "role": "Dev", "status": "applied"}, "status"),
    ({"company": "X", "role": "Dev", "status": "Applied", "url": "ftp://x"}, "url"),
    ({"company": "X", "role": "Dev", "status": "Applied", "deadline": "12/10/2026"}, "deadline"),
    ({"company": "X" * 101, "role": "Dev", "status": "Applied"}, "company"),
])
def test_create_rejects_invalid_input(client, payload, bad_field):
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 400
    assert bad_field in response.get_json()["details"]


def test_create_rejects_non_json_and_non_object_body(client):
    assert client.post("/api/jobs", data="hello").status_code == 400
    assert client.post("/api/jobs", json=[1, 2]).status_code == 400


# --------------------------------------------------------------------- read

def test_list_filter_search_and_sort(client):
    make_job(client, company="Zoho", role="Backend", status="Applied")
    make_job(client, company="TCS", role="Support", status="Rejected")
    make_job(client, company="Infosys", role="Backend", status="Applied")

    assert len(client.get("/api/jobs").get_json()) == 3
    assert len(client.get("/api/jobs?status=Applied").get_json()) == 2
    assert [j["company"] for j in client.get("/api/jobs?q=support").get_json()] == ["TCS"]

    by_company = client.get("/api/jobs?sort=company&order=asc").get_json()
    assert [j["company"] for j in by_company] == ["Infosys", "TCS", "Zoho"]


def test_list_rejects_unknown_filter_and_sort(client):
    assert client.get("/api/jobs?status=Nope").status_code == 400
    assert client.get("/api/jobs?sort=password").status_code == 400


def test_missing_job_returns_json_404(client):
    response = client.get("/api/jobs/999")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Job not found"}


# ------------------------------------------------------------------- update

def test_patch_status_records_history_only_when_changed(client):
    make_job(client)
    client.patch("/api/jobs/1", json={"status": "Technical Interview"})
    client.patch("/api/jobs/1", json={"status": "Technical Interview"})  # no change

    history = client.get("/api/jobs/1").get_json()["history"]
    assert [(h["from_status"], h["to_status"]) for h in history] == [
        (None, "Applied"),
        ("Applied", "Technical Interview"),
    ]


def test_patch_is_partial_and_validates(client):
    make_job(client, notes="keep me")
    response = client.patch("/api/jobs/1", json={"company": "Cargill"})
    assert response.status_code == 200
    job = response.get_json()["job"]
    assert job["company"] == "Cargill" and job["notes"] == "keep me"

    assert client.patch("/api/jobs/1", json={"company": " "}).status_code == 400
    assert client.patch("/api/jobs/1", json={"status": "Hired"}).status_code == 400
    assert client.patch("/api/jobs/999", json={"status": "Applied"}).status_code == 404


def test_put_requires_the_full_resource(client):
    make_job(client)
    assert client.put("/api/jobs/1", json={"status": "Rejected"}).status_code == 400
    ok = client.put("/api/jobs/1", json={"company": "A", "role": "B", "status": "Rejected"})
    assert ok.status_code == 200
    assert ok.get_json()["job"]["status"] == "Rejected"


# ------------------------------------------------------------------- delete

def test_delete_cascades_to_history(client, app):
    make_job(client)
    client.patch("/api/jobs/1", json={"status": "HR Interview"})
    assert client.delete("/api/jobs/1").status_code == 200
    assert client.delete("/api/jobs/1").status_code == 404

    with app.app_context():
        assert db.session.query(StatusHistory).count() == 0


# -------------------------------------------------------------------- stats

def test_stats_counts_every_status(client):
    make_job(client, status="Applied")
    make_job(client, status="Applied")
    make_job(client, status="Selected")

    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 3
    assert stats["by_status"]["Applied"] == 2
    assert stats["by_status"]["Selected"] == 1
    assert stats["by_status"]["Rejected"] == 0


# -------------------------------------------------------------- persistence

def test_data_survives_an_app_restart(tmp_path):
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'p.db'}"}

    first = create_app(config)
    assert make_job(first.test_client(), company="Persisted").status_code == 201

    second = create_app(config)   # fresh app, same database file
    jobs = second.test_client().get("/api/jobs").get_json()
    assert [j["company"] for j in jobs] == ["Persisted"]
