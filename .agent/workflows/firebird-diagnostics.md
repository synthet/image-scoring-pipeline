---
description: Perform comprehensive database diagnostics using mcp-firebird.
---

# Firebird Database Diagnostics Workflow

Use this workflow to check the health and performance of the Firebird database.

## Steps

1. **System Health Check**
   - Run `system-health-check` to verify the MCP server and database connection.

2. **Database Integrity**
   - Run `validate-database`.
   - Run `get-database-info` to check table counts and connection state.

3. **Schema Overview**
   - Run `list-tables`.
   - For critical tables (`IMAGES`, `FILE_PATHS`), run `describe-table`.

4. **Performance Stats**
   - Run `analyze-table-statistics` for the largest tables.
   - Example: `analyze-table-statistics(tableName="IMAGES")`.

5. **Generate Report**
   - Compile results into a markdown document.
