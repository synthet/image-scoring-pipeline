"""Bounded metadata snapshots for shadow authority; no inference or writes."""


def load_inputs(tx, image_id, source_observation, inventory_hash):
    image = tx.query_one("SELECT id, bird_bbox FROM images WHERE id=? FOR SHARE", (image_id,))
    if image is None:
        return None
    run = tx.query_one(
        "SELECT id,image_id,detector_key,detector_version,detector_config_hash,source_hash,"
        "source_hash_version,rendition_hash,rendition_version,coord_space,is_current,status "
        "FROM image_localization_runs WHERE image_id=? AND detector_key='bird' AND is_current",
        (image_id,),
    )
    if run is None:
        return None
    regions = tx.query(
        "SELECT id,localization_run_id,object_class,rank,confidence,x1,y1,x2,y2 "
        "FROM image_regions WHERE localization_run_id=? ORDER BY id", (run["id"],),
    )
    selection = tx.query_one(
        "SELECT id,localization_run_id,region_id,selected_by,projected_bird_bbox "
        "FROM image_localization_selections WHERE image_id=? AND detector_key='bird' AND revoked_at IS NULL",
        (image_id,),
    )
    keywords = tx.query(
        "SELECT kd.keyword_norm,ik.source FROM image_keywords ik "
        "JOIN keywords_dim kd ON kd.keyword_id=ik.keyword_id "
        "WHERE ik.image_id=? AND (kd.keyword_norm LIKE 'bird%' OR kd.keyword_norm LIKE 'species:%') "
        "ORDER BY kd.keyword_norm,ik.source", (image_id,),
    )
    discovery = [row for row in keywords if row["keyword_norm"].startswith("bird")]
    species = [row for row in keywords if row["keyword_norm"].startswith("species:")]
    reservations = tx.query(
        "SELECT inventory_sha256,original_run_id,original_region_id "
        "FROM localization_authority_reservations WHERE image_id=? ORDER BY inventory_sha256", (image_id,),
    )
    changes = tx.query(
        "SELECT kind,MAX(id) AS revision FROM localization_change_journal WHERE image_id=? GROUP BY kind",
        (image_id,),
    )
    revisions = {row["kind"]: row["revision"] for row in changes}
    return {
        "run": run, "regions": regions,
        "population": {"bird_tagged": bool(discovery), "has_active_selection": selection is not None},
        "components": {
            "authority": {"selection": selection, "projection": image["bird_bbox"], "run_id": run["id"],
                          "writer_revision": revisions.get("authority", 0)},
            # Observations are not eligibility or ownership grants. Legacy and
            # ambiguous outputs stay protected until the active lifecycle exists.
            "discovery": {"observed_keywords": discovery, "writer_revision": revisions.get("discovery", 0)},
            "ownership": {"observed_species": species, "outputs_protected": True,
                          "writer_revision": max(revisions.get("keyword", 0), revisions.get("embedding", 0))},
            "source": source_observation or {"status": "not_observed"},
            "reservation": {"inventory_hash": inventory_hash, "images": reservations},
        },
    }
