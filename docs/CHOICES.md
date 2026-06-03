# Architectural Choices & AI Evaluations

This document details the engineering choices, options considered, AI suggestions, and final decisions made during the development of the Store Analytics platform.

---

## 1. Decision 1: Detection, Tracking, and Re-ID Model Selection

### Options Considered
1.  **YOLOv8 + ByteTrack + Simple Bounding Box Distance**: Heavy dependence on spatial tracking. Low computational overhead, but fails when customers leave the camera view and return (re-entry) or when camera fields of view overlap.
2.  **YOLOv8 + DeepSORT (using default Cosine Metric)**: Uses Kalman filtering and appearance descriptors. Better tracking, but the default feature extractor is trained on general person-reid datasets and performs poorly on low-resolution, face-blurred CCTV feeds.
3.  **YOLOv8 + ByteTrack + OSNet Re-ID Feature Extractor (Selected)**: Combines high-accuracy spatial tracking (ByteTrack) with a lightweight, specialized CNN model (OSNet) trained for person re-identification. Appearance embeddings (128-dimensional vectors) are extracted for each track and stored in a short-term gallery to match returning visitors.

### AI Suggestion
The AI suggested using a pure YOLOv8 detector combined with standard ByteTrack, and performing re-entry matching using simple bounding box distance thresholds. The AI argued this was easier to implement and run in real time.

### Final Choice & Rationale
We chose **Option 3: YOLOv8 + ByteTrack + OSNet**. 
Using spatial bounding box distance alone to resolve re-entry is fundamentally broken. If a customer exits the store to fetch a wallet from their car and returns 5 minutes later, their spatial coordinates are gone, causing the system to double-count them as a new visitor. This directly inflates the visitor count and artificializes a lower conversion rate. By matching OSNet appearance embeddings against a 20-minute cache of inactive visitors using cosine similarity, we resolve this "vendor re-entry" problem robustly.

### VLM Staff Detection & Zone Classification Evaluation

Uniform detection is highly challenging for standard object detection models because store uniforms change seasonally, and small details (like chest logos) are lost in blurred CCTV frames.

#### VLM Staff Detection Prompt
```text
You are an expert AI retail auditor. Analyze this cropped image of a person inside the store.
The official store staff uniform is:
- A royal blue polo shirt
- A small yellow logo emblem on the left chest
- Black or khaki trousers

Evaluate if this person is wearing the official staff uniform.

Response format MUST be raw JSON:
{
  "is_staff": true/false,
  "confidence": 0.0 to 1.0,
  "reasoning": "brief description of uniform markers found or missed"
}
```

#### Evaluation Cases

##### Success Case
-   **Input**: Bounding box crop of a person walking near the billing counter wearing a blue polo shirt and khaki pants under fluorescent lighting.
-   **VLM Response**: `{"is_staff": true, "confidence": 0.95, "reasoning": "Person is wearing a royal blue polo shirt matching uniform guidelines. A yellow emblem is visible on the left chest."}`
-   **Analysis**: The VLM correctly used visual reasoning to identify the logo emblem even at low resolution, which a standard YOLO classifier struggled with due to scaling.

##### Failure Case
-   **Input**: Bounding box crop of a customer wearing a blue rain jacket and carrying a bright yellow shopping bag close to their chest.
-   **VLM Response**: `{"is_staff": true, "confidence": 0.75, "reasoning": "Blue upper garment detected. A yellow color block (the bag) is close to the chest, misconstrued as the yellow chest emblem."}`
-   **Critique & Change Loop**: The VLM associated the yellow shopping bag with the chest emblem because the prompt lacked negative constraints. We updated the prompt to include:
    *   *Negative Constraint*: "Do not count accessories, shopping bags, or backpacks as part of the clothing. The yellow emblem must be a small stitched logo directly on the blue shirt fabric."
    *   *Result*: This eliminated false-positive staff detections, ensuring accurate customer metrics.

---

## 2. Decision 2: Event Schema Design

### Options Considered
1.  **Stateless Coordinates Stream**: Emit raw bounding boxes $(x_1, y_1, x_2, y_2)$ and track IDs on every frame. Ingest and perform tracking analysis at the API layer.
2.  **Simple Event Stream**: Emit only `ENTRY`, `EXIT`, and `ZONE_CHANGE` events.
3.  **Context-Rich Behavioral Event Stream (Selected)**: Emit stateful behavioral events (`ENTRY`, `EXIT`, `ZONE_ENTER`, `ZONE_EXIT`, `ZONE_DWELL`, `BILLING_QUEUE_JOIN`, `BILLING_QUEUE_ABANDON`, `REENTRY`) with metadata like `dwell_ms`, `queue_depth`, and `is_staff`.

### AI Suggestion
The AI suggested Option 1, arguing that offloading all state logic to the backend database kept the edge pipeline simple and stateless.

### Final Choice & Rationale
We chose **Option 3**.
Emitting frame-level coordinate streams over the network introduces massive bandwidth and DB write bottlenecks (15 frames per second * 10 people * 40 stores = 6,000 requests/sec). Moving state-machine calculations (e.g. dwell time thresholds, queue joins) to the edge pipeline allows us to emit a thin, meaningful stream of events only when state transitions occur. This reduces network payload sizes by **99.9%** and offloads CPU-bound spatial tracking calculations from the API database.

---

## 3. Decision 3: API Ingestion and Session Aggregation

### Options Considered
1.  **Append-Only Event Logging**: Store all events in a single relational table and query metrics dynamically via complex SQL joins.
2.  **State-Machine Table Upserts (Selected)**: Upsert incoming events directly into a stateful `visitor_sessions` table, maintaining an active cache of current visits.

### AI Suggestion
The AI recommended Option 1, citing ease of database replication and clean horizontal write scalability of append-only tables.

### Final Choice & Rationale
We chose **Option 2**.
For analytical endpoints (like `/funnel` and `/metrics`), running aggregates on raw logs in real time degrades API performance. By maintaining the `visitor_sessions` table, the `/events/ingest` endpoint updates session details (e.g. increments `re_entry_count` on a `REENTRY` event, calculates total session duration, and flags `queue_joined = True` on `BILLING_QUEUE_JOIN`). Endpoints retrieve these computed properties instantly without scanning millions of event logs.

---

## 4. Scale Analysis: What Breaks at Scale?

If we scale this system to **40 stores** sending events in real time:

### Bottleneck 1: Database Write Lock Contentions
-   **What Breaks**: With SQLite, concurrent database writes from multiple edge nodes will cause `database is locked` errors (SQLITE_BUSY) because SQLite only supports single-writer operations.
-   **Resolution**: Replace SQLite with PostgreSQL. Implement an event broker (e.g., Redis or Kafka) in front of the API ingestion endpoint to buffer event batches and write them asynchronously via worker threads.

### Bottleneck 2: Network Latency & API Overload during Peak Hours
-   **What Breaks**: Edge nodes calling `POST /events/ingest` individually for every event will overload the FastAPI server.
-   **Resolution**: Implement **batch-and-flush** logic at the edge. The pipeline will queue events locally and transmit them in batches of 100 or every 10 seconds.

### Bottleneck 3: VLM API Cost & Latency
-   **What Breaks**: Invoking cloud VLMs (Claude/GPT-4V) for every new visitor will lead to thousands of dollars in API bills and network latency (often 2–5 seconds per request).
-   **Resolution**: Run a lightweight local uniform classification model (e.g. MobileNet or YOLOv8 trained specifically on uniform vs non-uniform classes) at the edge, using the cloud VLM only for low-confidence calibration samples.
