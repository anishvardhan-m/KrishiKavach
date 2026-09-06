"""Prediction service interface and implementations for KrishiKavach.

This module provides a clean abstraction over the crop-disease prediction pipeline.
Per SIH26131 — disease/pest detection must be accurate and evidence-based.

Per Correction #1 — we NEVER mislabel model outputs. Each prediction service
clearly indicates whether it is a REAL trained model or DEMO/seed behavior.

Architecture:
    PredictionService (ABC)
    ├── DemoPredictionService   <- default; marks output as DEMO
    └── RealPredictionService   <- loads the trained MobileNetV2 model
                                    (PlantVillage Tomato subset)

Usage:
    from app.services.prediction import get_prediction_service
    service = get_prediction_service()
    result = await service.predict(image_bytes=bytes, context={...})
"""
from __future__ import annotations

import json
import os
import random
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes for prediction output
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Disease severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class DiseasePrediction:
    """Output from the disease/pest prediction pipeline."""
    # The disease name as reported by the model (actual class label)
    disease: str
    # The crop the disease was detected on
    crop: str
    # Model confidence (0.0 – 1.0)
    confidence: float
    # Severity estimated from confidence and/or rules
    severity: Severity
    # True when confidence is below the uncertainty threshold
    uncertainty_flag: bool
    # Short human-readable description (may be localized)
    description: str
    # A simple URL-friendly slug for the disease
    disease_slug: str
    # Whether this prediction is from a REAL model or DEMO
    is_demo: bool = True
    # Human-readable label for UI badge
    model_source: str = "DemoPredictionService"
    # Top-2 alternatives (for expert referral if uncertainty is high)
    alternatives: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "disease": self.disease,
            "crop": self.crop,
            "confidence": round(self.confidence, 3),
            "severity": self.severity.value,
            "uncertainty_flag": self.uncertainty_flag,
            "description": self.description,
            "disease_slug": self.disease_slug,
            "is_demo": self.is_demo,
            "model_source": self.model_source,
            "alternatives": self.alternatives,
        }


# ---------------------------------------------------------------------------
# Recommendation data class
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    """Localized treatment/care recommendation for a disease prediction."""
    disease: str
    recommendation_text: str  # Primary recommendation (use this first)
    # Structured steps (step 1, step 2, ...)
    steps: list[str] = field(default_factory=list)
    # Warning / caution text (if any)
    warning: str | None = None
    # Whether expert escalation is recommended
    escalate: bool = False
    # Follow-up interval in calendar days
    follow_up_days: int = 7
    # Additional context (e.g., weather caveats)
    context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "disease": self.disease,
            "recommendation_text": self.recommendation_text,
            "steps": self.steps,
            "warning": self.warning,
            "escalate": self.escalate,
            "follow_up_days": self.follow_up_days,
            "context": self.context,
        }


# ---------------------------------------------------------------------------
# Prediction service interface
# ---------------------------------------------------------------------------

class PredictionService(ABC):
    """Abstract base for crop-disease prediction services."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the prediction service."""
        ...

    @property
    def is_demo(self) -> bool:
        """Return True if this service is a demo/seed implementation."""
        return False

    @abstractmethod
    async def predict(self, image_bytes: bytes, context: dict[str, Any]) -> DiseasePrediction:
        """Run disease/pest prediction on the given image.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG).
            context:      Additional context — may include:
                         - district: str
                         - crop_type: str
                         - crop_stage: str
                         - farmer_language: str

        Returns:
            DiseasePrediction with disease name, confidence, severity, etc.
        """
        ...

    @abstractmethod
    async def recommend(self, prediction: DiseasePrediction, context: dict) -> Recommendation:
        """Return a localized recommendation for a given prediction."""
        ...

    @abstractmethod
    def estimate_severity(self, confidence: float, disease: str) -> tuple[Severity, bool]:
        """Determine severity and uncertainty flag from confidence score.

        Returns:
            (severity, uncertainty_flag)
        """
        ...

    def _slugify(self, text: str) -> str:
        """Create a URL-friendly slug from disease name."""
        return text.lower().replace(" ", "-").replace("_", "-").replace("__", "-")


# ---------------------------------------------------------------------------
# Demo / Seed Prediction Service
# ---------------------------------------------------------------------------
# Per Correction #1 — this is CLEARLY MARKED as demo-only.
# It uses rule-based heuristics to simulate a prediction.
# It MUST NOT be presented as a trained ML model.
# ---------------------------------------------------------------------------

# PlantVillage-based disease catalog (from the actual dataset).
# These are REAL disease classes from the PlantVillage dataset.
PLANTVILLAGE_CATALOG: list[dict] = [
    {
        "disease": "Tomato Late Blight",
        "crop": "Tomato",
        "slug": "tomato-late-blight",
        "description": "Phytophthora infestans infection. Brown lesions on leaves and stems, white mold on leaf undersides in humid conditions.",
        "severity_hint": "high",
        "confidence_estimate": 0.87,
        "recommendation_text": "Apply a copper-based fungicide (e.g., copper hydroxide 77% WP at 2–3 g/L water) or a systemic fungicide such as metalaxyl. Remove and destroy severely infected plant parts. Ensure adequate plant spacing for airflow.",
        "steps": [
            "Remove severely infected leaves immediately.",
            "Spray copper-based fungicide at 2–3 g per litre of water.",
            "Repeat spray after 7 days if conditions persist.",
            "Reduce irrigation frequency and avoid wetting foliage.",
        ],
        "warning": "Do not apply systemic fungicides if harvest is within 14 days.",
        "escalate": False,
        "follow_up_days": 7,
    },
    {
        "disease": "Tomato Early Blight",
        "crop": "Tomato",
        "slug": "tomato-early-blight",
        "description": "Alternaria solani infection. Concentric rings (target spots) on older leaves, progressing upward.",
        "severity_hint": "medium",
        "confidence_estimate": 0.82,
        "recommendation_text": "Apply a protectant fungicide such as mancozeb (2.5 g/L) or chlorothalonil. Remove lower infected leaves. Practice crop rotation and avoid overhead irrigation.",
        "steps": [
            "Remove and destroy infected lower leaves.",
            "Spray mancozeb 75% WP at 2.5 g per litre of water.",
            "Repeat every 10–14 days.",
            "Avoid planting tomatoes in the same field for 2–3 seasons.",
        ],
        "warning": "Rotate fungicide classes to prevent resistance.",
        "escalate": False,
        "follow_up_days": 7,
    },
    {
        "disease": "Tomato Septoria Leaf Spot",
        "crop": "Tomato",
        "slug": "tomato-seeptoria-leaf-spot",
        "description": "Septoria lycopersici infection. Small dark spots with light centers and black pycnidia on leaves.",
        "severity_hint": "medium",
        "confidence_estimate": 0.79,
        "recommendation_text": "Apply a triazole or strobilurin fungicide. Remove infected plant debris after harvest. Use drip irrigation instead of overhead watering.",
        "steps": [
            "Remove spotted leaves carefully without shaking spores.",
            "Apply azoxystrobin or difenoconazole at recommended dose.",
            "Mulch around plants to reduce soil splash.",
            "Remove and burn plant debris at end of season.",
        ],
        "warning": None,
        "escalate": False,
        "follow_up_days": 7,
    },
    {
        "disease": "Tomato Bacterial Spot",
        "crop": "Tomato",
        "slug": "tomato-bacterial-spot",
        "description": "Xanthomonas vesicatoria infection. Small, dark, water-soaked spots that may have yellow halos on fruit and leaves.",
        "severity_hint": "high",
        "confidence_estimate": 0.85,
        "recommendation_text": "Apply copper-based bactericide (e.g., copper hydroxide) early in the season. Remove infected plants. Avoid working in the field when plants are wet.",
        "steps": [
            "Remove and destroy severely infected plants.",
            "Spray copper hydroxide at 2 g/L as a preventive.",
            "Do not work in wet fields to prevent spread.",
            "Use disease-free seeds and transplants.",
        ],
        "warning": "Repeated copper sprays can cause phytotoxicity.",
        "escalate": True,
        "follow_up_days": 5,
    },
    {
        "disease": "Tomato Yellow Leaf Curl Virus",
        "crop": "Tomato",
        "slug": "tomato-tylcv",
        "description": "Whitefly-transmitted virus. Severe leaf curling, yellowing, and stunting. Infected plants rarely produce fruit.",
        "severity_hint": "high",
        "confidence_estimate": 0.91,
        "recommendation_text": "There is no cure for TYLCV. Remove and destroy infected plants immediately. Control whitefly vectors with neem oil spray (5 ml/L). Use TYLCV-resistant tomato varieties in future plantings.",
        "steps": [
            "Remove and destroy all infected plants immediately.",
            "Spray neem oil 5 ml/L to control whitefly.",
            "Use yellow sticky traps to monitor whitefly.",
            "Plant TYLCV-resistant varieties next season.",
        ],
        "warning": "Do not compost infected plant material.",
        "escalate": True,
        "follow_up_days": 3,
    },
    {
        "disease": "Tomato Spider Mites",
        "crop": "Tomato",
        "slug": "tomato-spider-mites",
        "description": "Tetranychus urticae (two-spotted spider mite) infestation. Fine webbing on leaf undersides, stippled or bronzed leaves.",
        "severity_hint": "medium",
        "confidence_estimate": 0.76,
        "recommendation_text": "Spray with neem oil (5 ml/L) or spiromesifen. Increase humidity around plants. Introduce predatory mites (Phytoseiidae) if available.",
        "steps": [
            "Spray neem oil at 5 ml per litre of water.",
            "Repeat after 5 days if infestation persists.",
            "Increase watering frequency in dry conditions.",
            "Introduce predatory mites for biological control.",
        ],
        "warning": "Avoid spraying during peak sunlight hours.",
        "escalate": False,
        "follow_up_days": 5,
    },
    {
        "disease": "Tomato Leaf Mold",
        "crop": "Tomato",
        "slug": "tomato-leaf-mold",
        "description": "Passalora fulva infection. Pale greenish-yellow spots on upper leaf surface, brownish olive-green mold on undersides.",
        "severity_hint": "medium",
        "confidence_estimate": 0.80,
        "recommendation_text": "Improve greenhouse ventilation. Apply a protectant fungicide such as chlorothalonil or a systemic fungicide. Remove lower leaves to improve airflow.",
        "steps": [
            "Improve air circulation around plants.",
            "Apply chlorothalonil 72% SC at 2 ml/L.",
            "Remove heavily infected leaves.",
            "Maintain relative humidity below 85%.",
        ],
        "warning": None,
        "escalate": False,
        "follow_up_days": 7,
    },
    {
        "disease": "Tomato Target Spot",
        "crop": "Tomato",
        "slug": "tomato-target-spot",
        "description": "Corynespora cassiicola infection. Large brown target-like lesions on leaves, stems, and fruit.",
        "severity_hint": "medium",
        "confidence_estimate": 0.74,
        "recommendation_text": "Apply a combination of protectant and systemic fungicide. Practice crop rotation. Remove infected debris.",
        "steps": [
            "Apply mancozeb followed by a triazole fungicide.",
            "Remove severely infected plant parts.",
            "Rotate with non-solanaceous crops for 2 years.",
            "Avoid overhead irrigation.",
        ],
        "warning": "Rotate fungicide classes to prevent resistance.",
        "escalate": False,
        "follow_up_days": 7,
    },
    {
        "disease": "Tomato Mosaic Virus",
        "crop": "Tomato",
        "slug": "tomato-tobacco-mosaic-virus",
        "description": "Tobacco mosaic virus (TMOV) infection. Mottled light and dark green mosaic pattern on leaves, distorted leaf shape.",
        "severity_hint": "high",
        "confidence_estimate": 0.78,
        "recommendation_text": "Remove and destroy infected plants. Disinfect tools with 10% bleach solution. Do not smoke or handle tobacco near plants. Use TMV-resistant varieties.",
        "steps": [
            "Remove and destroy all infected plants.",
            "Disinfect tools with 10% bleach solution.",
            "Wash hands with soap before handling plants.",
            "Plant TMV-resistant varieties next season.",
        ],
        "warning": "TMV is highly stable and spread by contact.",
        "escalate": True,
        "follow_up_days": 5,
    },
    {
        "disease": "Potato Late Blight",
        "crop": "Potato",
        "slug": "potato-late-blight",
        "description": "Phytophthora infestans infection on potato. Water-soaked lesions on leaves that turn brown, white mold in humid conditions.",
        "severity_hint": "high",
        "confidence_estimate": 0.89,
        "recommendation_text": "Apply a contact fungicide such as mancozeb or a systemic fungicide such as metalaxyl immediately. Destroy infected foliage before harvest to prevent tuber infection.",
        "steps": [
            "Apply mancozeb 75% WP at 2.5 g/L immediately.",
            "For severe infection, use metalaxyl + mancozeb combination.",
            "Destroy infected foliage 2 weeks before harvest.",
            "Do not use infected tubers as seed.",
        ],
        "warning": "Late blight can destroy a potato crop within days.",
        "escalate": False,
        "follow_up_days": 5,
    },
    {
        "disease": "Potato Early Blight",
        "crop": "Potato",
        "slug": "potato-early-blight",
        "description": "Alternaria solani infection on potato. Dark brown lesions with concentric rings on older leaves.",
        "severity_hint": "medium",
        "confidence_estimate": 0.81,
        "recommendation_text": "Apply mancozeb or chlorothalonil as a protectant fungicide. Ensure adequate potassium nutrition. Practice crop rotation.",
        "steps": [
            "Spray mancozeb 75% WP at 2.5 g/L.",
            "Apply every 10–14 days as needed.",
            "Maintain balanced NPK fertilization.",
            "Rotate with non-solanaceous crops.",
        ],
        "warning": None,
        "escalate": False,
        "follow_up_days": 7,
    },
    {
        "disease": "Pepper Bacterial Spot",
        "crop": "Pepper",
        "slug": "pepper-bacterial-spot",
        "description": "Xanthomonas campestris pv. vesicatoria infection. Small water-soaked spots that become brown and raised on leaves and fruit.",
        "severity_hint": "medium",
        "confidence_estimate": 0.77,
        "recommendation_text": "Apply copper-based bactericide. Remove infected plants. Use disease-free seeds. Avoid overhead irrigation.",
        "steps": [
            "Spray copper hydroxide at 2 g/L.",
            "Remove and destroy severely infected plants.",
            "Use seeds treated with hot water or bleach.",
            "Avoid working in fields when plants are wet.",
        ],
        "warning": "Repeated copper use can cause phytotoxicity.",
        "escalate": False,
        "follow_up_days": 7,
    },
    {
        "disease": "Healthy",
        "crop": "Unknown",
        "slug": "healthy",
        "description": "No visible signs of disease or pest damage detected.",
        "severity_hint": "low",
        "confidence_estimate": 0.95,
        "recommendation_text": "The plant appears healthy. Continue regular monitoring and maintain good agricultural practices.",
        "steps": [
            "Continue regular watering and fertilization.",
            "Monitor plants weekly for any changes.",
            "Remove any yellowing or dead leaves.",
            "Ensure adequate spacing for airflow.",
        ],
        "warning": None,
        "escalate": False,
        "follow_up_days": 14,
    },
]

# Confidence thresholds for uncertainty flag
CONFIDENCE_CERTAIN = 0.80
CONFIDENCE_UNCERTAIN = 0.60


class DemoPredictionService(PredictionService):
    """Demo prediction service — RULE-BASED, NOT a trained ML model.

    Per Correction #1 — this service clearly marks all outputs as DEMO.
    It uses image hash-based selection from the PlantVillage catalog
    to produce consistent but fake predictions.

    For a REAL production deployment, replace this with RealPredictionService
    that loads an actual trained ONNX/Torch model.
    """

    def __init__(self, seed: int | None = 42):
        self._seed = seed

    @property
    def name(self) -> str:
        return "DemoPredictionService (Rule-Based — NOT a Trained ML Model)"

    @property
    def is_demo(self) -> bool:
        return True

    async def predict(self, image_bytes: bytes, context: dict[str, Any]) -> DiseasePrediction:
        """Produce a demo prediction using deterministic hash from image bytes."""
        # Deterministic selection based on image content hash
        hash_val = int(hashlib.md5(image_bytes[:8192]).hexdigest(), 16)
        rng = random.Random(hash_val)

        entry = rng.choice(PLANTVILLAGE_CATALOG)
        confidence = entry["confidence_estimate"]

        # Add small random variation to simulate model uncertainty
        confidence = round(
            max(0.5, min(0.98, confidence + rng.uniform(-0.05, 0.05))), 3
        )

        severity, uncertainty = self.estimate_severity(confidence, entry["disease"])

        # Build alternatives list (top-2 others)
        others = [e for e in PLANTVILLAGE_CATALOG if e["disease"] != entry["disease"]]
        alternatives = [
            {
                "disease": e["disease"],
                "crop": e["crop"],
                "confidence": round(e["confidence_estimate"] * rng.uniform(0.6, 0.9), 3),
            }
            for e in rng.sample(others, min(2, len(others)))
        ]

        return DiseasePrediction(
            disease=entry["disease"],
            crop=entry["crop"],
            confidence=confidence,
            severity=severity,
            uncertainty_flag=uncertainty,
            description=entry["description"],
            disease_slug=entry["slug"],
            is_demo=True,
            model_source="DemoPredictionService (Rule-Based — SIH Demo Only)",
            alternatives=alternatives,
        )

    async def recommend(self, prediction: DiseasePrediction, context: dict) -> Recommendation:
        """Return recommendation by matching the disease in the catalog."""
        entry = next(
            (e for e in PLANTVILLAGE_CATALOG if e["disease"] == prediction.disease),
            PLANTVILLAGE_CATALOG[-1],  # Healthy fallback
        )

        # Inject weather/soil context if available
        context_lines: list[str] = []
        if district := context.get("district"):
            context_lines.append(f"District: {district}")
        if soil_moisture := context.get("soil_moisture_percent"):
            context_lines.append(f"Soil moisture: {soil_moisture}%")

        context_str = " | ".join(context_lines) if context_lines else None

        return Recommendation(
            disease=prediction.disease,
            recommendation_text=entry["recommendation_text"],
            steps=entry.get("steps", []),
            warning=entry.get("warning"),
            escalate=entry.get("escalate", False),
            follow_up_days=entry.get("follow_up_days", 7),
            context=context_str,
        )

    def estimate_severity(
        self, confidence: float, disease: str
    ) -> tuple[Severity, bool]:
        """Determine severity and uncertainty from confidence score."""
        if confidence >= CONFIDENCE_CERTAIN:
            # Look up severity hint from catalog
            entry = next(
                (e for e in PLANTVILLAGE_CATALOG if e["disease"] == disease),
                None,
            )
            severity_hint = entry["severity_hint"] if entry else "medium"
            severity = Severity(severity_hint)
            uncertainty = False
        elif confidence >= CONFIDENCE_UNCERTAIN:
            severity = Severity.MEDIUM
            uncertainty = True
        else:
            severity = Severity.HIGH
            uncertainty = True

        return severity, uncertainty


# ---------------------------------------------------------------------------
# Real Prediction Service — trained MobileNetV2 on PlantVillage Tomato subset
# ---------------------------------------------------------------------------
# Per Correction #1 — this service honestly reports its domain:
#   "MobileNetV2 — PlantVillage Tomato"
# It MUST NOT be presented as covering other crops.
# ---------------------------------------------------------------------------

# Map PlantVillage folder class names to human-readable labels used by the
# existing PLANTVILLAGE_CATALOG. This is the ONLY mapping we perform — no
# class names are relabelled or reinterpreted; they are simply renamed for UI.
CLASS_DISPLAY: dict[str, dict[str, str]] = {
    "Tomato_Bacterial_spot":                {"disease": "Tomato Bacterial Spot", "crop": "Tomato", "slug": "tomato-bacterial-spot"},
    "Tomato_Early_blight":                  {"disease": "Tomato Early Blight", "crop": "Tomato", "slug": "tomato-early-blight"},
    "Tomato_Late_blight":                   {"disease": "Tomato Late Blight", "crop": "Tomato", "slug": "tomato-late-blight"},
    "Tomato_Leaf_Mold":                     {"disease": "Tomato Leaf Mold", "crop": "Tomato", "slug": "tomato-leaf-mold"},
    "Tomato_Septoria_leaf_spot":            {"disease": "Tomato Septoria Leaf Spot", "crop": "Tomato", "slug": "tomato-seeptoria-leaf-spot"},
    "Tomato_Spider_mites_Two_spotted_spider_mite": {"disease": "Tomato Spider Mites", "crop": "Tomato", "slug": "tomato-spider-mites"},
    "Tomato__Target_Spot":                  {"disease": "Tomato Target Spot", "crop": "Tomato", "slug": "tomato-target-spot"},
    "Tomato__Tomato_YellowLeaf__Curl_Virus": {"disease": "Tomato Yellow Leaf Curl Virus", "crop": "Tomato", "slug": "tomato-tylcv"},
    "Tomato__Tomato_mosaic_virus":          {"disease": "Tomato Mosaic Virus", "crop": "Tomato", "slug": "tomato-tobacco-mosaic-virus"},
    "Tomato_healthy":                       {"disease": "Healthy", "crop": "Unknown", "slug": "healthy"},
}


def _default_artifacts_dir() -> Path:
    """Locate the ml/artifacts directory relative to the backend root."""
    # backend/app/services/prediction.py -> backend/ml/artifacts
    return Path(__file__).resolve().parents[2] / "ml" / "artifacts"


class RealPredictionService(PredictionService):
    """Production prediction service — MobileNetV2 trained on PlantVillage Tomato.

    Per Correction #1 — this service must NEVER be used to make claims about
    crops outside its training domain. The model only recognises PlantVillage
    tomato leaf classes; for cotton, soybean, sugarcane, rice, wheat, pigeon
    pea, sorghum, or any other Maharashtra crop it returns an honest
    unsupported-crop signal (or no confident prediction).
    """

    IMAGE_SIZE = 224
    NORMALIZE_MEAN = (0.485, 0.456, 0.406)
    NORMALIZE_STD = (0.229, 0.224, 0.225)

    # Crops the model knows nothing about. If context.crop_type names one of
    # these, we refuse to return a tomato-disease label.
    UNSUPPORTED_CROPS: set[str] = {
        "cotton", "soybean", "soya", "sugarcane", "rice", "paddy",
        "wheat", "pigeon pea", "tur", "arhar", "sorghum", "jowar",
        "bajra", "maize", "corn", "onion", "grape", "apple", "cherry",
        "peach", "blueberry", "raspberry", "strawberry", "squash",
        "bell pepper", "pepper", "potato",
    }

    def __init__(
        self,
        model_path: str | os.PathLike[str] | None = None,
        class_index_path: str | os.PathLike[str] | None = None,
    ):
        artifacts_dir = _default_artifacts_dir()
        self._model_path = Path(model_path) if model_path else artifacts_dir / "tomato_model.pt"
        self._class_index_path = Path(class_index_path) if class_index_path else artifacts_dir / "tomato_class_index.json"
        self._model = None
        self._class_names: list[str] = []
        self._load_error: str | None = None
        self._load()

    @property
    def name(self) -> str:
        return "RealPredictionService (MobileNetV2 — PlantVillage Tomato)"

    @property
    def is_demo(self) -> bool:
        return False

    @property
    def model_source(self) -> str:
        return "MobileNetV2 — PlantVillage Tomato"

    @property
    def is_ready(self) -> bool:
        return self._model is not None and not self._load_error

    def _load(self) -> None:
        try:
            import torch
            from PIL import Image
        except ImportError as exc:
            self._load_error = (
                f"ML dependencies not installed ({exc}). "
                "Install torch + torchvision into the backend venv."
            )
            return

        if not self._model_path.is_file():
            self._load_error = (
                f"Model artifact not found at {self._model_path}. "
                "Run backend/ml/train_tomato.py to produce it."
            )
            return
        if not self._class_index_path.is_file():
            self._load_error = (
                f"Class index not found at {self._class_index_path}."
            )
            return

        try:
            with self._class_index_path.open() as f:
                self._class_names = json.load(f)
            self._model = torch.jit.load(
                str(self._model_path), map_location="cpu",
            )
            self._model.eval()
        except Exception as exc:
            self._load_error = f"Failed to load model: {exc}"
            self._model = None

    def _preprocess(self, image_bytes: bytes):
        """Load + preprocess image bytes to a (1, 3, 224, 224) tensor."""
        import torch
        from PIL import Image
        from torchvision import transforms
        from io import BytesIO

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        tf = transforms.Compose([
            transforms.Resize((self.IMAGE_SIZE, self.IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(self.NORMALIZE_MEAN, self.NORMALIZE_STD),
        ])
        tensor = tf(img).unsqueeze(0)
        return tensor

    def _infer(self, image_bytes: bytes) -> tuple[int, float, list[float]]:
        """Run model inference. Returns (top_index, top_conf, all_probs)."""
        import torch
        if not self.is_ready:
            raise RuntimeError(
                f"RealPredictionService is not ready: {self._load_error}"
            )
        x = self._preprocess(image_bytes)
        with torch.no_grad():
            logits = self._model(x)
        probs = torch.softmax(logits, dim=1)[0].tolist()
        top_idx = int(max(range(len(probs)), key=lambda i: probs[i]))
        return top_idx, float(probs[top_idx]), [float(p) for p in probs]

    def _is_unsupported_crop(self, context: dict) -> str | None:
        crop_type = (context.get("crop_type") or "").strip().lower()
        if crop_type and crop_type in self.UNSUPPORTED_CROPS:
            return crop_type
        return None

    def _unsupported_prediction(
        self, crop_type: str,
    ) -> DiseasePrediction:
        """Build a prediction that honestly says the model can't classify this."""
        return DiseasePrediction(
            disease="Unsupported crop (outside PlantVillage Tomato domain)",
            crop=crop_type.title(),
            confidence=0.0,
            severity=Severity.LOW,
            uncertainty_flag=True,
            description=(
                f"This model only recognises PlantVillage tomato leaf classes. "
                f"It has NOT been trained on '{crop_type}', and its predictions "
                f"for that crop would be unreliable. Please consult a local "
                f"agriculture extension officer for this crop."
            ),
            disease_slug="unsupported-crop",
            is_demo=False,
            model_source=self.model_source,
            alternatives=[],
        )

    async def predict(
        self, image_bytes: bytes, context: dict[str, Any],
    ) -> DiseasePrediction:
        if not self.is_ready:
            raise RuntimeError(
                f"RealPredictionService not available: {self._load_error}"
            )

        # Domain safety: refuse to fabricate predictions for unsupported crops.
        unsupported = self._is_unsupported_crop(context)
        if unsupported:
            return self._unsupported_prediction(unsupported)

        top_idx, top_conf, all_probs = self._infer(image_bytes)

        # Rank all classes for alternatives.
        ranked = sorted(
            enumerate(all_probs), key=lambda kv: kv[1], reverse=True,
        )

        primary_class = self._class_names[top_idx]
        display = CLASS_DISPLAY.get(primary_class)
        if display is None:
            # Defensive fallback — if a new class name appears in the model
            # index that we don't have a display label for, surface the raw
            # name rather than guessing.
            disease_name = primary_class.replace("Tomato_", "Tomato ").replace("_", " ")
            crop_name = "Tomato"
            slug = self._slugify(primary_class)
        else:
            disease_name = display["disease"]
            crop_name = display["crop"]
            slug = display["slug"]

        # Severity + uncertainty from confidence.
        severity, uncertainty = self.estimate_severity(top_conf, disease_name)

        # Catalog description if available.
        catalog_entry = next(
            (e for e in PLANTVILLAGE_CATALOG if e["disease"] == disease_name),
            None,
        )
        description = (
            catalog_entry["description"] if catalog_entry
            else f"Detected {disease_name} on {crop_name} (PlantVillage class)."
        )

        # Alternatives: top-K (excluding the top-1 itself).
        alternatives: list[dict] = []
        for idx, prob in ranked[1:4]:
            cls = self._class_names[idx]
            d = CLASS_DISPLAY.get(cls)
            alternatives.append({
                "disease": (d["disease"] if d else cls),
                "crop": (d["crop"] if d else "Tomato"),
                "confidence": round(prob, 4),
            })

        return DiseasePrediction(
            disease=disease_name,
            crop=crop_name,
            confidence=round(top_conf, 4),
            severity=severity,
            uncertainty_flag=uncertainty,
            description=description,
            disease_slug=slug,
            is_demo=False,
            model_source=self.model_source,
            alternatives=alternatives,
        )

    async def recommend(
        self, prediction: DiseasePrediction, context: dict,
    ) -> Recommendation:
        # If we refused to predict (unsupported crop), don't fabricate a
        # recommendation — direct the user to a human expert.
        if prediction.disease_slug == "unsupported-crop":
            return Recommendation(
                disease=prediction.disease,
                recommendation_text=(
                    "This image is outside the trained model domain. "
                    "Please consult your local agriculture extension officer "
                    "or a Krishi Vigyan Kendra (KVK) for diagnosis."
                ),
                steps=[
                    "Take a clear close-up photo of the affected leaf/plant.",
                    "Note the district, crop variety, and recent weather.",
                    "Visit the nearest KVK or call the Maharashtra agri helpline.",
                ],
                warning=(
                    "Do not apply pesticides based on unverified AI guesses."
                ),
                escalate=True,
                follow_up_days=1,
                context=(
                    f"District: {context.get('district')}"
                    if context.get("district") else None
                ),
            )

        # Match against the existing PlantVillage catalog so treatment
        # recommendations remain consistent with the demo service.
        entry = next(
            (e for e in PLANTVILLAGE_CATALOG if e["disease"] == prediction.disease),
            PLANTVILLAGE_CATALOG[-1],  # Healthy fallback
        )
        context_lines: list[str] = []
        if district := context.get("district"):
            context_lines.append(f"District: {district}")
        if soil_moisture := context.get("soil_moisture_percent"):
            context_lines.append(f"Soil moisture: {soil_moisture}%")
        context_str = " | ".join(context_lines) if context_lines else None

        return Recommendation(
            disease=prediction.disease,
            recommendation_text=entry["recommendation_text"],
            steps=entry.get("steps", []),
            warning=entry.get("warning"),
            escalate=entry.get("escalate", False),
            follow_up_days=entry.get("follow_up_days", 7),
            context=context_str,
        )

    def estimate_severity(
        self, confidence: float, disease: str,
    ) -> tuple[Severity, bool]:
        if confidence >= CONFIDENCE_CERTAIN:
            entry = next(
                (e for e in PLANTVILLAGE_CATALOG if e["disease"] == disease),
                None,
            )
            severity_hint = entry["severity_hint"] if entry else "medium"
            return Severity(severity_hint), False
        if confidence >= CONFIDENCE_UNCERTAIN:
            return Severity.MEDIUM, True
        return Severity.HIGH, True


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_prediction_service(mode: str = "demo") -> PredictionService:
    """Return the appropriate prediction service based on configuration.

    Args:
        mode: "demo" (default) or "real".
              Set PREDICTION_MODE env var or call with mode="real"
              to use the trained MobileNetV2 model.
    """
    if mode == "real":
        service = RealPredictionService()
        if not service.is_ready:
            raise RuntimeError(
                f"RealPredictionService is not ready: {service._load_error}. "
                "Either run ml/train_tomato.py or fall back to demo mode."
            )
        return service
    return DemoPredictionService()


async def predict_and_recommend(
    image_bytes: bytes,
    context: dict,
    mode: str = "demo",
) -> tuple[DiseasePrediction, Recommendation]:
    """Convenience function to run the full prediction + recommendation pipeline."""
    service = get_prediction_service(mode)
    prediction = await service.predict(image_bytes, context)
    recommendation = await service.recommend(prediction, context)
    return prediction, recommendation
