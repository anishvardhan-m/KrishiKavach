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

### 3. Weed Species Dataset
- **Location**: `/Individual Weed_Species/`
- **Format**: 16 weed species folders
- **Purpose**: Weed identification (not crop disease)

### 4. UAV/Dataset
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
- Clearly label predictions with actual plant/disease from model
- For demo purposes, we can show how the system would work with Maharashtra crops
- But NEVER claim a tomato disease model detects cotton diseases
- Architecture must be ready to swap in Maharashtra-specific models when available

## Recommended Initial Model Scope
For the foundation vertical slice, we will:
1. Train/use a model on PlantVillage tomato classes (largest representative set)
2. Return predictions like: "Tomato_Late_blight" with confidence
3. UI shows: "Detected: Late Blight on Tomato Plant"
4. NEVER show: "Detected: Bollworm on Cotton" (unless we have a cotton/bollworm model)
