-- Repair job_phases rows stuck as 'running' after jobs already reached a terminal status.
-- Cause (fixed in db.set_job_phase_state / update_job_status): terminal sync completed one
-- phase and auto-advanced the next to 'running' while the job was already completed.
--
-- Firebird-compatible. Review preview SELECT before running UPDATEs. Use a backup if unsure.
--
-- Preview stuck rows:
-- SELECT jp.id, jp.job_id, jp.phase_code, jp.state, j.status
-- FROM job_phases jp
-- JOIN jobs j ON j.id = jp.job_id
-- WHERE jp.state = 'running'
--   AND LOWER(TRIM(j.status)) IN ('completed', 'failed', 'canceled', 'cancelled', 'interrupted');

UPDATE job_phases jp
SET state = 'completed',
    completed_at = COALESCE(
      jp.completed_at,
      (SELECT finished_at FROM jobs j WHERE j.id = jp.job_id),
      (SELECT completed_at FROM jobs j WHERE j.id = jp.job_id),
      CURRENT_TIMESTAMP
    )
WHERE jp.state = 'running'
  AND EXISTS (
    SELECT 1 FROM jobs j
    WHERE j.id = jp.job_id
      AND LOWER(TRIM(j.status)) = 'completed'
  );

UPDATE job_phases jp
SET state = 'skipped',
    completed_at = COALESCE(
      jp.completed_at,
      (SELECT finished_at FROM jobs j WHERE j.id = jp.job_id),
      (SELECT completed_at FROM jobs j WHERE j.id = jp.job_id),
      CURRENT_TIMESTAMP
    )
WHERE jp.state = 'running'
  AND EXISTS (
    SELECT 1 FROM jobs j
    WHERE j.id = jp.job_id
      AND LOWER(TRIM(j.status)) IN ('failed', 'canceled', 'cancelled', 'interrupted')
  );
