"""API routes: score-dimension analytics (rank curves, distributions, correlation, OLS, stacks)."""

from __future__ import annotations

import gzip
import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response

from modules.api_models import (
    ScoreKeywordProfilesResponse,
    ScoreMatrixResponse,
    ScoreRegressionResponse,
    ScoreStacksResponse,
    ScoreStatsResponse,
)

logger = logging.getLogger(__name__)

# Handlers are sync (``def``) on purpose: matrix loads and statistics are CPU/DB
# bound, so FastAPI runs them in its threadpool instead of the event loop.

_KEYWORD_DESC = "Restrict to images tagged with this keyword (exact, case-insensitive). Omit for the full library."


def _raise_for(exc: Exception, op: str) -> None:
    from modules.score_analytics.service import ScoreAnalyticsInputError

    if isinstance(exc, ScoreAnalyticsInputError):
        raise HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=501, detail=str(exc))
    logger.exception("%s failed", op)
    raise HTTPException(status_code=500, detail=str(exc))


def create_score_analytics_router() -> APIRouter:
    router = APIRouter()

    @router.get(
        "/analytics/scores/matrix",
        response_model=None,
        responses={200: {"model": ScoreMatrixResponse}, 304: {"description": "Not modified (ETag match)"}},
        summary="Image × score-dimension matrix",
        description=(
            "Every image with every score dimension (composites + all models incl. shadow), "
            "column-oriented, `COALESCE(normalized, raw_score)` rounded to 3 decimals. "
            "Cached in-process; supports `If-None-Match` → 304. PostgreSQL only."
        ),
    )
    def get_score_matrix(request: Request, keyword: str | None = Query(None, description=_KEYWORD_DESC)):
        from modules.score_analytics import data

        try:
            body_gz, etag = data.get_matrix_payload(keyword)
        except Exception as e:
            _raise_for(e, "get_score_matrix")
        headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Accept-Encoding"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        if "gzip" in request.headers.get("accept-encoding", ""):
            headers["Content-Encoding"] = "gzip"
            return Response(content=body_gz, media_type="application/json", headers=headers)
        return Response(content=gzip.decompress(body_gz), media_type="application/json", headers=headers)

    @router.get(
        "/analytics/scores/stats",
        response_model=ScoreStatsResponse,
        summary="Score-dimension descriptives and correlations",
        description=(
            "Per-dimension descriptives (mean, median, mode, IQR, std, skewness, kurtosis, "
            "boxplot whiskers, 50-bin histogram) and pairwise-complete Pearson / Spearman "
            "matrices with p-values and n. PostgreSQL only."
        ),
    )
    def get_score_stats(keyword: str | None = Query(None, description=_KEYWORD_DESC)):
        from modules.score_analytics import service

        try:
            return service.get_stats(keyword)
        except Exception as e:
            _raise_for(e, "get_score_stats")

    @router.get(
        "/analytics/scores/regression",
        response_model=ScoreRegressionResponse,
        summary="OLS regression of a target score on predictor scores",
        description=(
            "Multiple linear regression on complete rows: coefficients (β, standardized β, SE, t, p, "
            "95% CI, VIF), R², adjusted R², 5-fold CV R², RMSE, MAE, F-test, sampled residuals and "
            "rule-based recommendations. `predictors` defaults to all non-shadow models. "
            "PostgreSQL only."
        ),
    )
    def get_score_regression(
        target: str = Query("general", description="Dimension to predict (e.g. general)"),
        predictors: str | None = Query(None, description="Comma-separated predictor dimensions"),
        keyword: str | None = Query(None, description=_KEYWORD_DESC),
    ):
        from modules.score_analytics import service

        preds = [p.strip() for p in predictors.split(",") if p.strip()] if predictors else None
        try:
            return service.get_regression(target, preds, keyword)
        except Exception as e:
            _raise_for(e, "get_score_regression")

    @router.get(
        "/analytics/scores/stacks",
        response_model=ScoreStacksResponse,
        summary="Within-stack culling signal per score dimension",
        description=(
            "For stacks with at least `min_size` scored images: within-stack spread, within-stack "
            "variance share, tie rate, top-gap, pick/reject pairwise AUC (images.pick_status), "
            "top-1 pick rate, stacks.best_image_id match rate, and mean within-stack Spearman "
            "agreement between dimensions. PostgreSQL only."
        ),
    )
    def get_score_stacks(
        keyword: str | None = Query(None, description=_KEYWORD_DESC),
        min_size: int = Query(2, ge=2, le=1000, description="Minimum scored images per stack"),
    ):
        from modules.score_analytics import service

        try:
            return service.get_stacks(keyword, min_size)
        except Exception as e:
            _raise_for(e, "get_score_stacks")

    @router.get(
        "/analytics/scores/keywords",
        response_model=ScoreKeywordProfilesResponse,
        summary="Per-keyword score profiles",
        description=(
            "For the most frequent keywords: per-dimension descriptives of the keyword layer and "
            "its shift vs the rest of the library (mean delta, Cohen's d, percentile-rank shift). "
            "PostgreSQL only."
        ),
    )
    def get_score_keyword_profiles(
        limit: int = Query(20, ge=1, le=200, description="Number of keywords (by image count)"),
        min_images: int = Query(30, ge=1, description="Skip keywords with fewer images"),
    ):
        from modules.score_analytics import service

        try:
            return service.get_keyword_profiles(limit, min_images)
        except Exception as e:
            _raise_for(e, "get_score_keyword_profiles")

    return router
