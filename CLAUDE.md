# Six Degrees of Movies

Find the shortest path between two actors through shared movies — a Six Degrees of Separation game using IMDB data.

Live at: **https://sixdegreesofmovies.com** (Cloud Run, `australia-southeast2`)

---

## Architecture

```
actor_game.py   — CLI + BFS engine + DB build pipeline
server.py       — FastAPI backend (serves API + static frontend)
frontend/       — React + Vite (no TypeScript)
gcs_db.py       — GCS helper for DB upload/download at container startup
entrypoint.sh   — Container startup: local DB → GCS → from-scratch fallback
terraform/      — GCP infrastructure (Cloud Run, GCS, Artifact Registry)
```

**Data:** IMDB public TSV datasets → SQLite (`imdb.db`, ~850 MB). Built once locally, uploaded to GCS, downloaded by Cloud Run on cold start.

**Database tables:** `actors` (nconst, name, max_votes, known_for), `movies` (tconst, title, year, type, rating, votes), `appearances` (nconst, tconst), `ratings` (tconst, rating, votes)

---

## Development

### Backend

```bash
uv run actor-game setup          # Download IMDB data and build DB (~20 min first time)
uv run actor-game serve          # Start API server on :8000
uv run actor-game play           # Interactive CLI game
```

The DB is stored at `~/.actor-game/imdb.db` by default. Override with `ACTOR_GAME_DATA_DIR`.

### Frontend

```bash
cd frontend
npm install
npm run dev       # Dev server on :5173 (proxies nothing — configure CORS via docker-compose)
npm run build     # Production build → frontend/dist/ (served by FastAPI in production)
```

For local full-stack dev, run both `uv run actor-game serve` and `npm run dev` simultaneously. CORS is enabled when `ALLOWED_ORIGINS` env var is set (see docker-compose.yml).

### Docker (full stack locally)

```bash
docker compose up --build        # Builds image, mounts ~/.actor-game, serves on :8000
```

The compose file mounts `~/.actor-game` as `/data` and runs as root (needed for volume permissions). In production the container runs as nonroot (uid 65532).

---

## Key design decisions

**BFS algorithm:** Bidirectional BFS (`bfs()`) for single shortest path. `bfs_multi()` finds up to 5 shortest paths — seeds from the first path, caps exploration at 2000 nodes, builds a shortest-path DAG, then DFS-enumerates up to k paths. Dijkstra is not needed; all edges are unweighted.

**Multi-leg searches:** Waypoint actors are added to a `forbidden` set so they can't appear as intermediaries in other legs — prevents nonsensical paths.

**Actor search:** Pre-computed `max_votes` and `known_for` columns on the `actors` table enable O(1) popularity-sorted search without joins. Populated in Pass 5 of `build_database()`.

**DB build:** Incremental — each of the 5 passes checks a completion flag before running, so re-running setup after a partial failure or adding a new pass only processes what's missing.

**Graph visualisation:** SVG with layered layout. Horizontal (left→right) on desktop, vertical (top→bottom) on mobile (≤640px breakpoint). Up to 5 paths shown side-by-side.

**URL state:** All game state (actors, filters, waypoints) is encoded in the URL via `URLSearchParams` so games can be shared. Actors encoded as `nconst|name`.

**CORS:** Only active when `ALLOWED_ORIGINS` env var is set (comma-separated origins). Not needed in production since frontend and API share the same Cloud Run origin.

**Rate limiting:** `slowapi` — 60 req/min on `/api/search`, 10 req/min on `/api/connect`. Uses `X-Forwarded-For` for real client IP behind Cloud Run's proxy.

---

## Deployment

### Infrastructure (Terraform)

```bash
cd terraform
cp backend.tf.example backend.tf        # Fill in TF state bucket
cp terraform.tfvars.example terraform.tfvars  # Fill in project_id

terraform init
terraform plan
terraform apply
```

Terraform manages: Cloud Run service, Artifact Registry, GCS data bucket, service accounts, IAM. State stored in `gs://terraform-six-degrees-imdb`.

Sensitive files are gitignored: `terraform/backend.tf`, `terraform/terraform.tfvars`.

### Build and deploy

```bash
# Authenticate (once)
gcloud auth configure-docker australia-southeast2-docker.pkg.dev

# Build for linux/amd64 — required; Cloud Run is amd64, dev machine is arm64
docker build --platform linux/amd64 \
  -t australia-southeast2-docker.pkg.dev/six-degrees-imdb/actor-game/actor-game:latest .

docker push australia-southeast2-docker.pkg.dev/six-degrees-imdb/actor-game/actor-game:latest

# Deploy
cd terraform && terraform apply \
  -var="image=australia-southeast2-docker.pkg.dev/six-degrees-imdb/actor-game/actor-game:latest"
```

### Seeding the database

The DB must be in GCS before deploying — otherwise Cloud Run will attempt a from-scratch build on startup (~20 min, high memory, likely OOM).

```bash
gsutil cp ~/.actor-game/imdb.db gs://six-degrees-imdb-actor-game-data/
```

### Container startup sequence

1. Check `$ACTOR_GAME_DATA_DIR/imdb.db` (local/mounted volume) → use it
2. Check `gs://$GCS_BUCKET/imdb.db` → download (~30–60s for 850 MB)
3. Sync any cached raw IMDB TSV files from GCS, run `actor-game setup`, upload everything to GCS

---

## GCP project

- **Project:** `six-degrees-imdb`
- **Region:** `australia-southeast2` (Melbourne)
- **Cloud Run:** `actor-game`
- **Artifact Registry:** `australia-southeast2-docker.pkg.dev/six-degrees-imdb/actor-game/actor-game`
- **GCS data bucket:** `six-degrees-imdb-actor-game-data`
- **GCS TF state bucket:** `terraform-six-degrees-imdb`
- **Terraform SA:** `terraform@six-degrees-imdb.iam.gserviceaccount.com`
- **Runtime SA:** `actor-game-run@six-degrees-imdb.iam.gserviceaccount.com`

---

## Frontend components

| Component | Purpose |
|---|---|
| `App.jsx` | Root — state, URL serialisation, random actor fetch on load |
| `LeftPanel.jsx` | Actor inputs, waypoints, filter controls, mobile collapse |
| `RightPanel.jsx` | Results display — path cards and graph |
| `ActorInput.jsx` | Search-as-you-type actor picker with popularity-sorted dropdown |
| `BranchCard.jsx` | Renders one path: actor → movie pill → actor → … |
| `GraphView.jsx` | SVG node/edge graph, horizontal desktop / vertical mobile |
| `SliderFilter.jsx` | Slider with click-to-type value editing |
| `Toggle.jsx` | Boolean filter toggle |

---

## Common gotchas

- **Always build with `--platform linux/amd64`** — building on Apple Silicon without this flag produces an arm64 image that crashes immediately on Cloud Run (`exec format error`).
- **Seed GCS before deploying** — Cloud Run will OOM trying to build the DB from scratch on startup.
- **`uv run` at runtime** — don't use `uv run` in the container entrypoint; call `/app/.venv/bin/*` directly to avoid uv trying to re-sync the root-owned venv as the nonroot runtime user.
- **DB build is incremental** — re-running `actor-game setup` on an existing DB is safe and fast; it only processes incomplete passes.
- **IMDB data coverage** — `title.principals.tsv.gz` only includes top-billed cast, not full credits. Some actors with few/minor roles will be in `name.basics` but unreachable in the graph.
