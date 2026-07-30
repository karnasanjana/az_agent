# SchemaViz v2.0 — Technical Specification

## Overview

Extend SchemaViz to support **Google BigQuery** alongside SQL Server, with **multi-database/dataset selection**, **color-coded diagrams**, and **manual relationship management**.

---

## User Flow

### Home Page — Database Type Selection

```
┌──────────────────────────────────────────────────────────┐
│                    SchemaViz                              │
│          Choose your database platform                   │
│                                                          │
│   ┌─────────────────────┐  ┌─────────────────────┐      │
│   │   🗄️ SQL Server     │  │   📊 BigQuery        │      │
│   │                     │  │                     │      │
│   │  Azure SQL, MSSQL   │  │  Google Cloud       │      │
│   │  On-premise         │  │  Platform           │      │
│   └─────────────────────┘  └─────────────────────┘      │
└──────────────────────────────────────────────────────────┘
```

### SQL Server Flow

```
Step 1: Enter credentials (Host, Port, Username, Password)
Step 2: Click "Connect" → We query sys.databases → Show database cards
Step 3: User selects one or more databases from cards (each shows table count)
Step 4: Click "Extract" → Extract all selected databases
Step 5: View Diagram — tables color-coded by database
```

### BigQuery Flow

```
Step 1: User is already signed in with Google (Auth.js)
Step 2: Enter Project ID → Click "Connect"
Step 3: We fetch all datasets → Show dataset cards (each shows table count)
Step 4: User selects one or more datasets
Step 5: Click "Extract" → Extract all selected datasets
Step 6: View Diagram — tables color-coded by dataset
```

---

## Database Selection UI

### Cards with Table Counts

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ 🔵 fabrics       │  │ 🟢 analytics     │  │ 🟠 staging       │
│                  │  │                  │  │                  │
│ 4 tables         │  │ 12 tables        │  │ 8 tables         │
│                  │  │                  │  │                  │
│ [ ✓ Selected ]   │  │ [   Select   ]   │  │ [   Select   ]   │
└──────────────────┘  └──────────────────┘  └──────────────────┘

                    2 databases selected (16 tables)
          ┌─────────────────────────────────────────┐
          │           Extract Schema →               │
          └─────────────────────────────────────────┘
```

### Large Selection Warning

When total tables across selected databases exceed 100:

```
┌─────────────────────────────────────────────────────┐
│  ⚠️  Large Selection                                │
│                                                     │
│  You selected 5 databases with 247 tables total.    │
│  This may take a while and the diagram may be       │
│  complex to navigate.                               │
│                                                     │
│  [ Cancel ]                [ Continue Anyway ]      │
└─────────────────────────────────────────────────────┘
```

---

## Color-Coded Diagram

Each database/dataset gets a distinct color applied to its table nodes:

```
Database Colors:
  Database 1 → Blue (#3B82F6)
  Database 2 → Green (#10B981)
  Database 3 → Amber (#F59E0B)
  Database 4 → Purple (#8B5CF6)
  Database 5 → Pink (#EC4899)
  Database 6 → Cyan (#06B6D4)
```

### Table Node Design (Multi-Database)

```
┌──────────────────────────────┐
│ 🔵 fabrics                   │  ← Database badge with color
├──────────────────────────────┤
│        conversations         │  ← Table name
├──────────────────────────────┤
│ 🔑 conversation_id  varchar │
│    user_id           varchar │
│    status            varchar │
│    created_at        datetime│
└──────────────────────────────┘
```

The top bar / badge shows the database name with its assigned color.

---

## Manual Relationship Management

### Add Relationship Panel

A collapsible panel on the diagram page:

```
┌─────────────────────────────────────────────────────┐
│  + Add Relationship                                  │
│                                                     │
│  Source Table:    [ conversation_messages    ▼ ]     │
│  Source Column:   [ conversation_id         ▼ ]     │
│                                                     │
│          ───────────  links to  ───────────          │
│                                                     │
│  Target Table:    [ conversations           ▼ ]     │
│  Target Column:   [ conversation_id         ▼ ]     │
│                                                     │
│  [ Cancel ]                    [ Add Relationship ] │
└─────────────────────────────────────────────────────┘
```

- Dropdowns are populated from all tables/columns across all selected databases
- Tables show database prefix: `fabrics.conversations`, `analytics.events`
- Source column dropdown updates when source table changes
- Adding creates a dashed edge immediately on the canvas

### Visual Distinction

| Type | Line Style | Color | Deletable |
|------|-----------|-------|-----------|
| Auto-detected FK | Solid line | Color from FK palette | No (read-only) |
| Manual relationship | Dashed line | Gray (#6B7280) | Yes (click to delete) |

### Delete Manual Relationship

- Click on a dashed edge → Shows delete button/tooltip
- Or right-click → "Remove Relationship"
- Only manual relationships can be deleted, auto-detected FKs are read-only

---

## Backend Changes

### New Dependencies

```
# backend/requirements.txt (additions)
google-cloud-bigquery>=3.25.0
google-auth>=2.30.0
```

### New API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/connection/databases` | List databases on a SQL Server instance |
| `POST` | `/api/bigquery/datasets` | List datasets in a BigQuery project |
| `POST` | `/api/bigquery/start` | Start BigQuery schema extraction |
| `GET`  | `/api/bigquery/stream/{id}` | SSE stream for BigQuery extraction |

### SQL Server — List Databases

```python
# New endpoint: POST /api/connection/databases
# Input: { host, port, username, password }
# Query: SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name
# For each database: SELECT COUNT(*) FROM sys.tables WHERE type='U' AND is_ms_shipped=0
# Returns: [{ name: "fabrics", table_count: 4 }, { name: "master_data", table_count: 12 }]
```

### BigQuery — List Datasets

```python
# New endpoint: POST /api/bigquery/datasets
# Input: { project_id, oauth_token }
# Uses: google.cloud.bigquery.Client with user OAuth credentials
# For each dataset: count tables via list_tables()
# Returns: [{ name: "orthosouth_clinical", table_count: 19 }, ...]
```

### BigQuery Schema Extractor

```python
class BigQuerySchemaExtractor:
    """Extract schema from BigQuery dataset(s).

    Uses INFORMATION_SCHEMA views:
    - INFORMATION_SCHEMA.TABLES → table list
    - INFORMATION_SCHEMA.COLUMNS → column metadata
    - INFORMATION_SCHEMA.TABLE_CONSTRAINTS → any existing constraints
    - INFORMATION_SCHEMA.KEY_COLUMN_USAGE → constraint columns
    """

    def __init__(self, project_id: str, datasets: list[str], oauth_token: str):
        # Create BigQuery client with user OAuth credentials
        pass

    async def extract_with_progress(self) -> AsyncGenerator[ExtractionProgress, None]:
        # Same progress pattern as SQL Server extractor
        # Iterates through each selected dataset
        pass

    def get_result(self) -> DatabaseSchema:
        # Returns combined schema from all selected datasets
        pass
```

### Multi-Database SQL Server Extraction

```python
# Enhanced: extract from multiple databases in one session
# Input: { host, port, username, password, databases: ["fabrics", "analytics"] }
# Extracts each database sequentially, combines into single DatabaseSchema
# Each table's schema_name becomes: "database_name.schema_name"
# e.g., "fabrics.dbo" instead of just "dbo"
```

---

## Frontend Changes

### Auth.js — Add BigQuery Scope

```typescript
// frontend/src/lib/auth.ts
export const authConfig = {
  providers: [
    Google({
      authorization: {
        params: {
          scope: "openid email profile https://www.googleapis.com/auth/bigquery.readonly",
          access_type: "offline",
          prompt: "consent",
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      // Store access_token for BigQuery API calls
      if (account) {
        token.accessToken = account.access_token
      }
      return token
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken
      return session
    },
  },
}
```

### New Components

| Component | Purpose |
|-----------|---------|
| `DatabaseTypeSelector` | Home page cards: SQL Server / BigQuery |
| `BigQueryForm` | Project ID input + connect button |
| `DatabasePicker` | Cards grid showing databases/datasets with table counts |
| `ManualRelationshipPanel` | Dropdown form to add manual FK relationships |
| `ManualEdge` | Custom React Flow edge with dashed style + delete button |

### Updated Types

```typescript
// frontend/src/types/schema.ts (additions)

export interface DatabaseInfo {
  name: string
  table_count: number
}

export interface ManualRelationship {
  id: string
  source_database: string
  source_table: string
  source_column: string
  target_database: string
  target_table: string
  target_column: string
}

// Updated DatabaseSchema to support multi-database
export interface DatabaseSchema {
  database_name: string           // Primary name or comma-separated
  databases: string[]             // All selected database/dataset names
  tables: Table[]                 // Tables from all selected databases
  foreign_keys: ForeignKey[]      // Auto-detected FKs
  manual_relationships: ManualRelationship[]  // User-added relationships
  extraction_time_seconds: number
  table_count: number
  standalone_table_count: number
}
```

### Updated Table Node

```typescript
// Table node data includes database source for color-coding
export interface TableNodeData extends Table {
  fkColumns: Set<string>
  database_source: string      // Which database this table belongs to
  database_color: string       // Assigned color for this database
}
```

---

## Data Persistence

### Save Diagram (Updated)

```json
{
  "schema": { /* DatabaseSchema with all databases */ },
  "positions": { "fabrics.dbo.conversations": { "x": 100, "y": 200 } },
  "manual_relationships": [
    {
      "id": "mr-1",
      "source_database": "fabrics",
      "source_table": "dbo.jobs",
      "source_column": "patient_id",
      "target_database": "orthosouth_clinical",
      "target_table": "patients",
      "target_column": "Id"
    }
  ],
  "viewport": { "x": 0, "y": 0, "zoom": 1 },
  "database_type": "bigquery",
  "database_colors": {
    "fabrics": "#3B82F6",
    "orthosouth_clinical": "#10B981"
  }
}
```

---

## Implementation Phases

### Phase 1 — Multi-Database SQL Server
1. New endpoint to list databases on a server
2. Database picker cards UI
3. Multi-database extraction (combine schemas)
4. Color-coded table nodes by database
5. Large selection warning

### Phase 2 — BigQuery Support
1. Auth.js BigQuery scope + access token storage
2. BigQuery connection form (Project ID)
3. Dataset listing endpoint + dataset picker cards
4. BigQuery schema extractor (INFORMATION_SCHEMA queries)
5. SSE streaming for BigQuery extraction

### Phase 3 — Manual Relationships
1. Add Relationship panel with dropdowns
2. Manual dashed edge component
3. Delete manual relationship (click edge)
4. Persist manual relationships in save/load
5. Cross-database relationships support

### Phase 4 — Home Page Redesign
1. Database type selector (SQL Server / BigQuery cards)
2. Conditional form rendering
3. Updated step indicator for new flow
4. Updated extract page for multi-database

---

## Test Plan

| Test | Expected Result |
|------|-----------------|
| SQL Server → List databases on `microfabrics.database.windows.net` | Shows `fabrics` with 4 tables |
| BigQuery → List datasets in `project-zion-454116` | Shows 26 datasets with table counts |
| Select 2 BigQuery datasets → Extract | Combined diagram with color-coded tables |
| Add manual relationship between two tables | Dashed edge appears immediately |
| Delete manual relationship | Edge removed from canvas |
| Save diagram with manual relationships → Reload | Manual relationships restored as dashed edges |
| Select 200+ tables → Warning shown | Warning dialog appears with continue/cancel |
| Cross-database manual relationship | Can link tables from different databases |
