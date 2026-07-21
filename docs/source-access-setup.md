# Granting the app access to Dataverse & SharePoint

Hand this to whoever administers your Microsoft 365 / Power Platform / Entra tenant.
It lists exactly **what to do**, **where**, and **what to cross-check**. Everything
here is done by an admin; the requester only needs the final URLs to test.

## The app being granted

| Field | Value |
|---|---|
| Client (Application) ID | `039ad0c3-7b36-496e-828a-8e01560c2b79` |
| Tenant ID | `e28d23e3-803d-418d-a720-c0bed39f77b6` |

> The app registration (Entra) already exists and authenticates fine. What's
> missing is **data-plane access** — Entra permission alone grants nothing in
> either Dataverse or SharePoint. Each has its own separate grant step below.

---

## Part A — Dataverse

### The gap
The app has an Entra app registration, but was **never added as an Application
User inside the Dataverse environment**. "Application User" is a Dataverse
concept — it is **not** in Entra and **not** in the app registration screen. This
is why an access test currently sees zero environments.

### Where: Power Platform admin center
Admin performing this needs the **System Administrator** role on the environment.

1. Go to **https://admin.powerplatform.microsoft.com**
2. Left nav → **Environments** → click the target environment.
3. **Settings** (top bar) → expand **Users + permissions** → **Application users**.
4. **+ New app user** (top).
5. **Add an app** → search/paste client id `039ad0c3-7b36-496e-828a-8e01560c2b79` → select it.
6. **Business unit**: leave as the root/default.
7. **Security roles** → add a role that has **Read** on the tables the requester
   needs. For read-only access, use a role scoped to Read (Organization or
   Business-Unit level) on the target tables. **Do not** assign System
   Administrator (over-privileged). If no suitable read role exists, create a
   custom role granting Read on the specific tables and assign that.
8. **Save**.
9. **Copy the Environment URL** — on the environment's page (or Settings →
   Developer resources). Format: `https://orgXXXXXXXX.crm.dynamics.com`
   (region suffix may vary: `.crm`, `.crm4`, etc.). **Give this URL to the requester** → it becomes `DATAVERSE_URL`.

### Cross-check (Dataverse)
- [ ] App appears in **Application users** list, **Status = Enabled**.
- [ ] The assigned **security role** grants **Read** on each needed table
      (check the role's table permissions — Read must be at least Business-Unit scope).
- [ ] No **Conditional Access** policy blocks this service principal from Dataverse.
- [ ] Environment URL captured and sent to the requester.

---

## Part B — SharePoint (`Sites.Selected`)

### The gap
`Sites.Selected` is **deny-by-default**. Granting admin consent on the permission
is **not enough** — the app has access to **nothing** until it is explicitly
granted **read on one specific site**. That per-site grant is a separate step
most people miss.

### Step 1 — confirm the permission + admin consent
Where: **Entra admin center** (https://entra.microsoft.com) → **App registrations**
→ the app → **API permissions**.

- [ ] **Microsoft Graph → Sites.Selected** is listed as an **Application** permission
      (not Delegated).
- [ ] Its status shows **"Granted for &lt;tenant&gt;"** (green check). If not, click
      **Grant admin consent**.

### Step 2 — grant the app read on a specific site
This is the step that actually unlocks data. Pick **one** method.

**Method A — PnP PowerShell (easiest):**
```powershell
# Run as a SharePoint / Global admin
Grant-PnPAzureADAppSitePermission `
  -AppId 039ad0c3-7b36-496e-828a-8e01560c2b79 `
  -DisplayName "BRD-ADF ingestion app" `
  -Site "https://<tenant>.sharepoint.com/sites/<YourSite>" `
  -Permissions Read
```

**Method B — Microsoft Graph (admin token):**
```
# 1. Get the site id
GET https://graph.microsoft.com/v1.0/sites/<tenant>.sharepoint.com:/sites/<YourSite>

# 2. Grant the app read on that site
POST https://graph.microsoft.com/v1.0/sites/<site-id>/permissions
{
  "roles": ["read"],
  "grantedToIdentities": [
    { "application": { "id": "039ad0c3-7b36-496e-828a-8e01560c2b79",
                       "displayName": "BRD-ADF ingestion app" } }
  ]
}
```

### Step 3 — hand over the site URL
Give the requester the exact site URL, e.g. `https://contoso.sharepoint.com/sites/Finance`.
They split it into:
- `SHAREPOINT_HOSTNAME` = `contoso.sharepoint.com`
- `SHAREPOINT_SITE_PATH` = `/sites/Finance`

### Cross-check (SharePoint)
- [ ] `Sites.Selected` is an **Application** permission with **admin consent granted**.
- [ ] A **site permission entry** exists on the target site for appId
      `039ad0c3…` with role **read** (verify: `GET .../sites/<site-id>/permissions`).
- [ ] Exact site URL sent to the requester.
- [ ] (Optional) A specific **list name** on that site, if row-level testing is wanted.

---

## Verification (requester side, after admin is done)

Fill these in `.env`:
```
SOURCE_CLIENT_SECRET=<the secret>
DATAVERSE_URL=https://orgXXXX.crm.dynamics.com
SHAREPOINT_HOSTNAME=<tenant>.sharepoint.com
SHAREPOINT_SITE_PATH=/sites/<YourSite>
SHAREPOINT_LIST=<a list name>          # optional, for reading rows
```
Then run:
```
python tools/probe_source.py
```
- **200 / OK** → access works; data can be landed to bronze.
- **401 / 403** → the corresponding grant above is still missing (the probe prints which).
