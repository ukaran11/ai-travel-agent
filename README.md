# AI Travel Agent



A production-ready conversational AI travel agent that replaces static filter-based location search with a **LangGraph-orchestrated multi-node agent** powered by **Gemini 2.0 Flash** and **Google Places API (New)**. Users describe what they want in plain language — the agent understands, searches, ranks, and streams back results card by card.



**Example interactions:**

> *"Find me a rooftop restaurant in Bandra under ₹1500 for a date night"*

> *"Best rated cafes near Connaught Place, Delhi that are open now"*

> *"Family-friendly restaurants in Indiranagar, Bangalore — budget options only"*



The agent maintains full conversation context, so follow-up questions like *"Are any of them open on Sundays?"* or *"Show me cheaper options"* work across turns.



---



## Table of Contents



1. [How It Works — End to End](#1-how-it-works--end-to-end)

2. [Architecture Overview](#2-architecture-overview)

3. [Tech Stack](#3-tech-stack)

4. [Project Structure](#4-project-structure)

5. [Prerequisites](#5-prerequisites)

6. [Getting API Keys](#6-getting-api-keys)

7. [Local Development Setup](#7-local-development-setup)

8. [Mock Mode (No API Keys Needed)](#8-mock-mode-no-api-keys-needed)

9. [Environment Variables Reference](#9-environment-variables-reference)

10. [Running with Docker](#10-running-with-docker)

11. [API Reference](#11-api-reference)

12. [Running Tests](#12-running-tests)

13. [Production Deployment — GCP Cloud Run](#13-production-deployment--gcp-cloud-run)

14. [CI/CD — GitHub Actions](#14-cicd--github-actions)

15. [Troubleshooting](#15-troubleshooting)

16. [Architecture Decisions](#16-architecture-decisions)

17. [Security](#17-security)

18. [Performance](#18-performance)



---



## 1. How It Works — End to End



### Request flow (one user message)



```

User types "Find rooftop bars in Bandra, Mumbai" → presses Enter

    │

    ▼

[React Frontend]

  useChat hook → sendMessageStream() → POST /api/v1/chat/stream

    │

    ▼

[FastAPI — POST /api/v1/chat/stream]

  Validates ChatRequest (message, session_id)

  Calls travel_agent.astream_events(...)

    │

    ▼

[LangGraph Agent — Node 1: intent_extraction_node]

  LLM (Gemini 2.0 Flash) reads the message

  Returns structured JSON:

    { query: "rooftop bars", location: "Bandra, Mumbai",

      budget: null, vibe: "casual", place_type: "bar" }

  Routing decision → new search pipeline

    │

    ▼

[Node 2: geocoding_node]

  Calls Google Geocoding API (or mock)

  "Bandra, Mumbai" → { lat: 19.0596, lng: 72.8295 }

    │

    ▼

[Node 3: places_search_node]

  Calls Google Places API (New) — Nearby Search

  Returns up to 20 raw PlaceResult objects

    │

    ▼

[Node 4: filter_and_rank_node]

  Removes closed places (if open-only requested)

  Filters by budget tier (price_level)

  Scores each place: rating×0.4 + distance×0.3 + reviews×0.2 + open×0.1

  Returns top-N sorted by score

    │

    ▼

[Node 5: response_generation_node]

  LLM generates a friendly natural-language summary

  Uses place names, ratings, and context

  Sets state.final_response and state.filtered_places

    │

    ▼

[FastAPI — streaming route]

  on_chain_end event fires for each node

  Emits SSE events:

    data: {"type":"places","content":[...]}    ← place cards

    data: {"type":"token","content":"Here "}   ← word-by-word text

    data: {"type":"token","content":"are "}

    ...

    data: {"type":"done","content":""}

    │

    ▼

[React Frontend]

  SSE reader in api.ts fires onToken / onPlaces / onDone callbacks

  useChat hook appends tokens to the assistant message in real time

  RecommendationCard components render each place

  Send button re-enables after onDone

```



### Follow-up turn flow



When the user sends a second message like *"Are they open now?"*:



1. `intent_extraction_node` detects a follow-up (no new location, references previous results)

2. Router sends to `follow_up_handler_node` instead of restarting the search pipeline

3. `follow_up_handler_node` answers from existing `filtered_places` in state

4. No new geocoding or Places API call is made — **session state is preserved by LangGraph's MemorySaver**



---



## 2. Architecture Overview



```

┌─────────────────────────────────────────────────────────────────┐

│                     React 18 + TypeScript                       │

│                                                                 │

│  ChatInterface.tsx                                              │

│    └── useChat hook (state, isLoading, sendChat, clearChat)     │

│         └── sendMessageStream() — fetch + SSE reader            │

│              └── onToken → append to message content            │

│              └── onPlaces → render RecommendationCard[]         │

│              └── onDone → setIsLoading(false)                   │

│                                                                 │

│  MessageBubble.tsx ── RecommendationCard.tsx                    │

│  ErrorBoundary.tsx ── LoadingIndicator.tsx                      │

└─────────────────────────────┬───────────────────────────────────┘

                              │ HTTP  (dev: Vite proxy → :8000)

                              │        (prod: Nginx proxy → backend)

┌─────────────────────────────▼───────────────────────────────────┐

│                FastAPI  (uvicorn, async)                        │

│                                                                 │

│  POST /api/v1/chat           — synchronous, returns full JSON   │

│  POST /api/v1/chat/stream    — SSE token stream                 │

│  GET  /api/v1/session/{id}   — conversation history             │

│  DELETE /api/v1/session/{id} — clear session                    │

│  GET  /api/v1/health         — readiness probe                  │

│  GET  /api/v1/place/{id}     — single place detail              │

│  POST /mcp/tools/call        — MCP JSON-RPC tool server         │

│                                                                 │

│  CORS middleware, Pydantic v2 validation                        │

└─────────────────────────────┬───────────────────────────────────┘

                              │

┌─────────────────────────────▼───────────────────────────────────┐

│               LangGraph StateGraph  (MemorySaver)               │

│                                                                 │

│  START                                                          │

│    ▼                                                            │

│  intent_extraction_node  ──missing location──► END (ask user)  │

│    │  follow-up detected                                        │

│    ├──────────────────────► follow_up_handler_node ──► END     │

│    │  new search                                                │

│    ▼                                                            │

│  geocoding_node  ──error──► END                                 │

│    ▼                                                            │

│  places_search_node  ──error──► END                             │

│    ▼                                                            │

│  filter_and_rank_node                                           │

│    ▼                                                            │

│  response_generation_node ──► END                               │

└────────────────┬───────────────────────┬────────────────────────┘

                 │                       │

    ┌────────────▼────────┐   ┌──────────▼──────────────┐

    │  Google Places API  │   │  Google Geocoding API   │

    │  (Nearby Search,    │   │  (address → lat/lng)    │

    │   Place Details)    │   └─────────────────────────┘

    └────────────┬────────┘

                 │

    ┌────────────▼────────────────────┐

    │  Gemini 2.0 Flash (via         │

    │  langchain-google-genai)        │

    │  Intent extraction, response    │

    │  generation, follow-up answers  │

    └─────────────────────────────────┘

```



---



## 3. Tech Stack



| Layer | Technology | Version |

|-------|------------|---------|

| LLM | Google Gemini 2.0 Flash | `gemini-2.0-flash-001` |

| Agent orchestration | LangGraph StateGraph + MemorySaver | 0.2.x |

| LLM SDK | LangChain + langchain-google-genai | 0.2.x |

| Backend framework | FastAPI | 0.111+ |

| ASGI server | uvicorn | 0.30+ |

| Data validation | Pydantic v2 + pydantic-settings | 2.7+ |

| SSE streaming | sse-starlette | 2.1+ |

| HTTP client | httpx (async) + tenacity retries | 0.27+ |

| MCP protocol | Custom HTTP JSON-RPC (FastAPI router) | — |

| Frontend framework | React 18 + TypeScript | 18.3 / 5.5 |

| Styling | Tailwind CSS v3 | 3.4+ |

| Bundler | Vite 5 | 5.3+ |

| API client | Axios (REST) + native `fetch` (SSE) | 1.7+ |

| Containers | Docker + docker-compose | 3.9 |

| Prod web server | Nginx Alpine | 1.27 |

| CI/CD | GitHub Actions + GCP Cloud Build | — |

| Cloud deployment | GCP Cloud Run | — |



---



## 4. Project Structure



```

ai-travel-agent/

│

├── backend/

│   ├── main.py                  # FastAPI app: CORS, routers, startup

│   ├── config.py                # Pydantic-settings: all env vars + USE_MOCKS flag

│   │

│   ├── agent/

│   │   ├── __init__.py

│   │   ├── state.py             # TypedDict (TravelAgentState) + Pydantic models

│   │   │                        #   IntentModel, Coords, PlaceResult

│   │   ├── prompts.py           # Prompt templates: SYSTEM, INTENT, RESPONSE, etc.

│   │   ├── nodes.py             # 6 async node functions + _get_llm() factory

│   │   └── graph.py             # StateGraph definition, routing functions,

│   │                            #   build_graph() → compiled travel_agent

│   │

│   ├── mcp/

│   │   ├── __init__.py

│   │   ├── server.py            # MCP HTTP tool server (FastAPI router at /mcp)

│   │   └── tools/

│   │       ├── __init__.py

│   │       ├── geocoding_tool.py  # geocode_location() → Coords

│   │       ├── places_tool.py     # search_places(), get_place_details()

│   │       ├── filter_tool.py     # filter_and_rank_places() — scoring logic

│   │       └── mock_data.py       # MockLLM, mock_geocode, _MOCK_PLACES

│   │                              #   used when USE_MOCKS=true

│   │

│   ├── api/

│   │   ├── schemas.py           # ChatRequest, ChatResponse, PlaceResponse, etc.

│   │   └── routes.py            # All route handlers (chat, stream, session, health)

│   │

│   ├── tests/

│   │   ├── conftest.py          # Fixtures: mock_settings, async client, etc.

│   │   ├── test_tools.py        # Unit tests: geocoding, places, filter

│   │   ├── test_agent.py        # Integration: full agent graph with mocks

│   │   └── test_api.py          # HTTP endpoint tests via AsyncClient

│   │

│   ├── .env                     # Your secrets (git-ignored)

│   ├── .env.example             # Template — copy to .env

│   ├── requirements.txt

│   ├── pytest.ini

│   └── Dockerfile

│

├── frontend/

│   ├── index.html

│   ├── src/

│   │   ├── main.tsx             # ReactDOM.createRoot entry point

│   │   ├── App.tsx              # Root: ErrorBoundary + ChatInterface

│   │   ├── index.css            # Tailwind directives + custom utilities

│   │   │

│   │   ├── components/

│   │   │   ├── ChatInterface.tsx      # Full chat UI: header, message list, input

│   │   │   ├── MessageBubble.tsx      # User / assistant message bubble

│   │   │   ├── RecommendationCard.tsx # Place card: rating, price, maps links

│   │   │   ├── LoadingIndicator.tsx   # Animated dots while streaming

│   │   │   └── ErrorBoundary.tsx      # React error boundary

│   │   │

│   │   ├── hooks/

│   │   │   ├── useChat.ts       # State: messages, isLoading, sendChat, clearChat

│   │   │   └── useStream.ts     # Low-level SSE reader hook

│   │   │

│   │   ├── services/

│   │   │   └── api.ts           # sendMessage(), sendMessageStream(), clearSession()

│   │   │

│   │   ├── types/

│   │   │   └── index.ts         # Place, ChatMessage, ChatRequest, ChatResponse, etc.

│   │   │

│   │   └── utils/

│   │       └── formatters.ts    # Rating stars, price symbols, distance formatting

│   │

│   ├── nginx.conf               # Prod Nginx: SPA routing, /api proxy, SSE support

│   ├── vite.config.ts           # Dev proxy to :8000, manual chunk splitting

│   ├── tailwind.config.js

│   ├── tsconfig.json

│   ├── package.json

│   └── Dockerfile               # Multi-stage: node builder → nginx:alpine

│

├── docker-compose.yml           # Dev: hot-reload backend + nginx frontend

├── docker-compose.prod.yml      # Prod: 4-worker uvicorn + nginx

├── cloudbuild.yaml              # GCP Cloud Build CI/CD pipeline

└── .github/

    └── workflows/

        ├── test.yml             # PR: lint + pytest on every push

        └── deploy.yml           # Push to main: build → push → Cloud Run deploy

```



---



## 5. Prerequisites



### Local development (without Docker)



| Requirement | Minimum Version | Check |

|-------------|----------------|-------|

| Python | 3.11 | `python --version` |

| Node.js | 20 | `node --version` |

| npm | 10 | `npm --version` |

| Git | any | `git --version` |



### Docker path



| Requirement | Version | Check |

|-------------|---------|-------|

| Docker Desktop (Windows/Mac) or Docker Engine (Linux) | 24+ | `docker --version` |

| docker-compose plugin | V2 | `docker compose version` |



---



## 6. Getting API Keys



The app needs three Google API keys for full functionality. All keys are obtained from [Google Cloud Console](https://console.cloud.google.com/).



> **Don't have keys?** See [Section 8](#8-mock-mode-no-api-keys-needed) to run with pre-canned mock data instead.



### Step-by-step



**1. Create a GCP project**



Go to https://console.cloud.google.com/ → New Project → give it a name.



**2. Enable the required APIs**



In your project, navigate to *APIs & Services → Library* and enable:

- **Places API (New)** — the modern Places API used by this app

- **Geocoding API** — converts address strings to coordinates

- **Generative Language API** — for Gemini models



**3. Create API keys**



*APIs & Services → Credentials → Create Credentials → API key*



You can use one key for all three APIs or create separate keys for each.



**Restrict your keys** (strongly recommended for production):

- Under *API restrictions*, select only the APIs each key needs

- Under *Application restrictions*, set allowed IPs or HTTP referrers



**4. Get a Gemini API key**



Either:

- Use the same Google Cloud key with *Generative Language API* enabled, **OR**

- Visit [Google AI Studio](https://aistudio.google.com/) → Get API key (simpler, free tier available)



**5. Set billing**



Google Places API (New) requires a billing account. The free tier gives $200/month credit, which covers ~10,000 Nearby Search calls. Enable billing at *Billing → Link a billing account*.



---



## 7. Local Development Setup



### Backend



```bash

# 1. Clone the repo

git clone https://github.com/your-org/ai-travel-agent.git

cd ai-travel-agent



# 2. Create and activate a virtual environment

cd backend

python -m venv .venv



# Windows (PowerShell)

.venv\Scripts\Activate.ps1



# macOS / Linux

source .venv/bin/activate



# 3. Install dependencies

pip install -r requirements.txt



# 4. Configure environment

cp .env.example .env

# Edit .env with your API keys (see Section 6) or leave as-is for mock mode

```



Your `backend/.env` should look like:



```env

GOOGLE_PLACES_API_KEY=AIzaSy...

GOOGLE_GEOCODING_API_KEY=AIzaSy...

GEMINI_API_KEY=AIzaSy...

GEMINI_MODEL=gemini-2.0-flash-001

ENVIRONMENT=development

LOG_LEVEL=INFO

MAX_RESULTS=20

DEFAULT_RADIUS_METERS=5000

SESSION_TTL_SECONDS=3600

CORS_ORIGINS=http://localhost:3000

USE_MOCKS=false

```



```bash

# 5. Start the backend (with hot reload)

uvicorn main:app --reload --port 8000

```



Verify it's running:

```bash

curl http://localhost:8000/api/v1/health

# → {"status":"ok","version":"1.0.0","uptime_seconds":...,"dependencies":{...}}

```



Interactive API docs: http://localhost:8000/docs



### Frontend



```bash

# Open a new terminal — keep backend running in the first one

cd frontend



# Install dependencies

npm install



# Start the dev server (proxies /api → localhost:8000)

npm run dev

```



Open http://localhost:3000. The Vite dev server proxies all `/api/*` and `/mcp/*` requests to the backend automatically, so no CORS issues during development.



---



## 8. Mock Mode (No API Keys Needed)



The app ships with a complete mock layer that substitutes all three external services with pre-canned data. This lets you run and develop the full UI/UX loop without any API keys or billing.



### Enable mock mode



In `backend/.env`:

```env

USE_MOCKS=true

```



Or set the default in `backend/config.py` (already set to `True` for new installs):

```python

use_mocks: bool = True

```



### What the mock layer provides



| Component | Mock behaviour |

|-----------|---------------|

| **Gemini LLM** | `MockLLM` in `mcp/tools/mock_data.py` — detects intent from prompt text and returns realistic JSON/text responses without any API call |

| **Google Geocoding** | `mock_geocode()` — returns real coordinates for known cities (Mumbai, Delhi, Bangalore, London, Paris, New York); random jitter for unknown locations |

| **Google Places API** | Returns 5 pre-built `PlaceResult` objects: The Rooftop Bistro ★4.6, Café Terraza ★4.3, Spice Garden ★4.7 (closed), The Coastal Kitchen ★4.4, Green Leaf Vegan ★4.2 |



### How to switch to real APIs



1. Add real API keys to `backend/.env`

2. Set `USE_MOCKS=false`

3. Restart uvicorn



The health endpoint shows which mode is active:

```json

{

  "status": "ok",

  "dependencies": {

    "google_places": "mocked",

    "google_geocoding": "mocked",

    "gemini": "mocked"

  }

}

```

vs `"configured"` when real keys are present and `USE_MOCKS=false`.



---



## 9. Environment Variables Reference



All variables are read from `backend/.env`. Set them as real environment variables in production (never commit `.env` with real keys).



| Variable | Required (real mode) | Default | Description |

|---|---|---|---|

| `GOOGLE_PLACES_API_KEY` | ✅ | `""` | Google Places API (New) key. Used in Nearby Search and Place Details calls. |

| `GOOGLE_GEOCODING_API_KEY` | ✅ | `""` | Google Geocoding API key. Converts address strings to lat/lng. |

| `GEMINI_API_KEY` | ✅ | `""` | Google Gemini API key. Used for intent extraction and response generation. |

| `GEMINI_MODEL` | — | `gemini-2.0-flash-001` | Gemini model version. `gemini-1.5-pro` also works. |

| `USE_MOCKS` | — | `true` | When `true`, all external APIs are replaced with mock data. Set `false` for real API calls. |

| `ENVIRONMENT` | — | `development` | `development` enables `/docs` and `/redoc`. `production` disables them. |

| `LOG_LEVEL` | — | `INFO` | Python log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

| `VERSION` | — | `1.0.0` | App version shown in health endpoint. |

| `MAX_RESULTS` | — | `20` | Maximum results requested from Places API. |

| `DEFAULT_RADIUS_METERS` | — | `5000` | Search radius around geocoded location (metres). |

| `SESSION_TTL_SECONDS` | — | `3600` | LangGraph MemorySaver session lifetime (seconds). |

| `CORS_ORIGINS` | — | `http://localhost:3000` | Comma-separated list of allowed CORS origins. In production: your frontend domain. |



### Frontend environment variables



Create `frontend/.env.local` for frontend overrides (Vite reads it automatically):



| Variable | Default | Description |

|---|---|---|

| `VITE_API_URL` | `/api/v1` | Backend API base URL. In production builds, set to the backend Cloud Run URL. |



Example for a production build pointing to a deployed backend:

```bash

VITE_API_URL=https://travel-agent-backend-xxxx-uc.a.run.app/api/v1 npm run build

```



---



## 10. Running with Docker



### Development (hot-reload)



```bash

# From the repo root

docker compose up --build

```



This starts:

- **backend** container: uvicorn with `--reload`, backend code volume-mounted for live edits

- **frontend** container: pre-built nginx serving the compiled React app



| Service | URL |

|---------|-----|

| Frontend | http://localhost:3000 |

| Backend API | http://localhost:8000 |

| Interactive docs | http://localhost:8000/docs |

| MCP tool list | http://localhost:8000/mcp/tools/list |

| Health check | http://localhost:8000/api/v1/health |



The backend `.env` file is read via `env_file: ./backend/.env` in `docker-compose.yml`.



To stop:

```bash

docker compose down

```



### Production



```bash

docker compose -f docker-compose.prod.yml up --build -d

```



Changes from dev compose:

- Backend: 4-worker uvicorn (`--workers 4`), no volume mount

- Frontend: same nginx image, port 80 exposed instead of 3000

- `restart: always` on both services

- `LOG_LEVEL=WARNING`



---



## 11. API Reference



### POST /api/v1/chat



Synchronous — returns after the full agent run completes.



```bash

curl -X POST http://localhost:8000/api/v1/chat \

  -H "Content-Type: application/json" \

  -d '{

    "message": "Find a rooftop bar in Bandra under ₹1500",

    "session_id": "user-abc-001"

  }'

```



Response:

```json

{

  "response": "Here are my top picks for rooftop bars in Bandra...",

  "places": [

    {

      "place_id": "ChIJmock_001",

      "name": "The Rooftop Bistro",

      "rating": 4.6,

      "price_level": 2,

      "price_symbol": "₹₹",

      "address": "14 Hill Road, Bandra West, Mumbai 400050",

      "lat": 19.0596,

      "lng": 72.8295,

      "photo_url": "https://places.googleapis.com/...",

      "is_open": true,

      "types": ["restaurant", "bar"],

      "total_ratings": 1240,

      "distance_meters": 350.5,

      "maps_url": "https://www.google.com/maps/place/?q=place_id:ChIJmock_001",

      "directions_url": "https://www.google.com/maps/dir/?api=1&destination_place_id:ChIJmock_001",

      "phone": "+91 22 2641 0000",

      "website": "https://example.com"

    }

  ],

  "session_id": "user-abc-001",

  "follow_up": "Would you like more details on any of these?",

  "turn_count": 1

}

```



### POST /api/v1/chat/stream



Streaming — returns Server-Sent Events. Use `Accept: text/event-stream`.



```bash

curl -N -X POST http://localhost:8000/api/v1/chat/stream \

  -H "Content-Type: application/json" \

  -H "Accept: text/event-stream" \

  -d '{"message": "Cafes in Indiranagar, Bangalore", "session_id": "sess-1"}'

```



SSE event types emitted (in order):



| Event type | Content | When |

|---|---|---|

| `places` | `Place[]` JSON array | After filter_and_rank_node completes |

| `token` | String (one word or phrase) | Streamed word-by-word from response text |

| `done` | `""` | Stream complete |

| `error` | Error message string | On agent exception |



### GET /api/v1/session/{session_id}



Returns the full conversation history for the session.



```bash

curl http://localhost:8000/api/v1/session/user-abc-001

```



### DELETE /api/v1/session/{session_id}



Clears a session (removes conversation history). The session ID can be reused immediately.



```bash

curl -X DELETE http://localhost:8000/api/v1/session/user-abc-001

```



### GET /api/v1/health



```bash

curl http://localhost:8000/api/v1/health

```



```json

{

  "status": "ok",

  "version": "1.0.0",

  "uptime_seconds": 3421.7,

  "environment": "development",

  "dependencies": {

    "google_places": "configured",

    "google_geocoding": "configured",

    "gemini": "configured"

  }

}

```



### GET /api/v1/place/{place_id}



Fetches detailed information for a single place (phone, website, hours).



```bash

curl http://localhost:8000/api/v1/place/ChIJN1t_tDeuEmsRUsoyG83frY4

```



### MCP Tool Server



```bash

# List available tools

curl http://localhost:8000/mcp/tools/list



# Call geocode tool

curl -X POST http://localhost:8000/mcp/tools/call \

  -H "Content-Type: application/json" \

  -d '{

    "jsonrpc": "2.0",

    "method": "geocode_location",

    "params": {"location_string": "Bandra West, Mumbai"},

    "id": "1"

  }'



# Call places search

curl -X POST http://localhost:8000/mcp/tools/call \

  -H "Content-Type: application/json" \

  -d '{

    "jsonrpc": "2.0",

    "method": "search_places",

    "params": {"query": "rooftop bar", "lat": 19.0596, "lng": 72.8295, "radius_meters": 2000},

    "id": "2"

  }'

```



---



## 12. Running Tests



```bash

cd backend



# Activate virtual environment first

.venv\Scripts\Activate.ps1        # Windows

source .venv/bin/activate          # macOS/Linux



# Run all tests (quiet summary)

python -m pytest tests/ -q



# Run with verbose output

python -m pytest tests/ -v



# Run specific test file

python -m pytest tests/test_tools.py -v

python -m pytest tests/test_agent.py -v

python -m pytest tests/test_api.py -v



# With coverage report

python -m pytest tests/ --cov=. --cov-report=term-missing



# HTML coverage report

python -m pytest tests/ --cov=. --cov-report=html

# Then open htmlcov/index.html

```



All tests run against mocks — no real API keys or network access required.



Test suite breakdown:



| File | What it tests |

|------|--------------|

| `test_tools.py` | `geocode_location`, `search_places`, `get_place_details`, `filter_and_rank_places` with mocked HTTP |

| `test_agent.py` | Full LangGraph graph: intent extraction → geocoding → search → filter → response, including follow-up turns |

| `test_api.py` | All FastAPI endpoints: `/chat`, `/chat/stream`, `/session`, `/health`, `/place/{id}` via `AsyncClient` |



---



## 13. Production Deployment — GCP Cloud Run



Cloud Run is the simplest deployment target — it scales to zero, handles HTTPS automatically, and charges per request.



### One-time setup



**1. Install and configure gcloud CLI**

```bash

# Install: https://cloud.google.com/sdk/docs/install

gcloud auth login

gcloud config set project YOUR_PROJECT_ID

```



**2. Enable required GCP APIs**

```bash

gcloud services enable \

  run.googleapis.com \

  cloudbuild.googleapis.com \

  containerregistry.googleapis.com \

  secretmanager.googleapis.com

```



**3. Store API keys in Secret Manager**

```bash

# Create secrets (one-time)

gcloud secrets create gemini-api-key --replication-policy=automatic

gcloud secrets create google-places-key --replication-policy=automatic

gcloud secrets create google-geocoding-key --replication-policy=automatic



# Add the actual key values

echo -n "YOUR_GEMINI_KEY" | gcloud secrets versions add gemini-api-key --data-file=-

echo -n "YOUR_PLACES_KEY" | gcloud secrets versions add google-places-key --data-file=-

echo -n "YOUR_GEOCODING_KEY" | gcloud secrets versions add google-geocoding-key --data-file=-

```



**4. Grant Cloud Run access to secrets**

```bash

PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")

SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"



gcloud secrets add-iam-policy-binding gemini-api-key \

  --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding google-places-key \

  --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding google-geocoding-key \

  --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"

```



### Manual deployment



```bash

PROJECT_ID=your-project-id

REGION=us-central1



# ── Backend ──────────────────────────────────────────────────────────



docker build -t gcr.io/$PROJECT_ID/travel-agent/backend:latest ./backend

docker push gcr.io/$PROJECT_ID/travel-agent/backend:latest



gcloud run deploy travel-agent-backend \

  --image=gcr.io/$PROJECT_ID/travel-agent/backend:latest \

  --region=$REGION \

  --platform=managed \

  --allow-unauthenticated \

  --set-env-vars="ENVIRONMENT=production,LOG_LEVEL=WARNING,USE_MOCKS=false" \

  --update-secrets="GEMINI_API_KEY=gemini-api-key:latest,GOOGLE_PLACES_API_KEY=google-places-key:latest,GOOGLE_GEOCODING_API_KEY=google-geocoding-key:latest" \

  --min-instances=0 \

  --max-instances=10 \

  --memory=512Mi \

  --cpu=1



BACKEND_URL=$(gcloud run services describe travel-agent-backend \

  --region=$REGION --format="value(status.url)")

echo "Backend: $BACKEND_URL"



# ── Frontend ─────────────────────────────────────────────────────────



docker build \

  --build-arg VITE_API_URL="$BACKEND_URL/api/v1" \

  -t gcr.io/$PROJECT_ID/travel-agent/frontend:latest \

  ./frontend

docker push gcr.io/$PROJECT_ID/travel-agent/frontend:latest



gcloud run deploy travel-agent-frontend \

  --image=gcr.io/$PROJECT_ID/travel-agent/frontend:latest \

  --region=$REGION \

  --platform=managed \

  --allow-unauthenticated \

  --min-instances=0 \

  --max-instances=5



FRONTEND_URL=$(gcloud run services describe travel-agent-frontend \

  --region=$REGION --format="value(status.url)")

echo "App is live at: $FRONTEND_URL"



# ── Update CORS so backend accepts frontend origin ────────────────────

gcloud run services update travel-agent-backend \

  --region=$REGION \

  --update-env-vars="CORS_ORIGINS=$FRONTEND_URL"

```



### Post-deployment verification



```bash

curl $BACKEND_URL/api/v1/health

curl -X POST $BACKEND_URL/api/v1/chat \

  -H "Content-Type: application/json" \

  -d '{"message": "Cafes in Mumbai", "session_id": "prod-test-1"}'

```



---



## 14. CI/CD — GitHub Actions



The repo includes two workflows in `.github/workflows/`:



### `test.yml` — runs on every push and pull request



1. Checkout code

2. Set up Python 3.11 → pip install → `pytest tests/ -v`

3. Set up Node 20 → `npm ci` → `tsc --noEmit` → `npm run build`



### `deploy.yml` — runs on push to `main` (after tests pass)



1. Build backend Docker image → push to GCR

2. `gcloud run deploy travel-agent-backend`

3. Build frontend Docker image (with `VITE_API_URL` set to backend URL) → push to GCR

4. `gcloud run deploy travel-agent-frontend`



### GitHub Secrets required



Add these in *Repository Settings → Secrets → Actions*:



| Secret | Value |

|--------|-------|

| `GCP_PROJECT_ID` | Your GCP project ID |

| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity Federation provider (recommended) |

| `GCP_SERVICE_ACCOUNT` | Service account email with Cloud Run + GCR permissions |



**Workload Identity Federation setup** (no long-lived keys stored in GitHub):

```bash

gcloud iam workload-identity-pools create "github-actions" \

  --project="$PROJECT_ID" --location="global"



gcloud iam workload-identity-pools providers create-oidc "github-provider" \

  --project="$PROJECT_ID" --location="global" \

  --workload-identity-pool="github-actions" \

  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \

  --issuer-uri="https://token.actions.githubusercontent.com"



PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \

  --project="$PROJECT_ID" \

  --role="roles/iam.workloadIdentityUser" \

  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions/attribute.repository/your-org/ai-travel-agent"

```



---



## 15. Troubleshooting



### Backend won't start



**`ModuleNotFoundError: No module named 'fastapi'`**

```bash

# Activate the virtual environment first

.venv\Scripts\Activate.ps1    # Windows

source .venv/bin/activate      # Linux/Mac

pip install -r requirements.txt

```



**`.env` file not found / settings error**

```bash

# The .env must be inside backend/, not the repo root

cd backend

cp .env.example .env

```



**Port 8000 already in use**

```bash

# Windows

netstat -ano | findstr :8000

taskkill /PID <PID_HERE> /F



# Linux/Mac

lsof -ti:8000 | xargs kill -9

```



---



### Frontend won't start



**TypeScript errors on `npm run dev`**

```bash

cd frontend

npm install

npx tsc --noEmit    # see the exact error list

```



**`Cannot find module 'vite/client'`**



Make sure the first line of `src/services/api.ts` is:

```ts

/// <reference types="vite/client" />

```



**Vite can't proxy to backend (Network Error)**



Ensure the backend is running on port 8000 first:

```bash

curl http://localhost:8000/api/v1/health

```



The proxy in `vite.config.ts` targets `http://localhost:8000`.



---



### Chat doesn't work in browser



**Send button stays disabled after typing**



The button condition is `disabled={!input.trim() || isLoading}`. After a response completes, it stays disabled only because the input is empty (expected behaviour — type something to re-enable it). If it's disabled with text showing, ensure the React `onChange` event fired (type manually in the browser, not via automation).



**"Network Error" or place cards missing**



Open browser DevTools → Network → find the `/api/v1/chat/stream` request:

- Response should contain `data: {"type":"places",...}` lines

- Check status code — non-200 usually means the backend is down or CORS is misconfigured



**Response appears but is generic ("Here are my top picks for [exact query]")**



This is expected in mock mode. The `MockLLM` generates a template response. Switch to `USE_MOCKS=false` with real API keys for location-specific answers.



---



### Docker issues



**`docker compose` not found**

```bash

# Use V2 plugin syntax (no hyphen)

docker compose up --build

# Not: docker-compose up

```



**Backend container exits immediately**

```bash

docker compose logs backend

```

Usually a missing or malformed `backend/.env`, or an import error.



**Frontend shows "502 Bad Gateway"**



The nginx proxy can't reach the backend. Check:

```bash

docker compose ps          # is backend healthy?

docker compose logs backend

```

The backend health check must pass before the frontend container starts (see `depends_on: condition: service_healthy`).



---



### Real API errors



**`INVALID_API_KEY` from Google**



The key doesn't exist or has a typo. Verify in GCP Console → APIs & Services → Credentials.



**`REQUEST_DENIED` from Places or Geocoding**



The API is not enabled for the project, or the key is restricted to different APIs:

- GCP Console → APIs & Services → Library → enable *Places API (New)* and *Geocoding API*

- Credentials → edit key → API restrictions → add both APIs



**Gemini `RESOURCE_EXHAUSTED` (429)**



Hit the free tier rate limit. Wait ~60 seconds. To reduce pressure: lower `MAX_RESULTS` in `.env`.



**Gemini key returns 403 despite being correct**



Check that *Generative Language API* is enabled:

```bash

curl "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY"

# Should list available models

```



---



## 16. Architecture Decisions



| Decision | Why |

|---|---|

| **LangGraph StateGraph** instead of a single LLM call | Explicit, debuggable multi-step pipeline. Each node has a single responsibility. Conditional routing handles missing locations, errors, and follow-ups without ad-hoc `if` chains in one giant prompt. |

| **MemorySaver checkpointer** | Zero-dependency in-process session persistence. For true multi-process or multi-instance deployments, swap to `AsyncRedisSaver` with one line change in `graph.py`. |

| **MCP as HTTP JSON-RPC router** | Avoids pip package naming conflicts with the official `mcp` SDK. The HTTP approach is compatible with MCP client libraries and allows the same tools to be called by the agent or by external clients. |

| **Gemini 2.0 Flash** | Best ratio of speed/cost/quality for structured-output tasks. Strong JSON instruction following, sub-second latency, generous free tier. |

| **SSE over WebSockets** | One-way (server → client) streaming is sufficient. SSE is simpler: no handshake protocol, reconnects automatically, works through standard HTTP proxies without special config. |

| **`fetch` for SSE instead of `EventSource`** | `EventSource` only supports GET requests. `POST` with a request body is required to send the chat message alongside the stream request. |

| **Haversine distance in Python** | Avoids an extra Distance Matrix API round-trip and cost. The formula is accurate to ~0.5% for city-scale distances and runs in microseconds. |

| **Tailwind CSS with JIT** | No CSS bundle at build time — only the classes actually used are included. Results in <5 KB of CSS in production. |

| **Vite manual chunk splitting** | Separates `react`/`react-dom` (vendor) and `axios` (http) into separate cached chunks. Users only re-download what changed between deploys. |

| **Non-root Docker user** | Security: backend runs as `appuser`, not root, limiting blast radius of any container escape. |



---



## 17. Security



| Practice | Implementation |

|---|---|

| **No secrets in source** | All keys in `backend/.env` (git-ignored) or GCP Secret Manager in production. Never baked into Docker images. |

| **Input validation** | Pydantic v2 models validate all request bodies and API responses at every boundary. |

| **Non-root container** | `adduser --system appuser` in backend Dockerfile — process runs without root privileges. |

| **CORS restriction** | Only origins listed in `CORS_ORIGINS` are allowed by FastAPI's CORSMiddleware. |

| **Docs hidden in production** | `docs_url=None, redoc_url=None` when `ENVIRONMENT=production`. |

| **API key restrictions** | Google API keys should be restricted to specific APIs and IPs/referrers in GCP Console. |

| **No keys in frontend** | Google API keys are used only server-side. The frontend only communicates with your own backend. |

| **Secret Manager injection** | In Cloud Run, secrets are injected as environment variables at container startup — they never appear in logs or image layers. |



---



## 18. Performance



| Optimization | Detail |

|---|---|

| **Async throughout** | All I/O is `async/await`: httpx for API calls, LangGraph for agent execution, FastAPI for request handling. No blocking threads. |

| **SSE word-by-word streaming** | Response text appears incrementally in the UI — users see output in under 1 second even for long responses. |

| **Distance ranking without extra API calls** | Haversine distance computed in Python after the Places search — avoids Distance Matrix API costs and latency. |

| **Vite code splitting** | `vendor` chunk (React) and `http` chunk (Axios) cached separately. Only the changed chunk re-downloads on deploy. |

| **Nginx gzip + immutable caching** | JS/CSS assets served with `Cache-Control: public, immutable, max-age=31536000`. Browser never re-requests unchanged assets. |

| **Multi-stage Docker build** | Frontend: node:20 builder → nginx:1.27-alpine. Final image is ~30 MB. |

| **Backend multi-worker** | Production compose runs `--workers 4` uvicorn processes, handling concurrent requests without GIL contention on I/O-bound work. |

| **tenacity retries** | Google API calls retry with exponential back-off on transient 429/503 errors — handles burst rate limiting gracefully. |

| **MemorySaver in-process** | No Redis round-trip for session state lookup in single-instance deployments. For horizontally-scaled deployments, replace with `AsyncRedisSaver`. |

