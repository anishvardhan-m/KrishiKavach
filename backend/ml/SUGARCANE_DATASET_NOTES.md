# Sugarcane Leaf Disease Dataset — Verified Local Facts

## Dataset Source
- **Name**: Sugarcane Leaf Disease Dataset
- **DOI**: [10.17632/9424skmnrk.1](https://data.mendeley.com/datasets/9424skmnrk/1)
- **Publisher**: Mendeley Data
- **Attribution**: Indian Biological Data Centre (IBDC) / Indian Biological Image Archive (IBIA)
- **Local archive**: `Sugarcane Leaf Disease Dataset.rar` (167 MB RAR5 archive)
- **Recovered extraction used for training**: `SugarcaneLeafDiseaseDataset_recovered/Sugarcane Leaf Disease Dataset/`

## Verified Class Counts (from local archive inspection)

| Class | Archive Total |
|---|---|
| Healthy | 522 |
| Mosaic | 462 |
| RedRot | 518 |
| Rust | 514 |
| Yellow | 505 |
| **TOTAL** | **2,521** |

The RAR archive itself is intact — all 2,521 JPEGs have non-zero `Size` headers in the archive.
A previous extraction produced 2,129 zero-byte files on disk (failed extraction, not
corrupt archive). The `SugarcaneLeafDiseaseDataset_recovered/` tree was re-extracted
with `unar` and contains 2,521 valid JPEGs and 0 zero-byte files.

## Recovered Dataset Layout

```
SugarcaneLeafDiseaseDataset_recovered/
└── Sugarcane Leaf Disease Dataset/
    ├── Healthy/   (522 .jpeg)
    ├── Mosaic/    (462 .jpeg)
    ├── RedRot/    (518 .jpeg)
    ├── Rust/      (514 .jpeg)
    └── Yellow/    (505 .jpeg)
```

## Training Details

### Model
- **Architecture**: MobileNetV2 (pretrained on ImageNet, fine-tuned)
- **Classes**: 5 (Healthy, Mosaic, RedRot, Rust, Yellow)
- **Image size**: 224×224
- **Epochs**: 3
- **Batch size**: 32
- **Validation split**: 20% (seed=42, stratified)
- **Optimizer**: AdamW (lr=1e-3, weight_decay=1e-4)
- **Best checkpoint saved** at epoch with highest val accuracy

### Training Data Distribution

| Class | Train | Validation | Archive Total |
|---|---|---|---|
| Healthy | 418 | 104 | 522 |
| Mosaic | 370 | 92 | 462 |
| RedRot | 414 | 104 | 518 |
| Rust | 411 | 103 | 514 |
| Yellow | 404 | 101 | 505 |
| **TOTAL** | **2,017** | **504** | **2,521** |

### Best Validation Accuracy

| Epoch | Train Loss | Val Accuracy |
|---|---|---|
| 1 | 0.5246 | 88.89% |
| 2 | 0.2409 | **91.47%** (best) |
| 3 | 0.1871 | 89.29% |

`backend/ml/artifacts/sugarcane_model.pt` was saved from the **epoch 2 weights** (the
best checkpoint), not the epoch 3 final state. After restoring best weights, the
re-evaluation reports 91.47% val accuracy (461/504).

### Per-Class Metrics (on validation set, best epoch)

| Class | Recall | Precision | F1 | TP/Total |
|---|---|---|---|---|
| Healthy | 77.88% | 98.78% | 87.10% | 81/104 |
| Mosaic | 100.00% | 76.03% | 86.38% | 92/92 |
| RedRot | 97.12% | 93.52% | 95.28% | 101/104 |
| Rust | 88.35% | 100.00% | 93.81% | 91/103 |
| Yellow | 95.05% | 94.12% | 94.58% | 96/101 |

Known confusion: Healthy ↔ Mosaic. Healthy recall is the lowest of the five classes
because some visually ambiguous healthy leaves are predicted as Mosaic. Mosaic
precision is the lowest because the model over-predicts Mosaic on borderline cases.

## Limitations

1. **Validation accuracy does NOT establish Maharashtra field performance**. Real
   field photos will differ in lighting, angle, background, and disease stage.
2. **Healthy ↔ Mosaic confusion is real**: ~22% of validation Healthy images are
   predicted as Mosaic. This is a model behavior, not an integration bug.
3. **Covers 5 Sugarcane leaf classes only** — does NOT cover other crops
   (cotton, soybean, rice, wheat, pigeon pea, tomato, pepper, potato, or any
   other Maharashtra crop).
4. **Class names are verbatim from the dataset folder names** (no disease
   ontology mapping performed).

## Router Integration
- `sugarcane_model.pt` in `backend/ml/artifacts/` (best-checkpoint weights, epoch 2)
- Entry in `MODEL_REGISTRY` in `backend/app/services/prediction.py`
- Class labels in `CLASS_DISPLAY` in `backend/app/services/prediction.py`
- Crop aliases: `sugarcane`, `ganna` (Hindi)
- Default `PREDICTION_MODE=demo` in `app/config.py`; set `PREDICTION_MODE=real` to
  use this model via the HTTP API

## Product Constraint
Per SIH26131 — Krishi Kavach is NOT a disease-classification demo. The Sugarcane
model is one component of: Image Evidence → Disease Probability → Context →
Risk Forecast → Recommendation → Expert Escalation → Follow-up → Outcome Feedback.
