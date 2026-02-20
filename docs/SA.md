# SA – Software Architecture: AI Food API

## 1. Tech Stack

| Thành phần | Công nghệ |
|-----------|-----------|
| Web Framework | FastAPI 0.115 + Uvicorn |
| AI / LLM | Google Gemini 2.0 Flash / Pro |
| Vector Search | FAISS (faiss-cpu) |
| Embedding | `intfloat/multilingual-e5-small` (dim=384) |
| Database | SQLite (per-city, read-only) |
| Language | Python 3.11+ |
| Deploy | Docker → Render + Cloudflare CDN |

---

## 2. Kiến Trúc 3 Tầng

```
┌────────────────────────────────────────────────┐
│  Layer 3: Routes  (FastAPI URL binding)        │
│  chat.py · search.py · ai.py · system.py       │
├────────────────────────────────────────────────┤
│  Layer 2: Handlers  (Orchestration)            │
│  ChatHandler · SearchHandler                   │
│  SuggestHandler · NearbyHandler                │
├────────────────────────────────────────────────┤
│  Layer 1: Core Services  (Business Logic OOP)  │
│  QueryRouter · SearchService                   │
│  GeminiService · SimpleQueryHandler            │
│  PromptBuilder                                 │
└────────────────────────────────────────────────┘
              ↓ async I/O
┌──────────────────────────────────────┐
│  Data Layer                         │
│  SQLite (food.db)  ·  FAISS index   │
└──────────────────────────────────────┘
```

---

## 3. OOP Class Design

### Layer 1 – Core Services

#### `QueryRouter` (`core/router.py`)
```
+ route(query: str, has_location: bool) → RouteDecision
+ get_meal_time(hour: int) → str
- _match_patterns(patterns, query) → bool
```

#### `SearchService` (`core/search.py`)
```
+ __init__(data_dir, model_name)
+ text_search(city, keyword, limit) → list[FoodItem]    [async]
+ semantic_search(city, query, top_k) → list[FoodItem]  [async]
+ hybrid_search(city, query, top_k) → list[FoodItem]    [async]
+ preload_all()
- _load_faiss(city) → faiss.Index
- _fetch_by_ids(city, ids) → list[FoodItem]
- _fetch_by_name(city, keyword, limit) → list[FoodItem]
```

#### `PromptBuilder` (`core/prompt.py`)
```
+ build_system(tier, city, hour, user_address?) → str
+ build_food_context(items) → str
+ build_history(raw) → list[dict]
+ trim_history(history, max_turns) → list[dict]
```

#### `GeminiService` (`core/gemini.py`)
```
+ __init__(api_key, prompt_builder)
+ chat(message, city, tier, max_tokens, ...) → str           [async]
+ stream(message, city, tier, max_tokens, ...) → AsyncIter   [async]
+ rank_nearby(items, user_address, city, query) → str        [async]
- _build_model(tier, system) → GenerativeModel
- _stream_worker(model, history, message, queue)
```

#### `SimpleQueryHandler` (`core/simple.py`)
```
+ handle(query, search_fn, hour) → (str, list[FoodItem], bool)  [async]
+ parse_intent(query) → (intent, keyword, keyword2?)
- _build_response(intent, keyword, items) → str
- _format_price(min, max) → str
```

### Layer 2 – Handlers

#### `ChatHandler` (`handlers/chat_handler.py`)
```
+ handle_rest(req: ChatRequest) → ChatResponse   [async]
+ handle_ws_message(data: dict, ws: WebSocket)   [async]
- _handle_simple(message, city, hour) → tuple    [async]
- _handle_gemini(message, req, decision) → tuple [async]
```

#### `SearchHandler`, `SuggestHandler`, `NearbyHandler` – tương tự.

### Dependency Injection (`deps.py`)
```python
# Singleton pattern – khởi tạo 1 lần khi startup
router   = QueryRouter()
search   = SearchService(DATA_DIR)
prompts  = PromptBuilder()
gemini   = GeminiService(API_KEY, prompts)
simple   = SimpleQueryHandler()
```

---

## 4. Data Flow

### UC1 – Simple Chat (REST)
```
POST /chat
  → ChatHandler.handle_rest()
    → QueryRouter.route()  [→ "local"]
    → SimpleQueryHandler.handle()
      → SearchService.hybrid_search()  [SQLite+FAISS]
      → template response
    → ChatResponse {reply, model_used="local", $0}
```

### UC3 – Nearby (REST)
```
POST /nearby
  → NearbyHandler.handle()
    → SearchService.hybrid_search() [top 15]
    → GeminiService.rank_nearby()
      → PromptBuilder.build_system()
      → Gemini Flash API call
    → NearbyResponse {reply, results}
```

### UC6 – Streaming (WebSocket)
```
WS /ws/chat  ← JSON frame
  → ChatHandler.handle_ws_message()
    → QueryRouter.route()
    → IF simple: SimpleQueryHandler → send_text()
    → ELSE: SearchService.hybrid_search()
           → GeminiService.stream()  [threading + Queue]
             → yield chunk → websocket.send_text(chunk)
           → send_json {done: true}
```

---

## 5. File Structure

```
e:\AI_online\
├── api/
│   ├── core/
│   │   ├── router.py          ≤ 100 lines
│   │   ├── search.py          ≤ 200 lines
│   │   ├── gemini.py          ≤ 200 lines
│   │   ├── simple.py          ≤ 180 lines
│   │   └── prompt.py          ≤ 100 lines
│   ├── handlers/
│   │   ├── chat_handler.py    ≤ 120 lines
│   │   ├── search_handler.py  ≤  60 lines
│   │   ├── suggest_handler.py ≤  80 lines
│   │   └── nearby_handler.py  ≤  60 lines
│   ├── routes/
│   │   ├── chat.py            ≤  50 lines
│   │   ├── search.py          ≤  30 lines
│   │   ├── ai.py              ≤  40 lines
│   │   └── system.py          ≤  20 lines
│   ├── deps.py                ≤  40 lines
│   ├── models.py              ≤  70 lines
│   └── main.py                ≤  40 lines
├── docs/
│   ├── BA.md
│   └── SA.md
├── tests/
│   ├── conftest.py
│   ├── test_router.py
│   ├── test_simple.py
│   ├── test_search.py
│   └── test_api.py
├── .env
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 6. Code Quality Rules
- **File:** ≤ 400 dòng
- **Method:** ≤ 20 dòng
- **Class:** Single Responsibility Principle (SRP)
- **Module:** 1 concern duy nhất
