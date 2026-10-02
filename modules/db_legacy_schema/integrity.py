# ruff: noqa: E701
"""Firebird integrity and index-hardening schema stage."""

from typing import Any


def run_integrity_phase(
    conn: Any,
    *,
    table_exists: Any,
    column_exists: Any,
    index_exists: Any,
    constraint_exists: Any,
    logger: Any,
) -> Any:
    """Apply the legacy integrity migrations and return the active connection."""
    _table_exists = table_exists
    _column_exists = column_exists
    _index_exists = index_exists
    _constraint_exists = constraint_exists
    c = conn.cursor()

    # --- Phase 1: Integrity + Index Hardening ---
    # Ref: docs/planning/database/DB_SCHEMA_REFACTOR_PLAN.md
    # All DDL is idempotent (check-then-act). Safe to run on every startup.
    try:
        c = conn.cursor()
        print("[Phase 1] Starting integrity + index hardening...")

        # 1.1: Repair orphan STACKS.BEST_IMAGE_ID rows
        print("  [1.1] Repairing orphan STACKS.BEST_IMAGE_ID...")
        try:
            c.execute("""
                UPDATE stacks SET best_image_id = NULL
                WHERE best_image_id IS NOT NULL
                  AND best_image_id NOT IN (SELECT id FROM images)
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("Phase1 1.1 orphan repair: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
            c = conn.cursor()

        # 1.2: Unique index on IMAGES.FILE_PATH (highest-impact for upsert perf)
        print("  [1.2] Adding UQ_IMAGES_FILE_PATH (with temp index optimization)...")
        if not _index_exists(c, "UQ_IMAGES_FILE_PATH"):
            try:
                # Optimization: create temporary non-unique index for fast de-dup grouping
                if not _index_exists(c, "IDX_TMP_FILE_PATH"):
                    c.execute("CREATE INDEX idx_tmp_file_path ON images(file_path)")
                    conn.commit()
                    c = conn.cursor()

                # Safety: delete exact duplicate file_path rows (keep highest id)
                c.execute("""
                    DELETE FROM images i1
                    WHERE i1.file_path IS NOT NULL
                      AND EXISTS (
                        SELECT 1 FROM images i2
                        WHERE i2.file_path = i1.file_path
                        AND i2.id > i1.id
                    )
                """)
                conn.commit()
                c = conn.cursor()

                # Drop temporary index before creating the final UNIQUE one
                if _index_exists(c, "IDX_TMP_FILE_PATH"):
                    c.execute("DROP INDEX idx_tmp_file_path")
                    conn.commit()
                    c = conn.cursor()

                c.execute(
                    "CREATE UNIQUE INDEX uq_images_file_path ON images(file_path)"
                )
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.2 UQ_IMAGES_FILE_PATH: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                # Emergency cleanup of temp index on failure
                try:
                    c = conn.cursor()
                    if _index_exists(c, "IDX_TMP_FILE_PATH"):
                        c.execute("DROP INDEX idx_tmp_file_path")
                        conn.commit()
                except Exception:
                    pass
                c = conn.cursor()

        # 1.3: Composite indexes for query hot paths
        print("  [1.3] Adding composite indexes (folder_score, stack_score)...")
        if not _index_exists(c, "IDX_IMAGES_FOLDER_SCORE"):
            try:
                c.execute(
                    "CREATE INDEX idx_images_folder_score ON images(folder_id, score_general)"
                )
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.3 IDX_IMAGES_FOLDER_SCORE: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        if not _index_exists(c, "IDX_IMAGES_STACK_SCORE"):
            try:
                c.execute(
                    "CREATE INDEX idx_images_stack_score ON images(stack_id, score_general)"
                )
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.3 IDX_IMAGES_STACK_SCORE: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        # 1.4a: Drop redundant single-column indexes (superseded by composites)
        print("  [1.4a] Dropping redundant single-column indexes...")
        for old_idx in ("IDX_IMAGES_FOLDER_ID", "IDX_IMAGES_STACK_ID"):
            if _index_exists(c, old_idx):
                try:
                    c.execute(f"DROP INDEX {old_idx}")
                    conn.commit()
                    c = conn.cursor()
                except Exception as e:
                    logger.warning("Phase1 1.4a DROP INDEX %s: %s", old_idx, e)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    c = conn.cursor()

        # 1.4b: Drop legacy auto-named FK artifacts on CULLING_PICKS
        # (INTEG_13, INTEG_14 — duplicates of FK_CULLING_PICKS_IMAGES/SESSIONS)
        print("  [1.4b] Dropping legacy CULLING_PICKS FK artifacts...")
        try:
            c.execute("""
                SELECT rdb$constraint_name FROM rdb$relation_constraints
                WHERE rdb$relation_name = 'CULLING_PICKS'
                  AND rdb$constraint_type = 'FOREIGN KEY'
                  AND rdb$constraint_name NOT STARTING WITH 'FK_'
            """)
            orphan_constraints = [row[0].strip() for row in c.fetchall()]
            for cn in orphan_constraints:
                try:
                    c.execute(f'ALTER TABLE culling_picks DROP CONSTRAINT "{cn}"')
                    conn.commit()
                    c = conn.cursor()
                except Exception as e:
                    logger.warning("Phase1 1.4b DROP CONSTRAINT %s: %s", cn, e)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    c = conn.cursor()
        except Exception as e:
            logger.warning("Phase1 1.4b constraint query: %s", e)

        # 1.5a: FK_STACKS_BEST_IMAGE (after orphan repair in 1.1)
        print("  [1.5a] Adding FK_STACKS_BEST_IMAGE...")
        if not _constraint_exists(c, "FK_STACKS_BEST_IMAGE"):
            try:
                c.execute("""
                    ALTER TABLE stacks ADD CONSTRAINT fk_stacks_best_image
                    FOREIGN KEY (best_image_id) REFERENCES images(id) ON DELETE SET NULL
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.5a FK_STACKS_BEST_IMAGE: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        # 1.5b: FK_IMAGES_JOB
        print("  [1.5b] Adding FK_IMAGES_JOB...")
        if not _constraint_exists(c, "FK_IMAGES_JOB"):
            try:
                c.execute(
                    "UPDATE images SET job_id = NULL WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)"
                )
                conn.commit()
                c = conn.cursor()
                c.execute("""
                    ALTER TABLE images ADD CONSTRAINT fk_images_job
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.5b FK_IMAGES_JOB: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        # 1.5c: FK_IMAGES_STACK
        print("  [1.5c] Adding FK_IMAGES_STACK...")
        if not _constraint_exists(c, "FK_IMAGES_STACK"):
            try:
                c.execute(
                    "UPDATE images SET stack_id = NULL WHERE stack_id IS NOT NULL AND stack_id NOT IN (SELECT id FROM stacks)"
                )
                conn.commit()
                c = conn.cursor()
                c.execute("""
                    ALTER TABLE images ADD CONSTRAINT fk_images_stack
                    FOREIGN KEY (stack_id) REFERENCES stacks(id) ON DELETE SET NULL
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.5c FK_IMAGES_STACK: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        # 1.5d: FK_IPS_JOB (IMAGE_PHASE_STATUS.JOB_ID)
        print("  [1.5d] Adding FK_IPS_JOB...")
        if _table_exists(c, "IMAGE_PHASE_STATUS") and not _constraint_exists(
            c, "FK_IPS_JOB"
        ):
            try:
                c.execute(
                    "UPDATE image_phase_status SET job_id = NULL WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)"
                )
                conn.commit()
                c = conn.cursor()
                c.execute("""
                    ALTER TABLE image_phase_status ADD CONSTRAINT fk_ips_job
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.5d FK_IPS_JOB: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        # 1.5e: STACK_CACHE FKs
        print("  [1.5e] Adding STACK_CACHE FK constraints...")
        if _table_exists(c, "STACK_CACHE"):
            if not _constraint_exists(c, "FK_STACK_CACHE_STACK"):
                try:
                    c.execute(
                        "DELETE FROM stack_cache WHERE stack_id NOT IN (SELECT id FROM stacks)"
                    )
                    conn.commit()
                    c = conn.cursor()
                    c.execute("""
                        ALTER TABLE stack_cache ADD CONSTRAINT fk_stack_cache_stack
                        FOREIGN KEY (stack_id) REFERENCES stacks(id) ON DELETE CASCADE
                    """)
                    conn.commit()
                    c = conn.cursor()
                except Exception as e:
                    logger.warning("Phase1 1.5e FK_STACK_CACHE_STACK: %s", e)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    c = conn.cursor()

            if not _constraint_exists(c, "FK_STACK_CACHE_REP_IMAGE"):
                try:
                    c.execute(
                        "UPDATE stack_cache SET rep_image_id = NULL WHERE rep_image_id IS NOT NULL AND rep_image_id NOT IN (SELECT id FROM images)"
                    )
                    conn.commit()
                    c = conn.cursor()
                    c.execute("""
                        ALTER TABLE stack_cache ADD CONSTRAINT fk_stack_cache_rep_image
                        FOREIGN KEY (rep_image_id) REFERENCES images(id) ON DELETE SET NULL
                    """)
                    conn.commit()
                    c = conn.cursor()
                except Exception as e:
                    logger.warning("Phase1 1.5e FK_STACK_CACHE_REP_IMAGE: %s", e)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    c = conn.cursor()

            if not _constraint_exists(c, "FK_STACK_CACHE_FOLDER"):
                try:
                    c.execute(
                        "UPDATE stack_cache SET folder_id = NULL WHERE folder_id IS NOT NULL AND folder_id NOT IN (SELECT id FROM folders)"
                    )
                    conn.commit()
                    c = conn.cursor()
                    c.execute("""
                        ALTER TABLE stack_cache ADD CONSTRAINT fk_stack_cache_folder
                        FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL
                    """)
                    conn.commit()
                    c = conn.cursor()
                except Exception as e:
                    logger.warning("Phase1 1.5e FK_STACK_CACHE_FOLDER: %s", e)
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    c = conn.cursor()

        try:
            n_folders = None
            n_stack_cache = None
            if _table_exists(c, "FOLDERS"):
                c.execute("SELECT COUNT(*) FROM folders")
                n_folders = c.fetchone()[0]
            if _table_exists(c, "STACK_CACHE"):
                c.execute("SELECT COUNT(*) FROM stack_cache")
                n_stack_cache = c.fetchone()[0]
            logger.info(
                "Phase1 after 1.5e row counts (for pause diagnosis): folders=%s stack_cache=%s",
                n_folders,
                n_stack_cache,
            )
        except Exception:
            pass

        # 1.5f: UQ_FOLDERS_PATH
        print("  [1.5f] Adding UQ_FOLDERS_PATH...")
        if not _index_exists(c, "UQ_FOLDERS_PATH"):
            try:
                # De-dup safety net
                c.execute("""
                    DELETE FROM folders WHERE id NOT IN (
                        SELECT MAX(id) FROM folders GROUP BY path
                    )
                    AND path IN (
                        SELECT path FROM folders GROUP BY path HAVING COUNT(*) > 1
                    )
                """)
                conn.commit()
                c = conn.cursor()
                c.execute("CREATE UNIQUE INDEX uq_folders_path ON folders(path)")
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.5f UQ_FOLDERS_PATH: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        # 1.7: Recompute statistics for Firebird query planner
        print("  [1.7] Recomputing index statistics...")
        for idx_name in (
            "UQ_IMAGES_FILE_PATH",
            "UQ_IMAGES_IMAGE_UUID",
            "IDX_IMAGES_FOLDER_SCORE",
            "IDX_IMAGES_STACK_SCORE",
            "IDX_FOLDER_ID",
            "IDX_STACK_ID",
            "UQ_FOLDERS_PATH",
        ):
            if _index_exists(c, idx_name):
                try:
                    c.execute(f"SET STATISTICS INDEX {idx_name}")
                    conn.commit()
                    c = conn.cursor()
                except Exception:
                    pass

        # 1.8: CHECK constraints for enum validation
        print("  [1.8] Adding CHECK constraints...")
        if not _constraint_exists(c, "CHK_IMAGES_LABEL"):
            try:
                c.execute("""
                    ALTER TABLE images ADD CONSTRAINT chk_images_label
                    CHECK (label IS NULL OR label IN ('Red','Yellow','Green','Blue','Purple','None',''))
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.8 CHK_IMAGES_LABEL: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        # CHK_IMAGES_CULL_DECISION: allow 'neutral','maybe' (used by selection/culling)
        if _constraint_exists(c, "CHK_IMAGES_CULL_DECISION"):
            try:
                c.execute("ALTER TABLE images DROP CONSTRAINT chk_images_cull_decision")
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase 1.8a DROP CHK_IMAGES_CULL_DECISION: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()
        if not _constraint_exists(c, "CHK_IMAGES_CULL_DECISION"):
            try:
                c.execute("""
                    ALTER TABLE images ADD CONSTRAINT chk_images_cull_decision
                    CHECK (cull_decision IS NULL OR cull_decision IN ('pick','reject','skip','neutral','maybe',''))
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.8 CHK_IMAGES_CULL_DECISION: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        if _table_exists(c, "IMAGE_PHASE_STATUS") and not _constraint_exists(
            c, "CHK_IPS_STATUS"
        ):
            try:
                c.execute("""
                    ALTER TABLE image_phase_status ADD CONSTRAINT chk_ips_status
                    CHECK (status IN ('not_started','pending','running','done','failed','skipped'))
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("Phase1 1.8 CHK_IPS_STATUS: %s", e)
                try:
                    conn.rollback()
                except Exception:
                    pass
                c = conn.cursor()

        print("[Phase 1] OK - Complete (integrity + index hardening).")
        logger.info("Phase 1 migration complete (integrity + index hardening).")
    except Exception as e:
        logger.error("Phase 1 migration error: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass

    return conn
