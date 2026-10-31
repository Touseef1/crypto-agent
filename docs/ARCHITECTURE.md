# Architecture
Next.js App Router provides server-rendered UI and authenticated HTTP APIs. Prisma connects to MySQL. The worker is a separate package and is intentionally non-operational in Phase 1. Future trading logic belongs in trading-core; the worker must remain PAPER-only until explicitly redesigned and audited.
