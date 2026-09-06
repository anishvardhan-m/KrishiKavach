# ML Models for KrishiKavach

## Dataset Registry (Per Correction #1)

### PlantVillage Dataset
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

### Roboflow Multiclass Dataset
- **Location**: `/Plants Diseases Detection and Classification.v12i.multiclass/`
- **Total Images**: ~2516 (per README)
- **Note**: Cannot determine specific crop/disease labels without inspecting individual filenames or metadata
- **Use**: Requires further inspection to determine actual classes

### Weed Species Dataset
- **Location**: `/Individual Weed_Species/`
- **Purpose**: Weed identification (not crop disease)

### UAV/Dataset
- **Location**: `/UAV/`
- **Format**: Aerial imagery
- **Purpose**: Crop health monitoring from altitude

## ML Model Implications

**Per Correction #1: NO MISLABELING**

Available datasets contain:
- Tomato, Pepper, Potato diseases (PlantVillage)
- Unknown plant disease classes (Roboflow)
- Weed species
- Aerial/UAV imagery

**NO dataset** contains Maharashtra-specific major crops like:
- Rice (Oryza sativa)
- Cotton (Gossypium hirsutum) 
- Sugarcane (Saccharum officinarum)
- Soybean (Glycine max)
- Pigeon pea (Cajanus caban)
- Sorghum (Sorghum bicolor)
- Wheat (Triticum aestivum)

## Approach
For the foundation vertical slice:
1. Use PlantVillage tomato classes as representative examples
2. Return predictions with actual plant/disease names from the model
3. UI shows: "Detected: Late Blight on Tomato Plant" (truthful)
4. NEVER show: "Detected: Bollworm on Cotton" unless we have actual cotton/bollworm model
5. Architecture ready to swap in Maharashtra-specific models when available

Current implementation uses DemoPredictionService that clearly indicates it is for demonstration purposes only.