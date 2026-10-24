---
name: git-changelog
description: Git workflow, changelog conventions, and commit practices for the image-scoring project.
---

# Git & Changelog Conventions

This skill documents the project's version control workflow and changelog format.

## Changelog Format

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) with [Semantic Versioning](https://semver.org/).

### Structure

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- **Feature Name**: Description of new functionality.

### Changed
- **Component**: What changed and why.

### Fixed
- **Bug Name**: What was broken and how it was fixed.

### Removed
- **Item**: What was removed.
```

### Conventions
- **Bold feature names** at the start of each bullet.
- Group related items under a single bullet with sub-items.
- Reference relevant files and modules when helpful.
- Version bumps: Major = breaking changes, Minor = new features, Patch = fixes.
- Current version is in the 3.x range.

## Commit Messages

Use descriptive, imperative-mood commit messages:
```
Add selection tab with pick/reject workflow
Fix double-normalization in general score calculation
Update scoring weights to prioritize LIQE
```

## Workflow: Update Changelog & Commit

1. **Check current status**:
   ```
   git status
   git log -5
   ```

2. **Review changes** — understand what was modified.

3. **Update `CHANGELOG.md`**:
   - Add a new version section at the top (below the header).
   - Categorize changes under Added/Changed/Fixed/Removed.
   - Use today's date.

4. **Stage and commit**:
   ```
   git add -A
   git commit -m "Description of changes"
   ```

5. **Push**:
   ```
   git push
   ```

## Using the Git MCP Server

The `git` MCP server provides tools for common operations without shell commands:

| Tool | Purpose |
|------|---------|
| `git_status` | Show working tree status |
| `git_log` | Show recent commit history |
| `git_diff_unstaged` | See uncommitted changes |
| `git_diff_staged` | See staged changes |
| `git_add` | Stage files |
| `git_commit` | Create a commit |
| `git_branch` | List branches |
| `git_checkout` | Switch branches |

## Important Files

- `CHANGELOG.md` — Project changelog (1000+ lines of history)
- `SCORING_CHANGES.md` — Focused scoring formula change log
- `.gitignore` — Excludes `.venv`, `__pycache__`, `.FDB`, thumbnails, etc.
- `.gitattributes` — LFS config for large files
