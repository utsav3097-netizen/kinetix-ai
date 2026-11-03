"""Authenticated owner-scoped report and immutable planning transport."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth import Database, prevent_caching
from app.models import PlanDraft, Report, TrainingPlanVersion
from app.nutrition_schemas import PageQuery
from app.planning_schemas import (AcceptInput, DraftInput, DraftPage, DraftView, PathPage, PlanEditInput,
                                  ReportInput, ReportPage, ReportView, VersionPage, VersionView)
from app.profile import CompletedProfile
from app.services import plans, reports

report_router = APIRouter(prefix="/api/v1/reports", tags=["reports"], dependencies=[Depends(prevent_caching)])
plan_router = APIRouter(prefix="/api/v1/plans", tags=["plans"], dependencies=[Depends(prevent_caching)])


@report_router.get("", response_model=ReportPage)
def list_reports(profile: CompletedProfile, db: Database, query: Annotated[PageQuery, Query()]):
    result = reports.list_reports(db, profile, query)
    db.commit()
    return result


@report_router.post("", response_model=ReportView, status_code=201)
def create_report(payload: ReportInput, profile: CompletedProfile, db: Database):
    result = reports.view(reports.create_snapshot(db, profile, payload))
    db.commit()
    return result


@report_router.get("/{report_id}", response_model=ReportView)
def read_report(report_id: str, profile: CompletedProfile, db: Database):
    return reports.view(reports.owned(db, Report, profile.user_id, report_id))


@plan_router.get("/paths", response_model=PathPage)
def paths(profile: CompletedProfile, db: Database):
    return plans.path_options(db, profile)


@plan_router.get("/drafts", response_model=DraftPage)
def list_drafts(profile: CompletedProfile, db: Database, query: Annotated[PageQuery, Query()]):
    return plans.list_drafts(db, profile.user_id, query)


@plan_router.post("/drafts", response_model=DraftView, status_code=201)
def generate_draft(payload: DraftInput, profile: CompletedProfile, db: Database):
    result = plans.draft_view(plans.generate_draft(db, profile, payload))
    db.commit()
    return result


@plan_router.get("/drafts/{draft_id}", response_model=DraftView)
def read_draft(draft_id: str, profile: CompletedProfile, db: Database):
    return plans.draft_view(reports.owned(db, PlanDraft, profile.user_id, draft_id))


@plan_router.post("/drafts/{draft_id}/edit", response_model=DraftView, status_code=201)
def edit_draft(draft_id: str, payload: PlanEditInput, profile: CompletedProfile, db: Database):
    result = plans.draft_view(plans.edit_draft(db, profile, draft_id, payload))
    db.commit()
    return result


@plan_router.post("/drafts/{draft_id}/accept", response_model=VersionView, status_code=201)
def accept_draft(draft_id: str, payload: AcceptInput, profile: CompletedProfile, db: Database):
    result = plans.version_view(db, plans.accept_draft(db, profile, draft_id))
    db.commit()
    return result


@plan_router.get("/versions", response_model=VersionPage)
def list_versions(profile: CompletedProfile, db: Database, query: Annotated[PageQuery, Query()]):
    return plans.list_versions(db, profile.user_id, query)


@plan_router.get("/versions/{version_id}", response_model=VersionView)
def read_version(version_id: str, profile: CompletedProfile, db: Database):
    return plans.version_view(db, reports.owned(db, TrainingPlanVersion, profile.user_id, version_id))


@plan_router.get("/active", response_model=VersionView | None)
def active_plan(profile: CompletedProfile, db: Database):
    version = plans.active_version(db, profile.user_id)
    return plans.version_view(db, version) if version else None
