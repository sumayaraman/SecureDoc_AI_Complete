# Architecture

Frontend: Next.js + TypeScript + Tailwind + Recharts. Backend: FastAPI + SQLAlchemy. Database: PostgreSQL-ready.

Flow: Upload -> validation -> private storage -> text extraction/OCR -> provider-independent AI extraction -> schema/financial validation -> duplicate detection -> review -> database -> analytics/reports -> controlled read-only assistant.

Organization isolation is represented on organization-owned backend entities and must be enforced at the authenticated service/query boundary in production.
