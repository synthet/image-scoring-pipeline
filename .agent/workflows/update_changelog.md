---
description: Update CHANGELOG.md with recent changes, commit, and push
---

// turbo-all

Follow the `git-changelog` skill (`d:\Projects\image-scoring\.agent\skills\git-changelog\SKILL.md`).

1. **Check status & recent history**:
   Use `git_status` and `git_log` (last 10) on `d:\Projects\image-scoring` to understand what changed.

2. **Review unstaged changes**:
   Use `git_diff_unstaged` to see the full diff. Read `CHANGELOG.md` to find the current version.

3. **Update `CHANGELOG.md`**:
   - Bump the version (major/minor/patch as appropriate).
   - Use today's date.
   - Categorize under **Added / Changed / Fixed / Removed**.
   - Bold feature names, reference files/modules where helpful.

4. **Stage all changes**:
   ```pwsh
   git -C "d:\Projects\image-scoring" add -A
   ```

5. **Commit with a descriptive message**:
   ```pwsh
   git -C "d:\Projects\image-scoring" commit -m "<summary of changes>"
   ```

6. **Push**:
   ```pwsh
   git -C "d:\Projects\image-scoring" push
   ```

7. **Verify**:
   Use `git_log` (last 1) to confirm the commit, and `git_status` to confirm a clean tree.
