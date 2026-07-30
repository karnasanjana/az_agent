# SchemaViz — Business Model & Revenue Strategy

## Revenue Model

### Primary Revenue: SaaS Subscriptions

| | Free | Pro ($19/mo) | Team ($79/mo) | Business ($199/mo) |
|---|---|---|---|---|
| **Purpose** | Acquisition funnel | Individual revenue | Team revenue | Expansion revenue |
| **Target** | 1000s of signups | 5-10% convert | 20% of Pro upgrade | Enterprise teams |

**Year 1 Realistic Projections:**

| Metric | Value |
|---|---|
| Monthly signups (free) | 500 |
| Free → Pro conversion (5%) | 25 new Pro/mo |
| Pro → Team upgrade (10%) | ~3 Team/mo |
| Monthly churn | 5% |
| **Month 12 MRR** | **~$8K-12K/mo** |
| **Year 1 ARR** | **~$100-150K** |

---

### Secondary Revenue: AI Usage (Consumption-Based)

AI features cost money (Vertex AI / Claude API calls). Turn cost into revenue:

| Feature | Free Tier | Pro Tier | Business Tier |
|---|---|---|---|
| AI chat messages | 10/day | 100/day | Unlimited |
| AI auto-documentation | 5 tables | Unlimited | Unlimited |
| Cross-database queries | None | 20/day | Unlimited |

**Why this works:** Users who get value from AI hit limits and upgrade. Users who don't use AI stay on free — costing nothing.

---

### Third Revenue: Enterprise Contracts

Once 50+ paying teams exist, enterprise deals come inbound:

| What They Need | What We Charge |
|---|---|
| SSO / SAML | $500+/mo |
| On-premise deployment | $1000+/mo |
| Custom connectors (Oracle, Snowflake, Databricks) | $200-500/mo add-on |
| SLA + dedicated support | 2-3x base price |
| Compliance reports (SOC2, data dictionary for audits) | Premium add-on |

**Enterprise deals average $20-50K/yr.** Five of these = entire Year 1 SMB revenue.

---

### Fourth Revenue: Marketplace & Integrations

| Integration | Revenue Model |
|---|---|
| **dbt integration** | Free (drives adoption) — dbt users need schema viz badly |
| **Slack bot** | "Ask your database from Slack" — premium feature |
| **VS Code extension** | Schema explorer in IDE — drives Pro signups |
| **API access** | Developers embed schema docs in CI/CD — usage-based pricing |
| **Terraform/Pulumi provider** | Infrastructure teams pay for schema-as-code — Business tier |

---

## Where the Real Money Is

What companies actually pay for, ranked by willingness to pay:

| Problem | What They Pay Today | What We Charge |
|---|---|---|
| "New hire onboarding takes 2 weeks to understand our data" | Nothing (lost productivity ~$5K/hire) | $79/mo Team plan |
| "We have no documentation for our databases" | $100K+/yr for Atlan/Alation, or nothing | $199/mo Business plan |
| "If we change this column, what breaks?" | Manual investigation (days of engineer time) | $199/mo Business plan |
| "We need a data dictionary for our SOC2 audit" | Consultant ($10-50K one-time) | $199/mo + export feature |
| "Our analysts keep asking engineers about the schema" | Meetings (hidden cost ~$2K/mo in time) | $79/mo Team plan |

**The insight:** We're not selling a tool. We're selling **time saved**. A $79/mo plan that saves a team 10 hours/month of "how does this database work?" conversations is an obvious buy.

---

## Go-to-Market Strategy

### Phase 1: Developer-Led Growth (Month 1-6)

| Channel | Action | Cost |
|---|---|---|
| **Product Hunt launch** | Launch with "Understand any database in 30 seconds" | Free |
| **HackerNews "Show HN"** | Post with honest technical story | Free |
| **Dev.to / Hashnode articles** | "I built an AI tool that auto-documents databases" | Free |
| **Reddit** | r/database, r/dataengineering, r/SQL | Free |
| **Twitter/X** | Demo GIFs — connect DB, instant diagram, AI explains it | Free |
| **YouTube** | 2-minute demo video | Free |

**Goal:** 1000 free signups, 50 paid users.

### Phase 2: Content-Led SEO (Month 3-12)

| Content | Target Keyword |
|---|---|
| "How to document your database automatically" | Database documentation tool |
| "ER diagram from existing database" | ER diagram generator |
| "Understand legacy database schema" | Legacy database documentation |
| "Free alternative to Atlan" | Atlan alternative |

**Goal:** Organic traffic → free signups → conversion.

### Phase 3: Team Expansion (Month 6-18)

One person signs up free → shows team → team upgrades. This is how Figma, Notion, and Slack grew.

**Key feature needed:** Shareable read-only links. This is the viral mechanism.

---

## Revenue Timeline

| Timeline | MRR | ARR | Milestone |
|---|---|---|---|
| Month 3 | $500 | $6K | First 30 paid users |
| Month 6 | $2K | $24K | Product-market fit signal |
| Month 12 | $8-12K | $100-150K | Sustainable solo/small team |
| Month 18 | $20-30K | $250-360K | First enterprise deal |
| Month 24 | $50K+ | $600K+ | Real business |

---

## Unit Economics

| Metric | Value |
|---|---|
| **CAC (Customer Acquisition Cost)** | ~$0 (product-led growth, free tier) |
| **LTV (Lifetime Value) — Pro** | $19/mo x 14 months avg = $266 |
| **LTV — Team** | $79/mo x 18 months avg = $1,422 |
| **LTV — Business** | $199/mo x 24 months avg = $4,776 |
| **LTV:CAC Ratio** | >10:1 (excellent for SaaS) |
| **Gross Margin** | ~80% (main costs: AI API calls, Cloud Run hosting) |
| **AI cost per user/month** | ~$0.50-2.00 (Haiku for simple, Sonnet for complex) |
| **Infrastructure cost per user/month** | ~$0.10-0.50 (Cloud Run scales to zero) |

---

## What Could Kill This

| Risk | Mitigation |
|---|---|
| ChartDB goes AI-heavy and targets same market | Move faster, focus on non-technical users (they won't) |
| Big player (GitHub, Atlassian) adds this feature | They'll do it poorly and enterprise-only. Mid-market is safe. |
| Claude/AI costs eat margins | Cache AI responses aggressively, use Haiku for simple tasks |
| Nobody wants to pay for database diagrams | We're not selling diagrams — we're selling "instant database understanding." Frame it right. |
| Free tier costs too much to host | Limit AI calls on free tier, use serverless (Cloud Run scales to zero) |

---

## Bottom Line

The revenue comes from solving a **$5K-50K/year problem** (wasted time understanding databases) with a **$19-199/month tool**. That's a 10-50x ROI for the customer — easy to justify.

The first dollar will come from a developer who connects their messy legacy SQL Server, sees AI-generated documentation, and thinks "I need this for my team." Price: $79/month. That's our beachhead.
