"""Workout commands, preserved evidence, analytics, and nested ownership boundaries."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

PROFILE = {
    "full_name": "Workout Athlete", "nickname": "Athlete", "age": 28,
    "biological_sex": "male", "height_cm": 180, "starting_weight_kg": 80,
    "current_weight_kg": 80, "display_unit": "kg", "activity_multiplier": 1.55,
    "phase": "baseline_assessment", "analysis_weeks": 2,
}


def day(days_ago=0):
    return (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()


def session_input(**changes):
    return {"title": "Pull training", "performed_on": day(), "bodyweight_kg": 80, **changes}


def set_input(**changes):
    return {"ordinal": 1, "set_type": "working", "external_load_kg": 10,
            "repetitions": 8, "duration_seconds": None, "rpe": 8, "rir": None,
            "rest_seconds": 120, **changes}


@pytest.fixture
def workouts(identity):
    from app import profile, reference_routes, workout_routes
    from app.seed import seed_reference_data

    identity.app.include_router(profile.router)
    identity.app.include_router(reference_routes.exercise_router)
    identity.app.include_router(workout_routes.router)
    with identity.sessions.begin() as db:
        seed_reference_data(db)
    with TestClient(identity.app, headers={"Origin": "http://testserver"}) as client:
        owners = []
        for email in ("workout.first@example.com", "workout.second@example.com"):
            result = client.post("/api/v1/auth/register", json={"email": email, "password": identity.password})
            assert result.status_code == 201
            headers = {"Authorization": "Bearer " + result.json()["access_token"]}
            assert client.put("/api/v1/profile", headers=headers, json=PROFILE).status_code == 200
            owners.append(headers)
        exercises = {item["name"]: item["id"] for item in client.get("/api/v1/exercises?limit=100", headers=owners[0]).json()["items"]}
        yield client, owners, exercises


def create_workout(client, owner, **changes):
    result = client.post("/api/v1/workouts", headers=owner, json=session_input(**changes))
    assert result.status_code == 201, result.text
    return result.json()


def add_block(client, owner, session, exercise_id, ordinal=1):
    result = client.post(f"/api/v1/workouts/{session['id']}/exercises", headers=owner, json={
        "exercise_id": exercise_id, "ordinal": ordinal, "target_min_reps": 8, "target_max_reps": 10,
    })
    assert result.status_code == 201, result.text
    return next(block for block in result.json()["exercises"] if block["ordinal"] == ordinal)


def block_path(session, block):
    return f"/api/v1/workouts/{session['id']}/exercises/{block['id']}"


def add_set(client, owner, session, block, **changes):
    result = client.post(block_path(session, block) + "/sets", headers=owner, json=set_input(**changes))
    assert result.status_code == 201, result.text
    return result.json()


def test_authoritative_pullup_snapshot_survives_reference_and_profile_changes(workouts, identity, monkeypatch):
    from app.models import Exercise, WorkoutSourceRecord
    from app import profile

    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    saved = add_set(client, owner, session, block)
    row = saved["exercises"][0]["sets"][0]
    assert row["bodyweight_kg"] == 80
    assert row["metrics"]["effective_load_kg"] == 86
    assert row["metrics"]["volume_kg"] == 688
    assert row["metrics"]["estimated_1rm_kg"] == pytest.approx(108.933333333)
    assert row["metrics"]["one_rm_formula"] == "epley"
    assert saved["total_volume_kg"] == 688
    with identity.sessions.begin() as db:
        original_source = db.get(WorkoutSourceRecord, row["source_record_id"]).payload
        exercise = db.get(Exercise, exercises["Pull-up"])
        exercise.name = "Changed reference"
        exercise.biomechanical_multiplier = .5
        exercise.muscles[0].contribution = .1
    next_measurement = datetime.now(timezone.utc) + timedelta(days=1)
    monkeypatch.setattr(profile, "utc_now", lambda: next_measurement)
    response = client.post("/api/v1/profile/check-ins", headers=owner, json={
        "measured_on": next_measurement.date().isoformat(), "weight_kg": 90,
    })
    assert response.status_code == 201
    assert client.get("/api/v1/profile", headers=owner).json()["profile"]["current_weight_kg"] == 90
    reloaded = client.get(f"/api/v1/workouts/{session['id']}", headers=owner).json()
    assert reloaded == saved
    history = client.get(f"/api/v1/workouts/{session['id']}/history", headers=owner).json()
    assert history["items"][0]["payload"] == original_source
    assert reloaded["exercises"][0]["exercise_snapshot"]["name"] == "Pull-up"
    assert client.put(f"/api/v1/workouts/{session['id']}", headers=owner, json=session_input(bodyweight_kg=90)).status_code == 422


def test_full_crud_appends_revisions_and_retains_deleted_sources(workouts):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    path = f"/api/v1/workouts/{session['id']}"
    block = add_block(client, owner, session, exercises["Pull-up"])
    saved = add_set(client, owner, session, block)
    row = saved["exercises"][0]["sets"][0]
    original_source_id = row["source_record_id"]
    result = client.put(block_path(session, block) + f"/sets/{row['id']}", headers=owner, json=set_input(repetitions=10))
    assert result.status_code == 200
    changed = result.json()["exercises"][0]["sets"][0]
    assert changed["source_record_id"] != original_source_id
    assert changed["metrics"]["volume_kg"] == 860
    result = client.put(block_path(session, block), headers=owner, json={"ordinal": 2, "target_min_reps": 6, "target_max_reps": 10})
    assert result.status_code == 200
    assert result.json()["exercises"][0]["exercise_snapshot"] == saved["exercises"][0]["exercise_snapshot"]
    result = client.post(block_path(session, block) + "/complete", headers=owner)
    assert result.status_code == 200
    assert result.json()["exercises"][0]["completed"] is True
    assert result.json()["exercises"][0]["progression"]["next_weight_kg"] == 12.5
    corrected = session_input(title="Corrected title", performed_on=day(1))
    assert client.put(path, headers=owner, json=corrected).status_code == 200
    assert client.delete(block_path(session, block) + f"/sets/{row['id']}", headers=owner).status_code == 204
    assert client.get(path, headers=owner).json()["set_count"] == 0
    assert client.put(path, headers=owner, json={**corrected, "bodyweight_kg": 81}).status_code == 422
    assert client.delete(block_path(session, block), headers=owner).status_code == 204
    assert client.delete(path, headers=owner).status_code == 204
    assert client.get(path, headers=owner).status_code == 404
    history = client.get(path + "/history?limit=100", headers=owner).json()
    events = list(reversed(history["items"]))
    assert [event["revision"] for event in events] == list(range(1, history["total"] + 1))
    assert events[2]["id"] == original_source_id
    assert events[2]["payload"]["repetitions"] == 8
    assert events[2]["payload"]["metrics"]["volume_kg"] == 688
    assert events[3]["payload"]["repetitions"] == 10
    assert events[5]["payload"]["progression"]["state"] == "increase_weight"
    assert client.get("/api/v1/workouts", headers=owner).json() == {"items": [], "total": 0}


@pytest.mark.parametrize("parent", ["session", "block"])
def test_parent_deletion_tombstones_children_with_individual_events(workouts, parent):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    add_set(client, owner, session, block)
    path = f"/api/v1/workouts/{session['id']}"
    target = path if parent == "session" else block_path(session, block)
    assert client.delete(target, headers=owner).status_code == 204
    history = client.get(path + "/history", headers=owner).json()
    deletions = [item["entity_type"] for item in history["items"] if item["action"] == "delete"]
    assert deletions == (["session", "exercise", "set"] if parent == "session" else ["exercise", "set"])
    assert client.get(f"/api/v1/workouts/exercise-history/{exercises['Pull-up']}", headers=owner).json()["total"] == 0
    assert client.get("/api/v1/workouts/analytics", headers=owner).json()["total_volume_kg"] == 0


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_source_journal_rejects_bulk_sql_changes(workouts, identity, operation):
    from app.models import WorkoutSourceRecord

    client, (owner, _), _ = workouts
    session = create_workout(client, owner)
    with identity.sessions() as db:
        statement = update(WorkoutSourceRecord).values(action="delete") if operation == "update" else delete(WorkoutSourceRecord)
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(statement.where(WorkoutSourceRecord.session_id == session["id"]))
        db.rollback()
    history = client.get(f"/api/v1/workouts/{session['id']}/history", headers=owner).json()
    assert history["total"] == 1
    assert history["items"][0]["action"] == "create"


@pytest.mark.parametrize(
    "exercise,current,previous,expected,weight,target",
    [
        ("Pull-up", {"repetitions": 10, "rpe": 8}, None, "increase_weight", 12.5, 8),
        ("Squat", {"repetitions": 10, "rpe": 8}, None, "increase_weight", 15, 8),
        ("Pull-up", {"repetitions": 8, "rpe": 9.5}, None, "increase_reps", 10, 9),
        ("Pull-up", {"repetitions": 9, "rpe": 9}, None, "hold", 10, 8),
        ("Pull-up", {"repetitions": 7, "rpe": 9}, None, "hold", 10, 8),
        ("Pull-up", {"repetitions": 7, "rpe": 9}, {"repetitions": 7, "rpe": 9}, "deload", 9, 8),
        ("Pull-up", {"repetitions": 0, "rpe": 10}, {"repetitions": 7, "rpe": 9}, "deload", 9, 8),
        ("Pull-up", {"repetitions": 10, "rpe": None}, None, "insufficient_data", 10, 8),
        ("Pull-up", {"repetitions": 10, "rpe": None, "rir": 2}, None, "increase_weight", 12.5, 8),
        ("Pull-up", {"repetitions": 10, "rpe": 8}, {"repetitions": 8, "rpe": None}, "insufficient_data", 10, 8),
    ],
)
def test_progression_uses_authoritative_engine_branches(workouts, exercise, current, previous, expected, weight, target):
    client, (owner, _), exercises = workouts
    if previous is not None:
        old = create_workout(client, owner, performed_on=day(1))
        old_block = add_block(client, owner, old, exercises[exercise])
        add_set(client, owner, old, old_block, **previous)
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises[exercise])
    saved = add_set(client, owner, session, block, **current)
    progression = saved["exercises"][0]["progression"]
    assert progression["state"] == expected
    assert progression["next_weight_kg"] == weight
    assert progression["target_reps"] == target
    assert progression["recovery_check"] is (expected == "deload")


def test_progression_checks_every_working_set_and_comparable_loads(workouts):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    add_set(client, owner, session, block, repetitions=10)
    saved = add_set(client, owner, session, block, ordinal=2, repetitions=9)
    assert saved["exercises"][0]["progression"]["state"] == "hold"
    saved = add_set(client, owner, session, block, ordinal=3, repetitions=10, external_load_kg=15)
    progression = saved["exercises"][0]["progression"]
    assert progression["state"] == "insufficient_data"
    assert "comparable" in progression["reason"].lower()
    assert "mixed" in progression["reason"].lower()


def test_nearest_previous_session_excludes_other_users_current_blocks_and_older_failures(workouts):
    client, (owner, other), exercises = workouts
    for user, days_ago, reps in ((owner, 3, 6), (owner, 2, 10), (other, 1, 6)):
        old = create_workout(client, user, performed_on=day(days_ago))
        old_block = add_block(client, user, old, exercises["Pull-up"])
        add_set(client, user, old, old_block, repetitions=reps, rpe=9)
    session = create_workout(client, owner)
    first = add_block(client, owner, session, exercises["Pull-up"])
    add_set(client, owner, session, first, repetitions=6, rpe=9)
    second = add_block(client, owner, session, exercises["Pull-up"], ordinal=2)
    saved = add_set(client, owner, session, second, repetitions=6, rpe=9)
    assert all(block["progression"]["state"] == "hold" for block in saved["exercises"])


def test_timed_zero_and_high_repetition_sets_preserve_raw_records(workouts):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    pull = add_block(client, owner, session, exercises["Pull-up"])
    for ordinal, repetitions in enumerate((0, 37, 1000), start=1):
        saved = add_set(client, owner, session, pull, ordinal=ordinal, repetitions=repetitions)
        row = saved["exercises"][0]["sets"][-1]
        assert row["repetitions"] == repetitions
        assert row["metrics"]["estimated_1rm_kg"] is None
        assert row["metrics"]["one_rm_formula"] is None
        assert row["metrics"]["estimate_unavailable_reason"]
        assert row["metrics"]["volume_kg"] == 86 * repetitions
    plank = add_block(client, owner, session, exercises["Plank"], ordinal=2)
    saved = add_set(client, owner, session, plank, repetitions=None, duration_seconds=45, external_load_kg=0)
    row = saved["exercises"][1]["sets"][0]
    assert row["metrics"]["effective_load_kg"] == 52
    assert row["metrics"]["volume_kg"] is None
    assert row["metrics"]["estimated_1rm_kg"] is None
    assert saved["exercises"][1]["progression"]["state"] == "insufficient_data"
    assert "does not apply" in saved["exercises"][1]["progression"]["reason"]
    assert client.post(block_path(session, plank) + "/sets", headers=owner, json=set_input(ordinal=2)).status_code == 422
    assert client.post(block_path(session, pull) + "/sets", headers=owner, json=set_input(ordinal=4, repetitions=None, duration_seconds=30)).status_code == 422
    analytics = client.get("/api/v1/workouts/analytics", headers=owner).json()
    assert analytics["prs"] == []
    assert analytics["strength_curves"] == []
    assert next(m for m in analytics["muscles"] if m["id"] == "lats")["hard_sets"] == 2
    assert next(m for m in analytics["muscles"] if m["id"] == "abs")["hard_sets"] == 1


def test_warmup_exclusion_daily_curves_weighted_volume_and_fatigue(workouts):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner, sleep_hours=7, soreness=4)
    block = add_block(client, owner, session, exercises["Pull-up"])
    add_set(client, owner, session, block, set_type="warmup", repetitions=20, external_load_kg=100, rpe=10)
    add_set(client, owner, session, block, ordinal=2, repetitions=8, rpe=8)
    add_set(client, owner, session, block, ordinal=3, set_type="drop_set", repetitions=6, external_load_kg=0, rpe=10)
    saved = add_set(client, owner, session, block, ordinal=4, set_type="failure", repetitions=5, external_load_kg=0, rpe=10)
    assert saved["total_volume_kg"] == 688 + 456 + 380
    assert saved["exercises"][0]["progression"]["state"] == "hold"
    second = create_workout(client, owner)
    second_block = add_block(client, owner, second, exercises["Pull-up"])
    add_set(client, owner, second, second_block, repetitions=10, rpe=None, rir=2)
    expected_volume = 688 + 456 + 380 + 860
    analytics = client.get("/api/v1/workouts/analytics?weeks=2", headers=owner).json()
    assert analytics["weeks"] == 2
    assert analytics["total_sessions"] == 2
    assert analytics["total_volume_kg"] == expected_volume
    lats = next(m for m in analytics["muscles"] if m["id"] == "lats")
    biceps = next(m for m in analytics["muscles"] if m["id"] == "biceps")
    assert lats["hard_sets"] == 4
    assert lats["weekly_hard_sets"] == 2
    assert lats["landmark"] == "below_maintenance"
    assert biceps["hard_sets"] == pytest.approx(2.4)
    assert biceps["volume_kg"] == pytest.approx(expected_volume * .6)
    points = analytics["strength_curves"][0]["points"]
    assert len(points) == 1
    assert points[0]["date"] == day()
    assert points[0]["estimated_1rm_kg"] == pytest.approx(86 * (1 + 10 / 30))
    assert points[0]["volume_kg"] == expected_volume
    assert analytics["prs"][0]["estimated_1rm_kg"] == points[0]["estimated_1rm_kg"]
    assert analytics["fatigue"]["components"]["effort_rpe"] == pytest.approx(7 / 9)
    assert analytics["fatigue"]["components"]["weekly_hard_sets"] == pytest.approx(2 / 22)
    assert analytics["fatigue"]["components"]["sleep_hours"] == pytest.approx(1 / 8)
    assert analytics["fatigue"]["components"]["soreness"] == .4
    assert analytics["fatigue"]["missing_inputs"] == []


def test_analytics_empty_history_window_and_all_time_pr(workouts):
    client, (owner, _), exercises = workouts
    empty = client.get("/api/v1/workouts/analytics", headers=owner).json()
    assert empty["total_sessions"] == 0
    assert empty["total_volume_kg"] == 0
    assert empty["muscles"] == empty["strength_curves"] == empty["prs"] == []
    assert empty["fatigue"]["state"] == "unavailable"
    assert empty["fatigue"]["score"] is None
    assert set(empty["fatigue"]["missing_inputs"]) == {"effort_rpe", "weekly_hard_sets", "sleep_hours", "soreness"}
    old = create_workout(client, owner, performed_on=day(20))
    block = add_block(client, owner, old, exercises["Pull-up"])
    add_set(client, owner, old, block)
    recent = client.get("/api/v1/workouts/analytics?weeks=1", headers=owner).json()
    assert recent["total_sessions"] == 0
    assert recent["muscles"] == recent["strength_curves"] == []
    assert len(recent["prs"]) == 1
    assert recent["fatigue"]["state"] == "unavailable"
    assert client.get("/api/v1/workouts/analytics?weeks=4", headers=owner).json()["total_sessions"] == 1


def test_ordinals_are_unique_but_tombstones_release_them(workouts):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    block_payload = {"exercise_id": exercises["Pull-up"], "ordinal": 1, "target_min_reps": 8, "target_max_reps": 10}
    assert client.post(f"/api/v1/workouts/{session['id']}/exercises", headers=owner, json=block_payload).status_code == 409
    second = add_block(client, owner, session, exercises["Squat"], ordinal=2)
    assert client.put(block_path(session, second), headers=owner, json={k: v for k, v in block_payload.items() if k != "exercise_id"}).status_code == 409
    saved = add_set(client, owner, session, block)
    row = saved["exercises"][0]["sets"][0]
    assert client.post(block_path(session, block) + "/sets", headers=owner, json=set_input()).status_code == 409
    assert client.put(block_path(session, block) + f"/sets/{row['id']}", headers=owner, json=set_input()).status_code == 200
    assert client.delete(block_path(session, block) + f"/sets/{row['id']}", headers=owner).status_code == 204
    add_set(client, owner, session, block)
    assert client.delete(block_path(session, block), headers=owner).status_code == 204
    replacement = add_block(client, owner, session, exercises["Pull-up"])
    assert replacement["id"] != block["id"]


def test_private_nested_ids_and_crossed_parents_are_not_resolvable(workouts):
    client, (owner, other), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    saved = add_set(client, owner, session, block)
    row = saved["exercises"][0]["sets"][0]
    own_second = create_workout(client, owner)
    second_block = add_block(client, owner, own_second, exercises["Pull-up"])
    other_session = create_workout(client, other)
    other_block = add_block(client, other, other_session, exercises["Pull-up"])
    other_saved = add_set(client, other, other_session, other_block)
    other_set = other_saved["exercises"][0]["sets"][0]
    path = f"/api/v1/workouts/{session['id']}"
    for method, suffix, payload in (
        ("get", "", None), ("put", "", session_input()), ("delete", "", None),
        ("get", "/history", None),
        ("post", "/exercises", {"exercise_id": exercises["Pull-up"], "ordinal": 2, "target_min_reps": 8, "target_max_reps": 10}),
        ("put", f"/exercises/{block['id']}", {"ordinal": 1, "target_min_reps": 8, "target_max_reps": 10}),
        ("delete", f"/exercises/{block['id']}", None),
        ("post", f"/exercises/{block['id']}/complete", None),
        ("post", f"/exercises/{block['id']}/sets", set_input()),
        ("put", f"/exercises/{block['id']}/sets/{row['id']}", set_input()),
        ("delete", f"/exercises/{block['id']}/sets/{row['id']}", None),
    ):
        result = getattr(client, method)(path + suffix, headers=other, **({"json": payload} if payload is not None else {}))
        assert result.status_code == 404, result.text
    for wrong_block in (second_block, other_block):
        wrong_path = block_path(session, wrong_block)
        assert client.post(wrong_path + "/sets", headers=owner, json=set_input()).status_code == 404
        assert client.post(wrong_path + "/complete", headers=owner).status_code == 404
        assert client.put(wrong_path, headers=owner, json={"ordinal": 1, "target_min_reps": 8, "target_max_reps": 10}).status_code == 404
        assert client.delete(wrong_path, headers=owner).status_code == 404
    for wrong_path in (
        block_path(own_second, second_block) + f"/sets/{row['id']}",
        block_path(session, block) + f"/sets/{other_set['id']}",
    ):
        assert client.put(wrong_path, headers=owner, json=set_input()).status_code == 404
        assert client.delete(wrong_path, headers=owner).status_code == 404
    assert client.get("/api/v1/workouts", headers=other).json()["total"] == 1
    assert client.get(f"/api/v1/workouts/exercise-history/{exercises['Pull-up']}", headers=other).json()["total"] == 1
    assert client.get("/api/v1/workouts/analytics", headers=other).json()["total_sessions"] == 1
    assert client.get(path, headers=owner).json()["revision"] == 3
    assert client.get("/api/v1/workouts/not-a-uuid", headers=owner).status_code == 404


def test_reference_privacy_and_deleted_reference_history(workouts):
    client, (owner, other), _ = workouts
    custom = client.post("/api/v1/exercises", headers=owner, json={
        "name": "Private pull", "equipment": "Bar", "met": 6,
        "biomechanical_multiplier": .95, "measurement_type": "reps", "classification": "upper_compound",
        "muscles": [{"muscle_id": "lats", "contribution": 1}],
    })
    assert custom.status_code == 201
    exercise_id = custom.json()["id"]
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercise_id)
    add_set(client, owner, session, block)
    other_session = create_workout(client, other)
    assert client.post(f"/api/v1/workouts/{other_session['id']}/exercises", headers=other, json={
        "exercise_id": exercise_id, "ordinal": 1, "target_min_reps": 8, "target_max_reps": 10,
    }).status_code == 404
    history_path = f"/api/v1/workouts/exercise-history/{exercise_id}"
    assert client.get(history_path, headers=other).status_code == 404
    before = client.get(history_path, headers=owner).json()
    assert before["total"] == 1
    assert client.delete(f"/api/v1/exercises/{exercise_id}", headers=owner).status_code == 204
    assert client.get(history_path, headers=owner).json() == before
    assert client.get(history_path, headers=other).status_code == 404
    assert client.get(f"/api/v1/workouts/{session['id']}", headers=owner).json()["exercises"][0]["exercise_snapshot"]["name"] == "Private pull"


def test_paging_date_filters_and_revision_offsets(workouts):
    client, (owner, _), exercises = workouts
    for days_ago in (0, 1, 2):
        session = create_workout(client, owner, performed_on=day(days_ago))
        block = add_block(client, owner, session, exercises["Pull-up"])
        add_set(client, owner, session, block)
    page = client.get("/api/v1/workouts?offset=1&limit=1", headers=owner).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1
    assert page["items"][0]["performed_on"] == day(1)
    filtered = client.get(f"/api/v1/workouts?from_date={day(1)}&to_date={day(1)}", headers=owner).json()
    assert filtered["total"] == 1
    assert filtered["items"][0] == page["items"][0]
    source = client.get(f"/api/v1/workouts/{session['id']}/history?offset=1&limit=1", headers=owner).json()
    assert source["total"] == 3
    assert [item["revision"] for item in source["items"]] == [2]
    history = client.get(f"/api/v1/workouts/exercise-history/{exercises['Pull-up']}?offset=1&limit=1", headers=owner).json()
    assert history["total"] == 3
    assert len(history["items"]) == 1
    assert history["items"][0]["performed_on"] == day(1)
    assert client.get("/api/v1/workouts?offset=50", headers=owner).json() == {"items": [], "total": 3}
    for suffix in ("?offset=-1", "?limit=0", "?limit=101", f"?from_date={day()}&to_date={day(1)}"):
        assert client.get("/api/v1/workouts" + suffix, headers=owner).status_code == 422
    for weeks in (0, 5):
        assert client.get(f"/api/v1/workouts/analytics?weeks={weeks}", headers=owner).status_code == 422


@pytest.mark.parametrize("changes", [
    {"performed_on": "2026-02-30"}, {"performed_on": day(-1)},
    {"bodyweight_kg": 19}, {"bodyweight_kg": 501}, {"bodyweight_kg": "NaN"},
    {"title": "   "}, {"owner_id": "spoof"}, {"sleep_hours": 25}, {"soreness": -1},
])
def test_session_input_validation(workouts, changes):
    client, (owner, _), _ = workouts
    assert client.post("/api/v1/workouts", headers=owner, json=session_input(**changes)).status_code == 422
    assert client.get("/api/v1/workouts", headers=owner).json()["total"] == 0


@pytest.mark.parametrize("changes", [
    {"ordinal": 0}, {"ordinal": 1.5}, {"external_load_kg": -1}, {"external_load_kg": 1001},
    {"external_load_kg": "Infinity"}, {"repetitions": -1}, {"repetitions": 1001},
    {"repetitions": True}, {"repetitions": None}, {"duration_seconds": 30},
    {"rpe": 0}, {"rir": 10}, {"rpe": 8, "rir": 1}, {"rest_seconds": 7201},
    {"set_type": "unknown"}, {"metrics": {"effective_load_kg": 123}}, {"bodyweight_kg": 90},
])
def test_set_validation_does_not_append_sources(workouts, changes):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    assert client.post(block_path(session, block) + "/sets", headers=owner, json=set_input(**changes)).status_code == 422
    saved = client.get(f"/api/v1/workouts/{session['id']}", headers=owner).json()
    assert saved["revision"] == 2
    assert saved["set_count"] == 0


def test_authentication_and_completed_profile_required(identity):
    from app import profile, workout_routes

    identity.app.include_router(profile.router)
    identity.app.include_router(workout_routes.router)
    with TestClient(identity.app, headers={"Origin": "http://testserver"}) as client:
        for path in ("/api/v1/workouts", "/api/v1/workouts/analytics"):
            assert client.get(path).status_code == 401
        result = client.post("/api/v1/auth/register", json={"email": "not.onboarded@example.com", "password": identity.password})
        assert result.status_code == 201
        headers = {"Authorization": "Bearer " + result.json()["access_token"]}
        assert client.get("/api/v1/workouts", headers=headers).status_code == 403
        assert client.get("/api/v1/workouts/analytics", headers=headers).status_code == 403
        assert client.post("/api/v1/workouts", headers=headers, json=session_input()).status_code == 403


@pytest.mark.parametrize("repetitions,formula,estimate", [
    (10, "epley", 86 * (1 + 10 / 30)),
    (11, "brzycki", 86 * 36 / 26),
    (36, "brzycki", 86 * 36),
])
def test_saved_one_rm_formula_boundaries(workouts, repetitions, formula, estimate):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    saved = add_set(client, owner, session, block, repetitions=repetitions)
    metrics = saved["exercises"][0]["sets"][0]["metrics"]
    assert metrics["one_rm_formula"] == formula
    assert metrics["estimated_1rm_kg"] == pytest.approx(estimate)
    assert metrics["estimate_unavailable_reason"] is None


def test_zero_load_and_warmup_only_do_not_fabricate_strength_or_effort(workouts):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Squat"])
    saved = add_set(client, owner, session, block, set_type="warmup", external_load_kg=0, rpe=None)
    row = saved["exercises"][0]["sets"][0]
    assert row["metrics"]["effective_load_kg"] == 0
    assert row["metrics"]["estimated_1rm_kg"] is None
    assert "positive effective load" in row["metrics"]["estimate_unavailable_reason"]
    assert saved["exercises"][0]["progression"]["state"] == "insufficient_data"
    assert saved["total_volume_kg"] == 0
    analysis = client.get("/api/v1/workouts/analytics", headers=owner).json()
    assert analysis["muscles"] == analysis["prs"] == analysis["strength_curves"] == []
    assert analysis["fatigue"]["state"] == "unavailable"


def test_weekly_landmarks_use_window_average_not_total_credits(workouts):
    client, (owner, _), exercises = workouts
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    for ordinal in range(1, 13):
        add_set(client, owner, session, block, ordinal=ordinal)
    one_week = client.get("/api/v1/workouts/analytics?weeks=1", headers=owner).json()
    two_weeks = client.get("/api/v1/workouts/analytics?weeks=2", headers=owner).json()
    first = next(m for m in one_week["muscles"] if m["id"] == "lats")
    second = next(m for m in two_weeks["muscles"] if m["id"] == "lats")
    assert first["hard_sets"] == second["hard_sets"] == 12
    assert first["weekly_hard_sets"] == 12
    assert first["landmark"] == "MAV"
    assert second["weekly_hard_sets"] == 6
    assert second["landmark"] == "MV"
    assert two_weeks["fatigue"]["components"]["weekly_hard_sets"] == pytest.approx(6 / 22)
