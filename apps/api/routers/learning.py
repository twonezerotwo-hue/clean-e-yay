"""GET /api/v1/learning/summary"""
from __future__ import annotations

from fastapi import APIRouter

from packages.learning.summary import build_summary

router = APIRouter(tags=["learning"])


@router.get("/learning/summary")
def get_learning_summary() -> dict:
    return build_summary()
