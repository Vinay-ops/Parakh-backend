# ML Integration Contract

This document describes the **implemented** legal-metrology ML/OCR pipeline integrated into the Parakh backend.

**IMPORTANT:** This describes the **actual implementation**, not a placeholder. The pipeline uses PaddleOCR for OCR, OpenCV for preprocessing, and a rules-based compliance engine evaluating against real Indian Legal Metrology Act requirements.

---

## 1. Architecture Overview

**Pipeline per inspection side:**
```
Raw image bytes (from Supabase Storage)
    ↓ OpenCV preprocessing (GaussianBlur + contrast enhancement)
    ↓ PaddleOCR (text detection + recognition)  
    ↓ OCRParser (structured {text, confidence, bounding_box} list)
    ↓ InformationExtractor (field extraction using extraction_schema.json)
```

**Multi-side processing:**
```
Multiple side results
    ↓ Confidence-based merging (highest confidence wins)
    ↓ Product information mapping
    ↓ Legal Metrology Rule Engine (legal_metrology_rules.csv)
    ↓ Final compliance verdict + per-rule results
```

## 2. Integration Point

**File:** `backend/services/ml_service.py`

**Main function:**
```python
def process_inspection(inspection_id: str, side_images: list[tuple[str, str]]) -> dict:
```

- **Input:** 
  - `inspection_id`: Public INSP-... identifier for logging
  - `side_images`: List of `(side_label, local_file_path)` tuples
- **Output:** Dict matching `ML_RESULT_SCHEMA`
- **Dependencies:** `paddlepaddle>=2.6.0`, `paddleocr>=2.9.1`, `opencv-python-headless>=4.9.0.80`

**Error handling:**
- Raises `MLNotIntegratedError` if dependencies not installed
- Raises `ValueError` for image decode failures or invalid input
- Non-fatal extraction failures on individual sides are logged but processing continues

## 3. Model Details

**OCR Engine:** PaddleOCR v2.9.1+
- **Language:** English (`lang="en"`)
- **Architecture:** Text detection + recognition pipeline
- **Loading:** Singleton initialization (loaded once at module import)
- **Runtime:** CPU by default (uses `paddlepaddle`); GPU via `paddlepaddle-gpu` if available

**Preprocessing:** OpenCV-based
- Gaussian blur (3×3 kernel) for denoising  
- Contrast enhancement (alpha=1.2, beta=0)
- No resizing or cropping — preserves original image dimensions

**Text extraction:** Structured output per token:
```json
{
  "text": "extracted text",
  "confidence": 0.95,
  "bounding_box": [x1, y1, x2, y2],
  "source_side": "front"
}
```

## 4. Field Extraction

**Schema:** `legal-metrology/data/rules/extraction_schema.json`

**Supported fields:**
- **Roles:** manufacturer, packer, importer, marketed_by, manufactured_for
- **Standard fields:** mrp, net_quantity, address, manufacturing_or_packing_date, expiry_or_use_by_date, consumer_care, other_declarations

**Extraction method:**
1. **Label matching:** Fuzzy matching against predefined labels (e.g., "MRP", "Mfg Date")  
2. **Geometric search:** Find values near detected labels using bounding box proximity
3. **Value validation:** Type-specific validation (currency for MRP, quantity patterns, etc.)
4. **Same-line extraction:** Parse values directly after labels in the same OCR token

## 5. Multi-side Merging

**Merging rule (deterministic):**
- For each field, keep the value with the **highest OCR confidence** across all sides
- Missing confidence defaults to 0.5 (below scored detections, above 'not found')
- **No arbitrary overwriting** — confidence-based precedence ensures reproducible results

**Example:**
```
Front side: MRP ₹50 (confidence: 0.7)
Back side:  MRP ₹50.00 incl. taxes (confidence: 0.92)
→ Result: "₹50.00 incl. taxes" (higher confidence)
```

## 6. Output Mapping

**Target schema:** `ML_RESULT_SCHEMA.product_information`
```json
{
  "common_product_name": "string | null",
  "manufacturer_name": "string | null", 
  "manufacturer_address": "string | null",
  "packer_name": "string | null",
  "packer_address": "string | null", 
  "importer_name": "string | null",
  "importer_address": "string | null",
  "multi_product_names": [],
  "multi_product_quantities": [],
  "net_quantity_value": "float | null",
  "net_quantity_unit": "string | null",
  "number_count": "int | null",
  "mrp": "float | null",
  "mrp_tax_wording": "string | null", 
  "manufacture_or_import_date": "string | null",
  "consumer_care_name": "string | null",
  "consumer_care_address": "string | null",
  "consumer_care_phone": "string | null",
  "consumer_care_email": "string | null",
  "commodity_dimensions": "string | null"
}
```

**Field parsing:**
- **Numeric extraction:** Regex-based (`[\d]+(?:[.,]\d+)?`)
- **Unit extraction:** Pattern matching for standard SI units (kg, g, ml, l, etc.)
- **Contact parsing:** Phone/email extraction from consumer care text
- **Currency parsing:** Amount extraction from MRP strings

## 7. Compliance Engine

**Rules source:** `legal-metrology/data/rules/legal_metrology_rules.csv`
- **19 rules** from Indian Legal Metrology (Packaged Commodities) Rules, 2011
- **Rule types:** Required declarations, MRP format, net quantity, manufacturing date, etc.

**Rule evaluation:**
```python
def evaluate_rule(rule, extracted, ocr_data, ocr_text) -> dict:
```

**Rule categories:**
- **`manual`:** Physical verification required (font sizes, contrast, etc.)
- **`mrp`:** MRP presence + tax-inclusive wording detection
- **`quantity`:** Net quantity value + standard unit validation  
- **`manufacturer`:** Manufacturer/packer/importer name + address
- **`product_name`:** Generic product name presence
- **`date`:** Manufacturing/packing date format validation
- **`consumer_care`:** Consumer care contact details
- **`quantity_modifier`:** Prohibited words (minimum, approximately, etc.)

**Status mapping:**
- **`COMPLIANT`** → `PASS`
- **`VIOLATION`** → `FAIL` 
- **`VERIFY`** → `VERIFY` (human verification needed)
- **`MANUAL`** → `VERIFY`

## 8. Final Compliance Verdict

**Overall status logic:**
- **`NON_COMPLIANT`:** Any rule fails OR any rule needs verification
- **`COMPLIANT`:** All rules pass
- **Conservative approach:** Unverified ≠ compliant

**Score calculation:**
```python
score = pass_count / total_rules
```

**Rule output:**
```json
{
  "rule_name": "Rule 6(1)(c) - Net Quantity",
  "status": "PASS | FAIL | VERIFY", 
  "reason": "Numeric net quantity and standard unit detected",
  "required_value": "Net quantity with SI units",
  "detected_value": null,
  "bounding_box": {"x1": 100, "y1": 200, "x2": 300, "y2": 250}
}
```

## 9. Backend Integration

**Call flow in `POST /api/inspections/{id}/process`:**

1. Fetch inspection + validate all required sides uploaded
2. Download images from Supabase Storage to temp files  
3. Call `ml_service.process_inspection(inspection_id, side_images)`
4. Validate result via `ml_service.validate_result()`
5. Persist via `inspection_service.apply_ml_result()`
6. Update inspection status → `EXTRACTED` or `COMPLIANCE_READY` or `COMPLIANT`/`NON_COMPLIANT`
7. Clean up temp files

**Status progression:**
```
CREATED → CAPTURING → PROCESSING → EXTRACTED → COMPLIANCE_READY → COMPLIANT/NON_COMPLIANT
                                                ↓
                                              FAILED (on errors)
```

## 10. Error Handling

**Dependency errors:**
- `MLNotIntegratedError` if PaddleOCR/OpenCV not installed
- Graceful degradation: backend starts but `/process` endpoint returns error

**Runtime errors:**
- Image decode failures → `ValueError` 
- Individual side failures → logged, processing continues with remaining sides
- Complete failure → inspection marked as `FAILED`

**No fake fallbacks:**
- Missing fields return `null`
- Failed OCR returns empty token list
- Rule evaluation errors marked as `VERIFY`
- **Never fabricate data**

## 11. Testing

**Test image:** `legal-metrology/data/input/image.png`
- Real package image for end-to-end validation

**Verification steps:**
1. PaddleOCR produces non-empty token list
2. Information extraction finds some fields  
3. Rule engine evaluates without crashing
4. Output conforms to `ML_RESULT_SCHEMA`
5. Database persistence succeeds

## 12. Deployment Requirements

**Runtime dependencies:**
```txt
paddlepaddle>=2.6.0      # CPU inference
paddleocr>=2.9.1         # OCR pipeline  
opencv-python-headless>=4.9.0.80  # Image preprocessing
```

**GPU support (optional):**
- Replace `paddlepaddle` with `paddlepaddle-gpu` for CUDA acceleration
- Requires CUDA-compatible GPU + drivers

**Model initialization:**
- PaddleOCR downloads models on first use (~100MB)
- Models cached in `~/.paddleocr/` 
- Initialization takes ~10-30 seconds on first import
- Subsequent requests are fast (inference only)

**Resource usage:**
- **RAM:** ~1-2GB for PaddleOCR model
- **CPU:** Moderate during inference
- **Disk:** ~100MB for cached models

## 13. Source Layout

```
26034/
├── backend/services/ml_service.py           ← Integration point
├── legal-metrology/                         ← ML pipeline source
│   ├── src/
│   │   ├── ocr/
│   │   │   ├── ocr_engine.py               ← PaddleOCR wrapper
│   │   │   ├── ocr_parser.py               ← Token parsing  
│   │   │   └── image_processor.py          ← OpenCV preprocessing
│   │   ├── extraction/
│   │   │   └── extractor.py                ← Field extraction logic
│   │   └── rules/
│   │       └── rule_engine.py              ← Compliance evaluation
│   └── data/
│       ├── rules/
│       │   ├── extraction_schema.json      ← Field definitions
│       │   └── legal_metrology_rules.csv   ← Compliance rules
│       └── input/
│           └── image.png                   ← Test image
```

**Import mechanism:**
- `ml_service.py` adds `legal-metrology/src/*` to `sys.path`
- Direct imports: `from ocr_engine import OCREngine`
- No package installation required

## 14. When the Model is Ready

✅ **The model is already integrated and ready.**

The pipeline described above is **implemented and functional**. Key integration points:

1. ✅ `process_inspection()` implemented in `services/ml_service.py`
2. ✅ PaddleOCR pipeline integrated with legal-metrology source
3. ✅ Multi-side merging with confidence-based precedence  
4. ✅ Real compliance rules from Legal Metrology Act
5. ✅ Database schema matches ML output exactly
6. ✅ Flutter status handling updated for new intermediate states

**No schema changes required** — the existing `extracted_information` and `compliance_results` tables are designed to store ML output.

**To verify integration:**
```bash
# Backend
cd backend
pip install -r requirements.txt
python -c "from services.ml_service import process_inspection; print('OK')"

# Run actual test
python -m pytest tests/ -q
```