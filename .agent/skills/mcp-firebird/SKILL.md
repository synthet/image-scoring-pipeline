---
name: mcp-firebird
description: Documentation for mcp-firebird tools and database interaction patterns.
---

# mcp-firebird Skill

This skill provides documentation and patterns for using the `mcp-firebird` server to interact with the project's Firebird database.

## Essential Tools

### Database Insight
- `list-tables`: Quick overview of all tables.
- `describe-table`: Get schema/columns for a specific table.
- `get-database-info`: Connection and database statistics.

### Performance & Health
- `system-health-check`: Verify connectivity and server state.
- `validate-database`: Check database integrity.
- `analyze-query-performance`: Benchmark SQL queries.
- `get-execution-plan`: Optimize complex queries.

### Data Access
- `execute-query`: Run SELECT statements (uses FIRST/ROWS for pagination).
- `get-table-data`: High-level data retrieval with filtering.
- `execute-batch-queries`: Run multiple queries in parallel.

## Common Query Patterns

### Paginating Results
Firebird uses `FIRST` and `SKIP` instead of `LIMIT` and `OFFSET`.
```sql
SELECT FIRST 10 SKIP 20 * FROM IMAGES ORDER BY CREATED_AT DESC
```

### Checking Image Scores
```sql
SELECT FIRST 5 * FROM IMAGES i 
JOIN FILE_PATHS fp ON i.ID = fp.IMAGE_ID 
ORDER BY i.SCORE_GENERAL DESC
```

## Maintenance Workflows
1. **Health Audit**: `system-health-check` -> `validate-database` -> `get-database-info`.
2. **Performance Audit**: `analyze-table-statistics` -> `get-execution-plan`.
