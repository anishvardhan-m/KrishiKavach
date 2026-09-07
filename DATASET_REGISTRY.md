# KrishiKavach Dataset Registry

## Available Image Datasets

### 1. PlantVillage Dataset (Primary)
- **Location**: `/PlantVillage/PlantVillage/`
- **Format**: Organized in subfolders by `<plant>___<disease>` or `<plant>___healthy`
- **Actual Classes Present** (with image counts):
  - Pepper__bell___Bacterial_spot: 997 images
  - Pepper__bell___healthy: 1478 images  
  - Potato___Early_blight: 1000 images
  - Potato___Late_blight: 1000 images
  - Potato___healthy: 152 images
  - Tomato_Bacterial_spot: 2127 images
  - Tomato_Early_blight: 1000 images
  - Tomato_Late_blight: 1911 images
  - Tomato_Leaf_Mold: 954 images
  - Tomato_Septoria_leaf_spot: 1773 images
  - Tomato_Spider_mites_Two_spotted_spider_mite: 1678 images
  - Tomato__Target_Spot: 1406 images
  - Tomato__Tomato_YellowLeaf__Curl_Virus: 3211 images
  - Tomato__Tomato_mosaic_virus: 375 images
  - Tomato_healthy: 1593 images

### 2. Roboflow Multiclass Dataset
- **Location**: `/Plants Diseases Detection and Classification.v12i.multiclass/`
- **Format**: Flat folder with train/valid/test splits
- **Total Images**: ~2516 (per README)
- **Classes**: Multi-class classification (specific classes not enumerated in flat structure)
- **Note**: Cannot determine specific crop/disease labels without inspecting individual filenames or metadata

### 3. Sugarcane Leaf Disease Dataset
- **Location (recovered)**: `/SugarcaneLeafDiseaseDataset_recovered/Sugarcane Leaf Disease Dataset/`
- **Archive**: `Sugarcane Leaf Disease Dataset.rar` (167 MB RAR5)
- **Format**: Organized in subfolders by class name
- **Classes** (verified counts from archive — all 2,521 images readable in the recovered extraction):
  - Healthy: 522
  - Mosaic: 462
  - RedRot: 518
  - Rust: 514
  - Yellow: 505
- **Total archive**: 2,521 images
- **Model**: Trained model at `backend/ml/artifacts/sugarcane_model.pt`
- **Notes**:
  - The RAR archive is intact (all 2,521 entries have non-zero `Size`).
  - The previously-checked-in `SugarcaneLeafDiseaseDataset/` extraction is NOT
    used for training — a failed extraction left 2,129 zero-byte files. Use
    `SugarcaneLeafDiseaseDataset_recovered/` instead.
  - See `backend/ml/SUGARCANE_DATASET_NOTES.md` for full per-class metrics.

### 4. Weed Species Dataset
- **Location**: `/Individual Weed_Species/`
- **Format**: 16 weed species folders
- **Purpose**: Weed identification (not crop disease)

### 5. UAV/Dataset
- **Location**: `/UAV/`
- **Format**: Aerial imagery (likely for field-level analysis)
- **Purpose**: Crop health monitoring from altitude

### 5. Tabular Data (Environmental)
- **Location**: `/data/`
  - `soil_moisture.csv`: District-level soil moisture for Maharashtra (697k rows)
  - `evapotranspiration.csv`: District-level evapotranspiration for Maharashtra (502k rows)

## ML Model Implications

**Per Correction #1: NO MISLABELING**

Given the available datasets:
1. **PlantVillage** provides validated tomato, pepper, and potato disease classifications
2. **Roboflow dataset** appears to be plant disease classification but specific classes unknown without deeper inspection
3. **No dataset** contains Maharashtra-specific major crops like:
   - Rice (Oryza sativa)
   - Cotton (Gossypium hirsutum) 
   - Sugarcane (Saccharum officinarum)
   - Soybean (Glycine max)
   - Pigeon pea (Cajanus caban)
   - Sorghum (Sorghum bicolor)
   - Wheat (Triticum aestivum)

**Approach for Foundation**:
- Use PlantVillage dataset for tomato/pepper/potato disease detection as-is
- Use Sugarcane Leaf Disease Dataset for sugarcane disease detection (with known limitations)
- Clearly label predictions with actual plant/disease from model
- For demo purposes, we can show how the system would work with Maharashtra crops
- But NEVER claim a tomato disease model detects cotton diseases
- Architecture must be ready to swap in Maharashtra-specific models when available

## Trained Models Summary

| Crop | Dataset | Classes | Valid Images | Val Accuracy |
|---|---|---|---|---|
| Tomato | PlantVillage | 11 | 16,011 | 97.63% |
| Pepper | PlantVillage | 2 | 2,475 | 99.60% |
| Potato | PlantVillage | 3 | 2,152 | 99.77% |
| Sugarcane | Sugarcane Leaf Disease | 5 | 2,521 | 91.47% |

**Note**: Sugarcane validation accuracy (91.47%, best epoch 2) is NOT representative
of Maharashtra field performance. Field photos will differ in lighting, angle,
background, and disease stage. Known confusion: Healthy ↔ Mosaic (~22% of
validation Healthy images are predicted as Mosaic). See
`backend/ml/SUGARCANE_DATASET_NOTES.md` for per-class precision/recall/F1.

## Recommended Initial Model Scope
For the foundation vertical slice, we will:
1. Train/use a model on PlantVillage tomato classes (largest representative set)
2. Return predictions like: "Tomato_Late_blight" with confidence
3. UI shows: "Detected: Late Blight on Tomato Plant"
4. NEVER show: "Detected: Bollworm on Cotton" (unless we have a cotton/bollworm model)
