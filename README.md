<!-- Fork README: concise, optimized, free-to-use fork of MiroFish -->

# MiroFish — Optimized Fork (Free-to-Use)

This repository is a fork of the original MiroFish project, reworked and optimized so anyone can run it easily and for free. The core ideas remain the same — multi-agent simulation for forecasting and creative simulations — but this fork focuses on streamlined setup, clearer defaults, and free-tier friendliness.

**Quick highlights:**

- **Free-friendly:** defaults and docs optimized to work with free-tier services where possible.
- **Lightweight:** reduced friction for local and Docker runs.
- **Same goals:** multi-agent simulation and report generation, ready for experimentation.

## **Why this fork**

This fork is intended for hobbyists, students, and developers who want to explore MiroFish concepts without heavy cloud requirements. It provides:

- Simplified configuration and examples for free LLM/Zep alternatives.
- Clear Quick Start paths (local and Docker).
- Fewer optional features enabled by default to lower costs.

## **Features**

- Multi-agent simulation engine and ReportAgent integrations
- Graph construction and environment generation tools
- Ready-to-run frontend and backend (Vue + Python)
- Docker Compose for one-command launches

## **Quick Start**

Recommended: run with Docker Compose (fast and consistent):

```bash
cp .env.example .env
docker compose up -d --build
```

Local (node + python):

```bash
# install frontend and backend deps
npm install
npm run setup:backend

# start dev servers
npm run dev
```

Default endpoints after startup:

- Frontend: http://localhost:3000
- Backend API: http://localhost:5001

## **Configuration**

Copy `.env.example` to `.env` and set any required keys. The fork aims to be usable with free LLM endpoints or mocked LLMs; if you don't have a paid key, configure a local or community model and point `LLM_BASE_URL` accordingly.

Minimum variables to check in `.env`:

- `LLM_API_KEY` (optional for mocked/local models)
- `LLM_BASE_URL` (point to your model endpoint)
- `ZEP_API_KEY` (optional; the repo can run with local memory or free Zep accounts)

If you want strictly zero-cost exploration, try setting up a local lightweight model (see docs) and leave API keys empty.

## **How to use**

1. Upload a project via the frontend `Process` flow or place sample project files under `backend/uploads/projects/`.
2. Build a graph in Step 1, configure environment in Step 2, run simulations in Step 3.
3. Use the Report view to inspect outputs and download reports.

## **Contributing & Support**

Contributions are welcome. For small fixes or docs improvements, open a PR. If you'd like help configuring a free setup, open an issue describing your environment and goals.

## **License & Credits**

This fork follows the original project's license. See [LICENSE](LICENSE) for details.

Original project and thanks: the MiroFish project and its contributors. The simulation engine leverages OASIS and other open tools — see original README for full credits.

---

If you want, I can also update `README-EN.md` to match this forked README or add a minimal `GETTING_STARTED.md` with step-by-step screenshots — tell me which you'd prefer.
