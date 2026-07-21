# Wiring Dataverse / SharePoint as a pipeline source (future build)

**Status: NOT built into the compiler yet.** Testing currently uses the bootstrap
mover `tools/inject_to_bronze.py` (agent-side copy, runs as the app-reg SP). This
doc is the plan for the *production* path: the BRD names a Dataverse table, the
compiler emits an ADF Copy that ADF runs on a schedule.

## Design: drop-in replacement for the landing container

Today: `landing CSV ──Copy──► bronze ──► silver ──► gold`. Grounding reads the
schema from the landing file header.

New: `Dataverse/SharePoint ──Copy──► bronze ──► silver ──► gold`. Only the origin
and the schema-read source change; **bronze/silver/gold are identical.** The
existing `sql_table` source is the exact template — a non-landing origin that
grounds and copies to bronze. Mirror it.

## Code changes (mirror the `sql_table` path)

1. **models/logical.py** — add to `SourceFormat`: `dataverse`, `sharepoint_list`.
   Add fields to `LogicalSource`: `dataverse_url`, `entity_set` (plural, e.g.
   `accounts`), `logical_name` (singular, e.g. `account`, for metadata). Extend
   `_location_complete` validator: `dataverse` needs `dataverse_url` + `entity_set`.

2. **models/spec.py** — add `AuthKind.service_principal`; add
   `DatasetKind.dataverse_entity`; `LinkedService` already has enough fields (add
   `entity_name` to `Dataset` or reuse `table_name`).

3. **agent/compiler.py** —
   - `_DS_KIND_BY_FORMAT[SourceFormat.dataverse] = DatasetKind.dataverse_entity`
   - linked-service loop (~line 298): add a `dataverse` branch building
     `LinkedService(type="CommonDataServiceForApps", ...)` keyed by env url.
   - ingest loop (~line 375, next to the `sql_table` branch): landing dataset =
     Dataverse entity dataset; bronze sink stays DelimitedText CSV; Copy source →
     bronze unchanged.

4. **agent/builder.py** — in `build_linked_service` add a `CommonDataServiceForApps`
   branch (auth JSON below). In `build_dataset` add a Dataverse-entity branch
   (`"type": "CommonDataServiceForAppsEntity"`, `typeProperties.entityName`). Add
   the copy source type to `_COPY_SOURCE_TYPE` (`"CommonDataServiceForAppsSource"`).

5. **agent/grounding.py** — when a source is `dataverse`, call
   `tools/source_schema.py::dataverse_schema(env_url, logical_name)` to stamp real
   columns/types INSTEAD of reading a file header. Schema is available before any
   data lands — removes the CSV first-run gap.

6. **agent/plantools.py + planhandlers.py** — `add_source` accepts `dataverse`
   with `dataverse_url` + `entity_set`, so the planner can emit it from a BRD.

## Auth — RESOLVED (2026-07-21, after a real deploy)

**System-Assigned Managed Identity does NOT work for a Dataverse source.** ADF
rejects it at runtime: `UserErrorUnsupportedDynamicsAuthenticationType — Invalid
authentication type 'SystemAssignedManagedIdentity' for Dynamics source.
Supported: Office365, OAuth, IFD`. Per Microsoft docs, `CommonDataServiceForApps`
valid `authenticationType` values are **AADServicePrincipal**, **Office365**, and
**ManagedIdentity (user-assigned only, via a credential reference)** — never
system-assigned. Also: a Dataverse copy source must NOT carry `storeSettings`
(that made ADF treat it as a file store and mis-read the auth).

### IMPLEMENTED default — AADServicePrincipal (the granted app reg)
```json
{
  "type": "CommonDataServiceForApps",
  "typeProperties": {
    "deploymentType": "Online",
    "serviceUri": "https://zcscmdemodev.crm.dynamics.com",
    "authenticationType": "AADServicePrincipal",
    "servicePrincipalId": "039ad0c3-7b36-496e-828a-8e01560c2b79",
    "servicePrincipalCredentialType": "ServicePrincipalKey",
    "servicePrincipalCredential": { "type": "SecureString", "value": "<secret>" }
  }
}
```
`build_linked_service` fills the id/secret from `SOURCE_*` (fallback `AZURE_*`)
env at build time — never stored in the spec; ADF encrypts the SecureString on
deploy. This reuses the app reg already granted as an Application User, so no new
admin step.

### PROD hardening — swap the inline secret for Key Vault
Replace `servicePrincipalCredential` with an `AzureKeyVaultSecret` ref (needs a
Key Vault linked service, not built yet):
```json
"servicePrincipalCredential": {
  "type": "AzureKeyVaultSecret",
  "store": { "referenceName": "ls_keyvault", "type": "LinkedServiceReference" },
  "secretName": "dataverse-app-secret"
}
```

### If you'd rather use a managed identity
Only **user-assigned** MI is valid: create a UAMI, assign it to the factory, add
it as a Dataverse Application User, and emit `authenticationType: ManagedIdentity`
with a `credential` CredentialReference. More infra than the service principal.

## SharePoint (same shape, when a site is granted)
- List → linked service `SharePointOnlineList`; document library files → Graph via
  the existing `http_csv`/REST path + a Web Activity for the OAuth token.
- Blocked until an admin grants the app a specific site (`Sites.Selected`). See
  `docs/source-access-setup.md`.

## Reference tools already built (proven)
- `tools/source_schema.py` — `dataverse_schema` / `github_schema` /
  `sharepoint_list_schema` (the "read schema first" step).
- `tools/inject_to_bronze.py` — bootstrap source→bronze copy (Dataverse ✅ 4
  accounts, GitHub ✅ iris landed to mock bronze).
- `tools/probe_source.py`, `tools/list_dataverse.py` — access probe + catalog.
