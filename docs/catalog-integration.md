# Catalog integration (ER-Diagram ↔ az_agent)

The one seam between the two agents: **ER owns schema truth, az_agent consumes it.**
The engineer extracts + reviews a schema in the ER app; az_agent grounds the
pipeline against *that reviewed schema* instead of silently re-probing the source.

## How it works

```
ER app: connect → extract → review → SHARE diagram  ──►  share token = source_id
                                                          │
az_agent /plan:  grounding reads GET {ER_CATALOG_URL}/catalog/{source_id}
                 catalog hit  → ground from reviewed schema  (note: "from catalog v4")
                 catalog miss → live-probe the source        (note: "from PostgreSQL")
```

- **`source_id` is a diagram's share token.** No new auth/storage — reuses the
  ER app's existing no-auth `load_shared_diagram`.
- **Catalog-first, live-probe fallback.** Unset the env vars and az_agent behaves
  exactly as before. Fully opt-in, zero risk to existing runs.
- **Contract** = ER's `DatabaseSchema` JSON + `source_id` + `schema_version`
  (no new format). Version comes from the ER app's `schema_history`.

## Wiring (az_agent env)

```
ER_CATALOG_URL    = https://<er-backend-host>/api     # or a local dir of {source_id}.json for offline dev
CATALOG_SOURCE_ID = <share-token-from-ER-app>         # one connected source per run for now
CATALOG_DRIFT_CHECK = 1                                # optional: also live-probe + flag drift (adds one read)
```

## Runbook — prove one BRD end to end

1. **ER app:** connect a source (postgres/bigquery/dataverse), extract its schema,
   review it, and **Share** the diagram → copy the share token.
2. **Sanity-check the endpoint:**
   `curl https://<er-host>/api/catalog/<token>` → returns `{source_id, schema_version, tables, ...}`.
3. **az_agent:** set `ER_CATALOG_URL` + `CATALOG_SOURCE_ID=<token>`, run `/plan` on the BRD.
   The plan review should show **"Grounded source 'x' from catalog v4"**.
4. **Deploy + run** in Azure as usual. The schema that built the pipeline is the
   one the engineer reviewed in the ER diagram.

## Drift (opt-in, advisory)

With `CATALOG_DRIFT_CHECK=1`, a catalog-grounded source also gets a live read; any
material difference surfaces as a loud plan-review note
(`⚠️ SCHEMA DRIFT for 'orders': ... added/removed/type changed ...`). It does **not**
block deploy — the plan stays grounded on the reviewed catalog schema, and the note
tells the engineer to re-extract in the ER app if the source really changed.

## Code

- az_agent: `tools/catalog.py` (reader), `agent/grounding.py` (`_external_columns`
  catalog-first, `_schema_drift`). Tests: `tools/test_catalog.py`, `tests/test_catalog_drift.py`.
- ER: `app/api/catalog.py` (`GET /api/catalog/{source_id}`), `load_shared_diagram`
  now returns `schema_history`.

## Deferred (post-demo)

- Multi-source per run (currently one `CATALOG_SOURCE_ID`).
- Dataverse grounds in a separate loop — catalog-first not yet wired there (~3 lines).
- ER `catalog_payload` has no unit test in the ER suite (verified via live round-trip).
