# SecureDoc AI

SecureDoc AI is a security-conscious document intelligence MVP for turning business invoices into structured, searchable and analyzable data.

## Included
- Next.js + TypeScript frontend
- FastAPI backend
- SQLite by default; PostgreSQL-ready
- Organization-aware authentication and role checks
- PDF text extraction and optional OCR for images/scanned PDFs
- Provider-independent AI extraction: rules, Ollama, or OpenAI-compatible APIs
- Invoice validation and duplicate detection
- Invoice line items
- Search and status filtering
- Live dashboard/analytics
- CSV, Excel and PDF exports
- Read-only rule-based business assistant with organization-scoped queries
- Notifications and audit log foundation
- Private local document storage with safe path checks
- Basic rate limiting and security headers

## Run backend
```bash
cd backend
python -m venv .venv
# activate the environment
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Run frontend
```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` if the API is not `http://localhost:8000/api`.

## AI providers
Default is `AI_PROVIDER=rules`, which requires no external AI API but is only a fallback parser.

For a local LLM, set:
```env
AI_PROVIDER=ollama
AI_MODEL=llama3.2
OLLAMA_URL=http://localhost:11434
```

For an OpenAI-compatible endpoint, set:
```env
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=your-key
AI_MODEL=your-model
```

Do not put AI API keys in the frontend.

## Production checklist
Before real company documents are used in production, replace local storage with private object storage, use PostgreSQL, set a strong `JWT_SECRET`, configure production CORS, use a mature authentication/session solution, add persistent rate limiting, run migrations, configure monitoring/backups, review data retention, and perform security testing.
