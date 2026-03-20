# Workflow: Visual Analysis

Use when the user wants to find duplicates, identify similar images, flag outliers, or propagate tags using embedding-based AI analysis tools.

## Prerequisites

- WebUI must be running (these tools use stored MobileNetV2 embeddings)
- Images must have been indexed and scored so embeddings exist

## Tools Involved

| Tool | Purpose |
|------|---------|
| `find_near_duplicates` | Find visually similar pairs even when file hashes differ |
| `find_outliers` | Flag images that don't visually fit the folder |
| `search_similar_images` | Find images similar to a specific reference image |
| `propagate_tags` | Spread keywords from tagged images to untagged neighbors |
| `get_stacks_summary` | Review existing cluster groupings |

---

## Sub-Workflow A: Find Near-Duplicates

```
1. find_near_duplicates(folder_path=..., threshold=0.98, limit=50)
   → Returns pairs of near-identical images with similarity scores

2. Review pairs — decide which to keep/delete via the Electron UI
   or query_images to get their scores and ratings for comparison

3. If needed: execute_sql to inspect both images side by side
   SELECT id, file_path, score_general, rating, label
   FROM images WHERE id IN (?, ?)
```

**Threshold guidance:**
- `0.99+` — virtually identical (different export, slight resize)
- `0.97–0.99` — very close duplicates (minor crop, slight edit)
- `0.90–0.97` — similar compositions (burst shots, bracketing)

---

## Sub-Workflow B: Find Outliers

```
1. find_outliers(folder_path=..., z_threshold=2.0, limit=20)
   → Returns images with low mean similarity to their neighbors

2. Review flagged images — outliers may be:
   - Wrong folder (misplaced files)
   - Test shots / accidental captures
   - Genuinely unique standout images

3. Use get_image_details(file_path) to check metadata, score, label
```

**z_threshold guidance:**
- `2.0` (default) — moderate sensitivity, catches clear outliers
- `1.5` — more aggressive, flags borderline cases
- `3.0` — only extreme outliers

---

## Sub-Workflow C: Search Similar to a Reference

```
1. search_similar_images(example_path="D:/Photos/ref.jpg", folder_path=..., limit=20)
   → Returns images ranked by visual similarity to the reference

2. Use to:
   - Find all shots of the same subject/scene
   - Locate the best version of a similar composition
   - Find images to group into a stack
```

---

## Sub-Workflow D: Tag Propagation

```
1. Check how many images lack keywords:
   execute_sql("SELECT COUNT(*) FROM images WHERE keywords IS NULL
                AND folder_id = (SELECT id FROM folders WHERE path = ?)", [folder])

2. Preview propagation (always start with dry_run=True):
   propagate_tags(folder_path=..., dry_run=True, min_similarity=0.85)
   → Shows which tags would be assigned and with what confidence

3. Review the preview output — check if proposed tags make sense

4. Apply if results look good:
   propagate_tags(folder_path=..., dry_run=False, min_similarity=0.85)

5. Verify:
   execute_sql("SELECT COUNT(*) FROM images WHERE keywords IS NOT NULL
                AND folder_id = (SELECT id FROM folders WHERE path = ?)", [folder])
```

**Parameter guidance:**
- `k` — number of tagged neighbors to consult (default: 10)
- `min_similarity` — minimum cosine similarity to consider a neighbor (default: 0.8)
- `min_keyword_confidence` — minimum vote fraction for a tag to be applied (default: 0.3)

---

## Combined Analysis Workflow

For a full visual health check of a folder:

```
1. get_database_stats + get_folder_tree
   → Understand scope (how many images, are embeddings present?)

2. find_near_duplicates(folder_path=...)
   → Identify obvious duplicates to cull

3. find_outliers(folder_path=...)
   → Flag potentially misplaced or accidental images

4. propagate_tags(folder_path=..., dry_run=True)
   → Preview how many untagged images can have tags inferred

5. get_stacks_summary(folder_path=...)
   → Review existing cluster groupings for the folder
```

---

## Notes

- All these tools rely on MobileNetV2 embeddings stored during scoring — run scoring first if embeddings are missing.
- `propagate_tags` is always safe to preview with `dry_run=True` (the default).
- `find_outliers` returns nearest neighbors for each flagged image — useful context for deciding whether to keep or move them.
- For large folders, use the `limit` parameter to get a manageable result set before processing everything.
