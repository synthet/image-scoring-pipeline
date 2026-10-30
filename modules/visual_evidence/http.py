"""Evidence v1 compatibility plus explicit asynchronous diagnostic generation."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from modules.visual_evidence.jobs import close_manager, get_manager
from modules.visual_evidence.service import build_evidence_for_image


class DiagnosticRequest(BaseModel):
    layers: list[Literal["sharpness", "peaking", "noise", "mask", "head"]] = Field(min_length=1, max_length=5)
    refresh: bool = False


async def _call(function, *args, **kwargs):
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except KeyError:
        raise HTTPException(status_code=404, detail="Image not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError:
        raise HTTPException(status_code=429, detail="Diagnostic capacity reached; retry shortly")


def create_router():
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await asyncio.to_thread(close_manager)

    router = APIRouter(lifespan=lifespan)

    @router.get("/images/{image_id}/evidence", summary="Cached visual evidence manifest")
    async def manifest(image_id: int, schema_version: int = Query(1, ge=1, le=2)):
        if schema_version == 1:
            value = await _call(build_evidence_for_image, image_id)
            return value.model_dump()
        return await _call(get_manager().manifest, image_id)

    @router.post("/images/{image_id}/evidence/requests", status_code=202, summary="Request on-demand diagnostics")
    async def request(image_id: int, body: DiagnosticRequest):
        return await _call(get_manager().request, image_id, body.layers, refresh=body.refresh)

    @router.delete("/images/{image_id}/evidence/requests/{request_id}", status_code=204, summary="Cancel one diagnostic subscription")
    async def cancel(image_id: int, request_id: str):
        if not await _call(get_manager().cancel, image_id, request_id):
            raise HTTPException(status_code=404, detail="Diagnostic request not found")
        return Response(status_code=204)

    @router.get("/images/{image_id}/evidence/artifacts/{artifact_id}", summary="Read an immutable diagnostic artifact")
    async def artifact(image_id: int, artifact_id: str):
        cache = get_manager().cache
        pin = None
        try:
            pin = cache.pin(image_id, artifact_id[:64])
            pin.__enter__()
            path = cache.artifact(image_id, artifact_id)
            return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg",
                                headers={"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
                                background=BackgroundTask(pin.__exit__, None, None, None))
        except (ValueError, FileNotFoundError):
            if pin is not None:
                pin.__exit__(None, None, None)
            raise HTTPException(status_code=404, detail="Artifact expired or unavailable")

    return router
