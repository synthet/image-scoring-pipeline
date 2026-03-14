"""
Pipeline Phase Architecture — Configurable, data-driven processing phases.

Phases are registered in the DB (PIPELINE_PHASES table) and bound to
executors at runtime via PhaseRegistry.  A phase that exists in the DB
but has no registered executor will appear in the UI but cannot be triggered.

Status values (for IMAGE_PHASE_STATUS):
    not_started | running | done | skipped | failed

Folder-level summaries are computed live (no stored table).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase code enum — canonical identifiers
# ---------------------------------------------------------------------------

class PhaseCode(str, Enum):
    """
    Canonical phase codes.  Must match pipeline_phases.code in the DB.

    Using ``str`` mixin so values serialise cleanly to JSON / SQL.
    """
    INDEXING  = "indexing"
    METADATA  = "metadata"
    SCORING   = "scoring"
    CULLING   = "culling"
    KEYWORDS  = "keywords"


# ---------------------------------------------------------------------------
# Phase status enum
# ---------------------------------------------------------------------------

class PhaseStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING     = "running"
    DONE        = "done"
    SKIPPED     = "skipped"
    FAILED      = "failed"

# Allowed transitions: from_status -> set of to_statuses
ALLOWED_TRANSITIONS = {
    PhaseStatus.NOT_STARTED: {PhaseStatus.RUNNING},
    PhaseStatus.RUNNING:     {PhaseStatus.DONE, PhaseStatus.FAILED, PhaseStatus.SKIPPED},
    PhaseStatus.DONE:        {PhaseStatus.RUNNING},      # rerun
    PhaseStatus.FAILED:      {PhaseStatus.RUNNING},      # retry
    PhaseStatus.SKIPPED:     {PhaseStatus.RUNNING},      # explicit rerun
}


# ---------------------------------------------------------------------------
# Folder-level summary status
# ---------------------------------------------------------------------------

class FolderPhaseStatus(str, Enum):
    NOT_STARTED = "not_started"
    PARTIAL     = "partial"
    DONE        = "done"
    FAILED      = "failed"


# ---------------------------------------------------------------------------
# Phase executor — binds a code to its run logic
# ---------------------------------------------------------------------------

@dataclass
class PhaseExecutor:
    """
    Binds a phase code to its actual execution logic.

    Attributes:
        code:             Phase code (must match PIPELINE_PHASES.code).
        executor_version: Version of the algo/model.  Bumped when the model
                          or algorithm changes — independent of APP_VERSION.
        run_folder:       ``fn(folder_path, job_id) -> None``
        run_image:        ``fn(image_path, job_id) -> None``  (optional)
        depends_on:       List of phase codes that must be ``done`` before
                          this phase can run.  (Enforcement deferred to v2.)
    """
    code:             str
    executor_version: str
    run_folder:       Optional[Callable[..., Any]] = None
    run_image:        Optional[Callable[..., Any]] = None
    depends_on:       List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase registry — runtime lookup
# ---------------------------------------------------------------------------

class PhaseRegistry:
    """
    Runtime registry mapping ``phase_code -> PhaseExecutor``.

    Executors are registered at app startup; the Folder Tree UI queries this
    to decide which buttons are active.
    """
    _executors: dict[str, PhaseExecutor] = {}

    @classmethod
    def register(cls, executor: PhaseExecutor):
        logger.info("PhaseRegistry: registered executor for '%s' (v%s)",
                     executor.code, executor.executor_version)
        cls._executors[executor.code] = executor

    @classmethod
    def get(cls, code: str) -> Optional[PhaseExecutor]:
        return cls._executors.get(code)

    @classmethod
    def get_all(cls) -> list[PhaseExecutor]:
        return list(cls._executors.values())

    @classmethod
    def is_registered(cls, code: str) -> bool:
        return code in cls._executors


# ---------------------------------------------------------------------------
# Seed data — inserted into PIPELINE_PHASES on first startup
# ---------------------------------------------------------------------------

SEED_PHASES = [
    {
        "code": "indexing",
        "name": "Indexing",
        "description": "Scan folder, create/update DB records, compute file hash and register image paths.",
        "sort_order": 1,
        "enabled": 1,
        "optional": 0,
        "default_skip": False,
    },
    {
        "code": "metadata",
        "name": "Physical Metadata",
        "description": "Extract EXIF/XMP tags, generate thumbnails, and prepare files for scoring.",
        "sort_order": 2,
        "enabled": 1,
        "optional": 0,
        "default_skip": False,
    },
    {
        "code": PhaseCode.SCORING,
        "name": "Scoring",
        "description": "AI quality scoring (MUSIQ, SPAQ, AVA, LIQE, etc.)",
        "sort_order": 30,
        "optional": False,
        "default_skip": False,
    },
    {
        "code": PhaseCode.CULLING,
        "name": "Culling & Stacks",
        "description": "Clustering into stacks, cull/pick decisions",
        "sort_order": 40,
        "optional": True,
        "default_skip": False,
    },
    {
        "code": PhaseCode.KEYWORDS,
        "name": "Keywords",
        "description": "CLIP keyword tagging + BLIP captioning",
        "sort_order": 50,
        "optional": True,
        "default_skip": False,
    },
]
