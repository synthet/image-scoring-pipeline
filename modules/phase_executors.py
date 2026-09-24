"""
Phase Executor Registration — wires PhaseCode to actual runner logic.

Called once at app startup (after db.init_db, before UI build).
Each executor binds:
  - code:             PhaseCode enum value
  - executor_version: bumped when the underlying algorithm/model changes
  - run_folder:       fn(folder_path, job_id) -> None
  - depends_on:       hard prerequisites — phase codes that must be 'done' first
  - preferred_before: advisory consumers this phase should precede, but never blocks
"""
import logging

from modules.phases import (
    PHASE_PREFERRED_BEFORE,
    PHASE_PREREQUISITES,
    PhaseCode,
    PhaseExecutor,
    PhaseRegistry,
)

logger = logging.getLogger(__name__)


def _prereqs(code: PhaseCode) -> list[str]:
    """Hard prerequisites for ``code``, read from the one authoritative table.

    ``PHASE_PREREQUISITES`` is what ``assert_prereqs_for_scope`` actually enforces;
    deriving ``depends_on`` from it makes the two structurally impossible to drift.
    """
    return list(PHASE_PREREQUISITES[code.value])


def _preferred(code: PhaseCode) -> list[str]:
    """Advisory consumers for ``code``, read from :data:`PHASE_PREFERRED_BEFORE`.

    Same derivation as :func:`_prereqs`, different table: a preferred edge orders the
    work when both phases are co-requested but never gates the consumer.  Absent keys
    are normal -- most phases have no advisory edges.
    """
    return list(PHASE_PREFERRED_BEFORE.get(code.value, ()))


def register_all(
    scoring_runner=None,
    tagging_runner=None,
    clustering_runner=None,
    selection_runner=None,
    bird_species_runner=None,
    indexing_runner=None,
    metadata_runner=None,
    localization_runner=None,
):
    """
    Register all known phase executors.

    Runners are optional — if a runner is None, that phase will appear in the
    UI (from the DB) but its button will be disabled (no executor registered).
    """

    # Phase A — Indexing
    if indexing_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.INDEXING,
            executor_version="1.0.0",
            run_folder=indexing_runner.start_batch,
            depends_on=_prereqs(PhaseCode.INDEXING),
            preferred_before=_preferred(PhaseCode.INDEXING),
        ))
    else:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.INDEXING,
            executor_version="1.0.0",
            run_folder=None,
            depends_on=_prereqs(PhaseCode.INDEXING),
            preferred_before=_preferred(PhaseCode.INDEXING),
        ))

    # Phase B — Metadata Prep
    if metadata_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.METADATA,
            executor_version="1.0.0",
            run_folder=metadata_runner.start_batch,
            depends_on=_prereqs(PhaseCode.METADATA),
            preferred_before=_preferred(PhaseCode.METADATA),
        ))
    else:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.METADATA,
            executor_version="1.0.0",
            run_folder=None,
            depends_on=_prereqs(PhaseCode.METADATA),
            preferred_before=_preferred(PhaseCode.METADATA),
        ))

    # Localization (shadow, #387) — runs after metadata, preferred before consumers.
    if localization_runner:
        from modules.localization import LOCALIZATION_RUNNER_VERSION

        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.LOCALIZATION,
            executor_version=LOCALIZATION_RUNNER_VERSION,
            run_folder=localization_runner.start_batch,
            depends_on=_prereqs(PhaseCode.LOCALIZATION),
            preferred_before=_preferred(PhaseCode.LOCALIZATION),
        ))

    # Phase C — Scoring
    if scoring_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.SCORING,
            executor_version=_get_scorer_version(scoring_runner),
            run_folder=scoring_runner.start_batch,
            depends_on=_prereqs(PhaseCode.SCORING),
            preferred_before=_preferred(PhaseCode.SCORING),
        ))

    # Phase D — Culling & Stacks (clustering OR selection)
    if selection_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.CULLING,
            executor_version="1.0.0",
            run_folder=selection_runner.start_batch,
            depends_on=_prereqs(PhaseCode.CULLING),
            preferred_before=_preferred(PhaseCode.CULLING),
        ))
    elif clustering_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.CULLING,
            executor_version="1.0.0",
            run_folder=clustering_runner.start_batch,
            depends_on=_prereqs(PhaseCode.CULLING),
            preferred_before=_preferred(PhaseCode.CULLING),
        ))

    # Phase E — Keywords
    if tagging_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.KEYWORDS,
            executor_version="1.0.0",
            run_folder=tagging_runner.start_batch,
            depends_on=_prereqs(PhaseCode.KEYWORDS),
            preferred_before=_preferred(PhaseCode.KEYWORDS),
        ))

    # Phase F — Bird Species
    if bird_species_runner:
        from modules.bird_species import BIRD_SPECIES_RUNNER_VERSION

        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.BIRD_SPECIES,
            executor_version=BIRD_SPECIES_RUNNER_VERSION,
            run_folder=bird_species_runner.start_batch,
            depends_on=_prereqs(PhaseCode.BIRD_SPECIES),
            preferred_before=_preferred(PhaseCode.BIRD_SPECIES),
        ))

    registered = [e.code for e in PhaseRegistry.get_all()]
    logger.info("Phase executors registered: %s", registered)


def _get_scorer_version(scoring_runner) -> str:
    """Phase-registry scoring version (must match IPS writes in pipeline runners).

    Do not use per-model ``shared_scorer.VERSION`` (e.g. topiq-nr-1) here — that tag
    describes the active backend, not the pipeline scoring phase generation stored in
    ``image_phase_status.executor_version``.
    """
    _ = scoring_runner
    from modules.phases import SCORING_EXECUTOR_VERSION

    return SCORING_EXECUTOR_VERSION
