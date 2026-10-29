"""Active lifecycle metadata and append-only invalidation; identical to migration 0046."""

LIFECYCLE_SCHEMA_SQL = """
ALTER TABLE localization_authority_control
    DROP CONSTRAINT IF EXISTS localization_authority_control_mode_check;
ALTER TABLE localization_authority_control
    ADD CONSTRAINT localization_authority_control_mode_check CHECK (mode IN ('off','shadow','active'));
ALTER TABLE localization_authority_control
    ADD COLUMN IF NOT EXISTS selection_freshness_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE localization_authority_policies
    ADD COLUMN IF NOT EXISTS rule_kind TEXT NOT NULL DEFAULT 'r2';
CREATE TABLE IF NOT EXISTS localization_policy_approvals (
    policy_hash TEXT PRIMARY KEY REFERENCES localization_authority_policies(policy_hash),
    revision BIGINT NOT NULL CHECK (revision > 0),
    active BOOLEAN NOT NULL DEFAULT FALSE,
    geometry_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    species_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    qualification_sha256 TEXT NOT NULL,
    receipt JSONB NOT NULL,
    approved_by TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS localization_policy_events (
    id BIGSERIAL PRIMARY KEY,
    policy_hash TEXT NOT NULL REFERENCES localization_authority_policies(policy_hash),
    revision BIGINT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('approve','revoke')),
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (policy_hash,revision)
);
CREATE TABLE IF NOT EXISTS localization_discovery_state (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    legacy_positive BOOLEAN NOT NULL,
    selection_only BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS localization_change_journal (
    id BIGSERIAL PRIMARY KEY,
    image_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    owner_context TEXT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS ix_localization_journal_resource
    ON localization_change_journal (image_id,kind,resource_key,id DESC);
ALTER TABLE localization_change_journal DROP CONSTRAINT IF EXISTS localization_change_journal_image_id_fkey;
CREATE TABLE IF NOT EXISTS localization_selection_lineage (
    selection_id BIGINT PRIMARY KEY REFERENCES image_localization_selections(id) ON DELETE CASCADE,
    policy_hash TEXT NOT NULL REFERENCES localization_authority_policies(policy_hash),
    approval_revision BIGINT NOT NULL,
    baseline_bird_bbox JSONB,
    source_hash TEXT NOT NULL,
    source_hash_version TEXT NOT NULL,
    rendition_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE OR REPLACE FUNCTION localization_record_change() RETURNS trigger
LANGUAGE plpgsql AS $journal$
DECLARE
    value JSONB;
    prior JSONB;
    iid INTEGER;
    category TEXT := TG_ARGV[0];
    resource TEXT;
    keyword TEXT;
BEGIN
    value := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    prior := CASE WHEN TG_OP='UPDATE' THEN to_jsonb(OLD) ELSE NULL END;
    iid := CASE WHEN TG_TABLE_NAME='images' THEN (value->>'id')::integer ELSE (value->>'image_id')::integer END;
    IF NOT EXISTS (SELECT 1 FROM images WHERE id=iid) THEN
        RETURN NULL;
    END IF;
    IF TG_TABLE_NAME='images' AND TG_OP='UPDATE' AND prior->>'file_path' IS DISTINCT FROM value->>'file_path' THEN
        UPDATE localization_authority_observations
        SET components=jsonb_set(components,'{source}','{"status":"not_observed"}'::jsonb),
            revision=revision+1,source_revision=source_revision+1,updated_at=clock_timestamp()
        WHERE image_id=iid;
    END IF;
    resource := COALESCE(value->>'keyword_id',value->>'embedding_space_id',value->>'id','image');
    IF TG_TABLE_NAME='image_keywords' THEN
        SELECT keyword_norm INTO keyword FROM keywords_dim WHERE keyword_id=(value->>'keyword_id')::integer;
        IF keyword NOT LIKE 'bird%' AND keyword NOT LIKE 'species:%' THEN RETURN NULL; END IF;
        value := jsonb_build_object('keyword_norm',keyword,'source',value->'source','operation',TG_OP);
        category := CASE WHEN keyword LIKE 'bird%' THEN 'discovery' ELSE 'keyword' END;
    ELSIF TG_TABLE_NAME LIKE 'image_embeddings%' THEN
        IF NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE id=(value->>'embedding_space_id')::integer
                       AND code IN ('bioclip_2_image','bioclip_2_crop')) THEN RETURN NULL; END IF;
        value := jsonb_build_object('space_id',value->'embedding_space_id','operation',TG_OP);
    ELSE
        value := jsonb_build_object('operation',TG_OP,'table',TG_TABLE_NAME);
    END IF;
    INSERT INTO localization_change_journal (image_id,kind,resource_key,owner_context,payload)
    VALUES (iid,category,resource,NULLIF(current_setting('vexlum.authority_publication',true),''),value);
    RETURN NULL;
END;
$journal$;
CREATE OR REPLACE TRIGGER trg_localization_image_change AFTER UPDATE OF bird_bbox,file_path ON images
    FOR EACH ROW EXECUTE FUNCTION localization_record_change('authority');
CREATE OR REPLACE TRIGGER trg_localization_selection_change
    AFTER INSERT OR UPDATE OR DELETE ON image_localization_selections
    FOR EACH ROW EXECUTE FUNCTION localization_record_change('authority');
CREATE OR REPLACE TRIGGER trg_localization_keyword_change
    AFTER INSERT OR UPDATE OR DELETE ON image_keywords
    FOR EACH ROW EXECUTE FUNCTION localization_record_change('keyword');
CREATE OR REPLACE TRIGGER trg_localization_embedding_change
    AFTER INSERT OR UPDATE OR DELETE ON image_embeddings
    FOR EACH ROW EXECUTE FUNCTION localization_record_change('embedding');
CREATE OR REPLACE TRIGGER trg_localization_embedding_change
    AFTER INSERT OR UPDATE OR DELETE ON image_embeddings_512
    FOR EACH ROW EXECUTE FUNCTION localization_record_change('embedding');
CREATE OR REPLACE TRIGGER trg_localization_embedding_change
    AFTER INSERT OR UPDATE OR DELETE ON image_embeddings_768
    FOR EACH ROW EXECUTE FUNCTION localization_record_change('embedding');
CREATE OR REPLACE FUNCTION localization_selection_is_fresh(sid BIGINT) RETURNS BOOLEAN
LANGUAGE sql STABLE AS $fresh$
SELECT COALESCE((
    SELECT CASE
        WHEN NOT ctl.selection_freshness_enabled THEN TRUE
        WHEN s.revoked_at IS NOT NULL OR r.status<>'detected' OR r.coord_space<>'display_normalized' THEN FALSE
        WHEN l.selection_id IS NOT NULL AND
             (a.active IS NOT TRUE OR NOT a.geometry_allowed OR a.revision<>l.approval_revision) THEN FALSE
        WHEN l.selection_id IS NOT NULL AND COALESCE(o.components->'source'->>'status','')<>'available' THEN FALSE
        WHEN l.selection_id IS NOT NULL AND
             (l.source_hash IS DISTINCT FROM r.source_hash OR l.source_hash_version IS DISTINCT FROM r.source_hash_version
              OR l.rendition_hash IS DISTINCT FROM r.rendition_hash) THEN FALSE
        WHEN o.components->'source'->>'status'='available' AND r.source_hash IS NOT NULL AND
             (r.source_hash IS DISTINCT FROM o.components->'source'->>'hash'
              OR r.source_hash_version IS DISTINCT FROM o.components->'source'->>'version') THEN FALSE
        WHEN current_run.source_hash IS NOT NULL AND r.source_hash IS NOT NULL AND
             (current_run.source_hash IS DISTINCT FROM r.source_hash
              OR current_run.source_hash_version IS DISTINCT FROM r.source_hash_version) THEN FALSE
        WHEN current_run.rendition_hash IS NOT NULL AND r.rendition_hash IS NOT NULL AND
             current_run.rendition_hash<>r.rendition_hash THEN FALSE
        ELSE TRUE END
    FROM image_localization_selections s
    JOIN image_localization_runs r ON r.id=s.localization_run_id AND r.image_id=s.image_id
    CROSS JOIN localization_authority_control ctl
    LEFT JOIN localization_selection_lineage l ON l.selection_id=s.id
    LEFT JOIN localization_policy_approvals a ON a.policy_hash=l.policy_hash
    LEFT JOIN localization_authority_observations o ON o.image_id=s.image_id
    LEFT JOIN image_localization_runs current_run ON current_run.image_id=s.image_id
         AND current_run.detector_key=s.detector_key AND current_run.is_current
    WHERE s.id=sid AND ctl.id=1
), FALSE);
$fresh$;
CREATE OR REPLACE VIEW image_bird_bbox_compat AS
SELECT i.id AS image_id,
       CASE WHEN s.id IS NOT NULL THEN
           CASE WHEN NOT localization_selection_is_fresh(s.id) THEN NULL
                WHEN r.id IS NOT NULL AND selected_run.display_width>0 AND selected_run.display_height>0
                THEN s.projected_bird_bbox ELSE i.bird_bbox END
       ELSE CASE WHEN ctl.selection_freshness_enabled AND EXISTS (
           SELECT 1 FROM image_localization_selections old
           JOIN localization_selection_lineage old_l ON old_l.selection_id=old.id
           WHERE old.image_id=i.id AND old.projected_bird_bbox=i.bird_bbox
             AND NOT localization_selection_is_fresh(old.id)
             AND (SELECT owner_context FROM localization_change_journal j
                  WHERE j.image_id=i.id AND j.kind='authority' AND j.payload->>'table'='images'
                  ORDER BY j.id DESC LIMIT 1) IS NOT NULL
       ) THEN NULL ELSE COALESCE(NULLIF(imported.legacy_payload,'null'::jsonb),i.bird_bbox) END
       END AS bird_bbox
FROM images i
CROSS JOIN localization_authority_control ctl
LEFT JOIN image_localization_selections s ON s.image_id=i.id AND s.detector_key='bird' AND s.revoked_at IS NULL
LEFT JOIN image_regions r ON r.id=s.region_id AND r.localization_run_id=s.localization_run_id
LEFT JOIN image_localization_runs selected_run ON selected_run.id=s.localization_run_id
    AND selected_run.image_id=s.image_id AND selected_run.detector_key=s.detector_key
LEFT JOIN image_localization_runs imported ON imported.image_id=i.id AND imported.detector_key='bird'
    AND imported.is_current AND imported.legacy_payload IS NOT NULL
WHERE ctl.id=1;
"""


def initialize_lifecycle_schema(cur):
    cur.execute(LIFECYCLE_SCHEMA_SQL)
