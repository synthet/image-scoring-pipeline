"""Add species provenance, transactional work and protected read models."""
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

SPECIES_SCHEMA_SQL = """
ALTER TABLE localization_authority_control
    ADD COLUMN IF NOT EXISTS species_baseline_initialized BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE localization_authority_control
    ADD COLUMN IF NOT EXISTS species_scan_cursor BIGINT NOT NULL DEFAULT 0;
ALTER TABLE localization_authority_control
    ADD COLUMN IF NOT EXISTS species_scan_upper_bound BIGINT NOT NULL DEFAULT 0;
ALTER TABLE localization_discovery_state
    ADD COLUMN IF NOT EXISTS species_managed BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS localization_discovery_evidence (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    keyword_id INTEGER NOT NULL REFERENCES keywords_dim(keyword_id),
    independent BOOLEAN NOT NULL,
    origin TEXT NOT NULL,
    event_id BIGINT,
    PRIMARY KEY (image_id,keyword_id)
);
CREATE TABLE IF NOT EXISTS localization_species_work (
    id BIGSERIAL PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    input_fingerprint TEXT NOT NULL,
    input_state JSONB NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('classify','fallback','cleanup','preserve','out_of_scope')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed')),
    fencing_token BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    disposition TEXT,
    last_error TEXT,
    completed_at TIMESTAMPTZ,
    UNIQUE (image_id,input_fingerprint)
);
CREATE INDEX IF NOT EXISTS ix_localization_species_claim
    ON localization_species_work (available_at,id) WHERE status<>'completed';
CREATE INDEX IF NOT EXISTS ix_localization_species_image
    ON localization_species_work (image_id,id DESC);
CREATE TABLE IF NOT EXISTS localization_species_outputs (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('keyword','embedding')),
    resource_key TEXT NOT NULL,
    work_id BIGINT NOT NULL REFERENCES localization_species_work(id),
    produced_event_id BIGINT NOT NULL,
    value_fingerprint TEXT NOT NULL,
    PRIMARY KEY (image_id,kind,resource_key)
);
INSERT INTO localization_discovery_evidence (image_id,keyword_id,independent,origin)
SELECT ik.image_id,ik.keyword_id,TRUE,'legacy' FROM image_keywords ik
JOIN keywords_dim kd ON kd.keyword_id=ik.keyword_id
CROSS JOIN localization_authority_control ctl
WHERE ctl.id=1 AND NOT ctl.species_baseline_initialized AND kd.keyword_norm LIKE '%birds%'
ON CONFLICT DO NOTHING;
INSERT INTO localization_discovery_state (image_id,legacy_positive,selection_only)
SELECT DISTINCT image_id,TRUE,FALSE FROM localization_discovery_evidence
WHERE origin='legacy' ON CONFLICT DO NOTHING;
UPDATE localization_authority_control SET species_baseline_initialized=TRUE WHERE id=1;
CREATE OR REPLACE FUNCTION localization_record_discovery() RETURNS trigger
LANGUAGE plpgsql AS $discovery$
DECLARE value JSONB; norm TEXT; iid INTEGER; kid INTEGER; context TEXT;
BEGIN
    value := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    iid := (value->>'image_id')::integer; kid := (value->>'keyword_id')::integer;
    IF NOT EXISTS (SELECT 1 FROM images WHERE id=iid) THEN RETURN NULL; END IF;
    SELECT keyword_norm INTO norm FROM keywords_dim WHERE keyword_id=kid;
    IF norm NOT LIKE '%birds%' THEN RETURN NULL; END IF;
    IF TG_OP='DELETE' THEN
        DELETE FROM localization_discovery_evidence WHERE image_id=iid AND keyword_id=kid;
    ELSE
        context := COALESCE(current_setting('vexlum.authority_publication',true),'');
        INSERT INTO localization_discovery_evidence (image_id,keyword_id,independent,origin,event_id)
        VALUES (iid,kid,context NOT LIKE 'species:%',
                CASE WHEN context LIKE 'species:%' THEN 'species_compatibility' ELSE 'external' END,
                (SELECT MAX(id) FROM localization_change_journal WHERE image_id=iid
                 AND kind='discovery' AND resource_key=kid::text))
        ON CONFLICT (image_id,keyword_id) DO UPDATE SET independent=EXCLUDED.independent,
            origin=EXCLUDED.origin,event_id=EXCLUDED.event_id;
    END IF;
    RETURN NULL;
END;
$discovery$;
CREATE OR REPLACE TRIGGER trg_localization_z_discovery_evidence
    AFTER INSERT OR UPDATE OR DELETE ON image_keywords
    FOR EACH ROW EXECUTE FUNCTION localization_record_discovery();
CREATE OR REPLACE FUNCTION localization_species_owns(iid INTEGER,kind TEXT,resource TEXT)
RETURNS BOOLEAN LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $owns$
SELECT EXISTS (
    SELECT 1 FROM localization_species_outputs out
    JOIN localization_change_journal event ON event.id=out.produced_event_id
    WHERE out.image_id=iid AND out.kind=$2 AND out.resource_key=resource
      AND event.owner_context='species:'||out.work_id::text
      AND event.id=(SELECT MAX(j.id) FROM localization_change_journal j
                    WHERE j.image_id=iid AND j.resource_key=resource
                    AND (j.kind=$2 OR ($2='keyword' AND j.kind='discovery')))
);
$owns$;
CREATE OR REPLACE FUNCTION localization_selection_species_allowed(sid BIGINT)
RETURNS BOOLEAN LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $species_allowed$
SELECT COALESCE((
    SELECT localization_selection_is_fresh(s.id)
       AND (g.x2::numeric-g.x1::numeric)*(g.y2::numeric-g.y1::numeric)>=0.005
       AND (l.selection_id IS NULL OR
            (a.active AND a.species_allowed AND a.revision=l.approval_revision
             AND a.receipt->'species_bands' ?
                 CASE WHEN (g.x2-g.x1)*(g.y2-g.y1)<0.02 THEN 'medium' ELSE 'large' END))
    FROM image_localization_selections s JOIN image_regions g ON g.id=s.region_id
    LEFT JOIN localization_selection_lineage l ON l.selection_id=s.id
    LEFT JOIN localization_policy_approvals a ON a.policy_hash=l.policy_hash
    WHERE s.id=sid AND s.revoked_at IS NULL
),FALSE);
$species_allowed$;
CREATE OR REPLACE FUNCTION localization_species_input(iid INTEGER)
RETURNS JSONB LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $input$
WITH evidence AS (
    SELECT EXISTS(SELECT 1 FROM localization_discovery_evidence d WHERE d.image_id=iid AND d.independent) AS independent
), selected AS (
    SELECT s.id,s.region_id,s.localization_run_id,l.policy_hash,l.approval_revision,
           jsonb_build_array(g.x1,g.y1,g.x2,g.y2) AS region,
           r.source_hash,r.source_hash_version,r.rendition_hash
    FROM image_localization_selections s JOIN image_regions g ON g.id=s.region_id
    JOIN image_localization_runs r ON r.id=s.localization_run_id
    LEFT JOIN localization_selection_lineage l ON l.selection_id=s.id
    CROSS JOIN evidence e
    WHERE s.image_id=iid AND s.detector_key='bird' AND s.revoked_at IS NULL
      AND localization_selection_species_allowed(s.id) AND (l.selection_id IS NOT NULL OR e.independent)
), revisions AS (
    SELECT COALESCE(MAX(id) FILTER (WHERE kind='authority'),0) AS authority,
           COALESCE(MAX(id) FILTER (WHERE kind='discovery' AND COALESCE(owner_context,'') NOT LIKE 'species:%'),0) AS discovery,
           COALESCE(MAX(id) FILTER (WHERE kind IN ('keyword','embedding') AND COALESCE(owner_context,'') NOT LIKE 'species:%'),0) AS ownership
    FROM localization_change_journal WHERE image_id=iid
)
SELECT jsonb_build_object(
    'source',COALESCE(o.components->'source','{"status":"not_observed"}'::jsonb),
    'independent_discovery',e.independent,
    'selection',(SELECT to_jsonb(s) FROM selected s),
    'in_scope',e.independent OR EXISTS(SELECT 1 FROM selected),
    'authority_revision',v.authority,'discovery_revision',v.discovery,'ownership_revision',v.ownership,
    'managed',EXISTS(SELECT 1 FROM localization_selection_lineage l JOIN image_localization_selections s ON s.id=l.selection_id WHERE s.image_id=iid)
              OR EXISTS(SELECT 1 FROM localization_discovery_state d WHERE d.image_id=iid AND d.species_managed),
    'curated_species',EXISTS(SELECT 1 FROM image_keywords ik JOIN keywords_dim kd ON kd.keyword_id=ik.keyword_id
                            WHERE ik.image_id=iid AND kd.keyword_norm LIKE 'species:%'
                            AND NOT localization_species_owns(iid,'keyword',ik.keyword_id::text))
)
FROM images i CROSS JOIN evidence e CROSS JOIN revisions v
LEFT JOIN localization_authority_observations o ON o.image_id=i.id WHERE i.id=iid;
$input$;
CREATE OR REPLACE FUNCTION localization_species_in_scope(iid INTEGER)
RETURNS BOOLEAN LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $scope$
SELECT COALESCE((state->>'in_scope')::boolean AND
    (ctl.mode='active' OR NOT (state->>'managed')::boolean),FALSE)
FROM localization_authority_control ctl CROSS JOIN LATERAL (SELECT localization_species_input(iid) AS state) x
WHERE ctl.id=1;
$scope$;
CREATE OR REPLACE FUNCTION localization_species_has_disposition(iid INTEGER)
RETURNS BOOLEAN LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $disposition$
SELECT EXISTS(SELECT 1 FROM localization_species_work w WHERE w.image_id=iid AND w.status='completed'
              AND w.disposition<>'superseded' AND w.input_state->'semantic'=localization_species_input(iid));
$disposition$;
CREATE OR REPLACE FUNCTION localization_species_output_visible(iid INTEGER,kind TEXT,resource TEXT)
RETURNS BOOLEAN LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $visible$
SELECT CASE WHEN NOT ctl.selection_freshness_enabled OR NOT localization_species_owns(iid,$2,resource) THEN TRUE
       ELSE EXISTS(SELECT 1 FROM localization_species_outputs out JOIN localization_species_work w ON w.id=out.work_id
                   WHERE out.image_id=iid AND out.kind=$2 AND out.resource_key=resource AND w.status='completed'
                     AND w.disposition IN ('classified','no_species_match','classified_embedding_preserved')
                     AND w.input_state->'semantic'=localization_species_input(iid)
                     AND w.input_state->'semantic'->'source'->>'status'='available') END
FROM localization_authority_control ctl WHERE ctl.id=1;
$visible$;
CREATE OR REPLACE VIEW localization_visible_image_keywords AS
SELECT ik.* FROM image_keywords ik
WHERE localization_species_output_visible(ik.image_id,'keyword',ik.keyword_id::text);
CREATE OR REPLACE VIEW localization_visible_image_embeddings AS
SELECT e.* FROM image_embeddings e
WHERE localization_species_output_visible(e.image_id,'embedding',e.embedding_space_id::text);
CREATE OR REPLACE VIEW localization_visible_image_embeddings_512 AS
SELECT e.* FROM image_embeddings_512 e
WHERE localization_species_output_visible(e.image_id,'embedding',e.embedding_space_id::text);
CREATE OR REPLACE VIEW localization_visible_image_embeddings_768 AS
SELECT e.* FROM image_embeddings_768 e
WHERE localization_species_output_visible(e.image_id,'embedding',e.embedding_space_id::text);
"""

def upgrade():
    # exec_driver_sql passes an empty parameter mapping, so psycopg2 %-formats the
    # statement; escape the literal % in LIKE '%birds%' (#731).
    op.get_bind().exec_driver_sql(SPECIES_SCHEMA_SQL.replace("%", "%%"))

def downgrade():
    raise RuntimeError("species lineage requires a reviewed preservation migration")
