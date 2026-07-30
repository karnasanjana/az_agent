# SchemaViz — Product Strategy & Roadmap

## The Market Gap

There's a **massive gap** between free tools (dbdiagram.io, DrawSQL) and enterprise catalogs ($100K+/yr like Atlan, Alation). Nothing exists in the **$15-250/mo range** that does what we're building.

Our idea — "help people understand data before implementation" — maps to a real, painful workflow:

> Person joins team → asks "how does the database work?" → nobody knows → spends days/weeks guessing → knowledge stays in their head → next person repeats the cycle

---

## Positioning

**Don't position as:** "An ER diagram tool" — commoditized, free alternatives everywhere.

**Position as:** "Instant database understanding for teams" — connect any database, get AI-generated documentation, relationship maps, and impact analysis in seconds.

**Tagline:** "Understand any database in 30 seconds."

**Target user (primary):** The developer or analyst who just joined a team and needs to build something on an existing database they've never seen.

**Target user (secondary):** The tech lead who's tired of answering "how does the database work?" for every new hire.

---

## What to Build (Focused Roadmap)

### Phase 1: Nail the "Instant Understanding" Story

This is our wedge. Someone connects a database and in **30 seconds** they understand it.

| Feature | Why It Matters |
|---------|---------------|
| **AI auto-documentation** | Generate plain-English descriptions for every table and column. "This table stores customer orders, linked to customers via customer_id." No tool does this affordably. |
| **AI relationship inference with confidence scores** | Legacy DBs have missing FKs. Show "85% confident order_items.product_id → products.product_id" with Accept/Reject. ChartDB started this but it's basic. |
| **"Explain this schema" chat** | Our existing feature. But frame it as onboarding, not optimization. The first question should be "What does this database do?" not "Optimize this schema." |
| **Sample data preview** | Show 5 rows per table inline on the diagram. Instantly answers "what kind of data is in here?" |

### Phase 2: Make It a Team Tool

This is what justifies paying $50+/mo.

| Feature | Why It Matters |
|---------|---------------|
| **Shareable links** | Generate a read-only link to a diagram. No login required. This is how it spreads in teams. |
| **Schema change tracking** | "3 columns added to orders table since last week." Living documentation, not stale Confluence. |
| **Annotations/comments** | Click a table, leave a note: "Don't use this column, it's deprecated." Team knowledge captured. |
| **Impact analysis** | "If I change customer_id, what breaks?" Show all tables/columns that reference it. This is $100K+ enterprise catalog territory — offer it for $100/mo. |

### Phase 3: Cross-Database Intelligence (Our Differentiator)

No mid-market tool does this. Enterprise catalogs charge $100K+ for it.

| Feature | Why It Matters |
|---------|---------------|
| **Cross-database lineage** | "Data flows from Dataverse → SQL Server → BigQuery." Visual lineage map. |
| **Cross-database querying** | Already built. Polish it. |
| **Unified data dictionary** | One place to see all tables across all connected databases with AI descriptions. |

---

## What to Stop Doing

| Drop/Deprioritize | Why |
|---|---|
| Schema optimization suggestions ("merge tables", "add indexes") | DBAs don't need AI for this. It's a nice demo but not a buying reason. |
| SQL DDL generation | Every DB tool does this. Not a differentiator. |
| PDF export polish | Nice-to-have, not a reason anyone pays. |
| Manual relationship drawing | Focus on AI inference instead. |

---

## Pricing (Validated by Market Research)

| Tier | Price | What You Get |
|------|-------|---|
| **Free** | $0 | 1 database, 20 tables, 2 saved diagrams |
| **Pro** | $19/mo | Unlimited, AI docs, export, all connectors |
| **Team** | $79/mo (5 users) | Shared diagrams, annotations, change tracking |
| **Business** | $199/mo (15 users) | Cross-database, impact analysis, API |

The $19-199/mo range has **zero competition** for this feature set.

---

## Competitive Landscape

### Closest Competitor

**ChartDB** — open source, AI-assisted, browser-based. But they target developers only, not business users. They don't have cross-database orchestration, natural language querying, or auto-documentation.

### Our Moat

**Cross-database intelligence + AI auto-documentation + non-technical user accessibility.** No one else combines these three at mid-market pricing.

### Competitor Matrix

| Tool | Price | Live DB Connection | AI Features | Cross-Database | Non-Technical Users |
|------|-------|--------------------|-------------|----------------|---------------------|
| dbdiagram.io | Free-$14/mo | No | No | No | No |
| DrawSQL | Free-$179/mo | No | No | No | Partial |
| ChartDB | Free-$59/mo | Yes (one-click) | Basic AI FK detection | No | No |
| Azimutt | Open source | Yes | No | Partial | No |
| Atlan | $100K+/yr | Yes | Yes | Yes | Yes |
| **SchemaViz (us)** | **$0-199/mo** | **Yes** | **Yes (advanced)** | **Yes** | **Yes** |

---

## Key Risks

| Risk | Mitigation |
|------|-----------|
| ChartDB goes AI-heavy and targets same market | Move faster, focus on non-technical users (they won't) |
| Big player (GitHub, Atlassian) adds this feature | They'll do it poorly and enterprise-only. Mid-market is safe. |
| Claude/AI costs eat margins | Cache AI responses aggressively, use Haiku for simple tasks |
| Nobody wants to pay for database diagrams | We're not selling diagrams — we're selling "instant database understanding." Frame it right. |
| Free tier costs too much to host | Limit AI calls on free tier, use serverless (Cloud Run scales to zero) |
