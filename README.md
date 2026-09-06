# KrishiKavach — SIH26131

Voice-first AI crop-health and early-warning system for Maharashtra farmers.

## Scope

First vertical slice: farmer uploads a photo of a sick crop → gets a diagnosis → receives a localized treatment recommendation → can escalate to an expert.

## Architecture

```
frontend/   Vite + React + TypeScript   (port 5173)
backend/    FastAPI + SQLAlchemy         (port 8000)
ml/         Dataset registry + model specs
data/       Environmental CSV data (Maharashtra districts)
```

- **Frontend** proxies `/api/*` → `http://localhost:8000` via Vite dev server.
- **Backend** stores cases and farmer data in SQLite (dev) or PostgreSQL/PostGIS (prod).
- **Prediction** is handled by a `DemoPredictionService` (rule-based) in this demo build. A `RealPredictionService` stub is in place for when a trained ML model is available.

## How to Run

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## Demo Limitations

### ⚠️ DEMO PREDICTION — NOT A TRAINED ML MODEL

The current prediction endpoint (`POST /api/predict`) uses `DemoPredictionService`, a **rule-based, deterministic hash-based demo**. It is:

- **NOT** a trained deep-learning model.
- **NOT** a validated Maharashtra crop classifier.
- Clearly marked `is_demo: true` and `model_source: "DemoPredictionService"` in every response.

Available classes are limited to tomato, potato, and pepper diseases from the PlantVillage dataset. The system is **NOT** trained on Maharashtra major crops (rice, cotton, sugarcane, soybean, etc.).

Real ML inference requires loading a trained ONNX/Torch model into `RealPredictionService`.

### Voice Limitation

Voice interaction uses the browser's **Web Speech API** (SpeechSynthesis + SpeechRecognition). This is available in Chrome/Edge desktop. It is **not available** in Firefox or iOS Safari. The UI degrades gracefully — buttons still work without voice.
