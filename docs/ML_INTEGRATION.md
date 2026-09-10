# ML Integration Contract

This document is the contract between the **Parakh backend** and the **ML team**.
The backend is ready to receive, validate, and persist ML output; only the
model itself is missing.

**Do not change** the signature of `process_image`, the result structure below,
or the database schema when implementing the model — the Flutter API contract
is intentionally independent of the ML implementation.

---

## 1. Integration point

File: `services/ml_service.py`

```python
def process_image(image_path: str) -> dict:
    ...
```

- **Input:** absolute path to a local file containing the product-label image
  that was just uploaded (JPEG/PNG/WebP). The backend writes the validated
  upload to a temp file and calls `process_image` with its path.
- **Output:** a Python dict matching the structure in section 2.
- **Current behavior:** raises `MLNotIntegratedError` (a `NotImplementedError`
  subclass). The scan endpoint catches it, leaves the inspection in
  `PENDING_ML`, and returns `ml_pending: true`. Nothing else changes when the
  real model is wired in.

Call flow in `POST /api/scan`:

```
upload ─> validate (magic bytes + size) ─> Supabase Storage ─>
create inspection (PENDING_ML) ─> process_image(path) ─>
validate_result(...) ─> apply_ml_result(...) ─> status = COMPLIANT/NON_COMPLIANT
```

## 2. Expected model output

```json
{
  "product_information": {
    "common_product_name": "string | null",
    "manufacturer_name": "string | null",
    "manufacturer_address": "string | null",
    "packer_name": "string | null",
    "packer_address": "string | null",
    "importer_name": "string | null",
    "importer_address": "string | null",
    "multi_product_names": ["string", "..."] | null,
    "multi_product_quantities": ["string", "..."] | null,
    "net_quantity_value": 250.0 | null,
    "net_quantity_unit": "g" | null,
    "number_count": 4 | null,
    "mrp": 30.0 | null,
    "mrp_tax_wording": "string | null",
    "manufacture_or_import_date": "string | null",
    "consumer_care_name": "string | null",
    "consumer_care_address": "string | null",
    "consumer_care_phone": "string | null",
    "consumer_care_email": "string | null",
    "commodity_dimensions": "string | null"
  },
  "compliance": {
    "status": "COMPLIANT | NON_COMPLIANT | null",
    "score": 95.0 | null,
    "rules": [
      {
        "rule_name": "string",
        "status": "PASS | FAIL | string",
        "reason": "string | null",
        "required_value": "string | null",
        "detected_value": "string | null",
        "bounding_box": {
          "x1": 12.5, "y1": 8.0, "x2": 90.0, "y2": 30.0
        } | null
      }
    ]
  }
}
```

Notes:

- `product_information` keys map 1:1 to columns of `extracted_information`.
- `compliance.rules` is a list; an empty list means "no per-rule results".
- `bounding_box` is optional per rule and stored as JSON (normalized
  coordinates in the image's own coordinate space).
- Missing/`None` fields are stored as `NULL`; there is no need to return every
  key.

## 3. Validation

`ml_service.validate_result(result)` is applied to the raw model output before
anything is persisted. It:

1. Requires a `dict` with `product_information` and `compliance` dicts.
2. Requires `compliance.rules` to be a list.
3. Normalizes the output to the canonical shape:

```python
{
    "product_information": {...},
    "compliance": {"status": ..., "score": ..., "rules": [...]},
}
```

Anything missing is tolerated (stored as `NULL`); structurally invalid output
raises `ValueError`, which the scan flow treats as a failed inspection
(`FAILED`).

## 4. Persistence

`inspection_service.apply_ml_result(db, inspection, ml_result)`:

- Creates/replaces one `extracted_information` row from
  `product_information`.
- Replaces `compliance_results` rows from `compliance.rules` (one row per
  rule, including `bounding_box`).
- Sets `inspection.compliance_status` (defaults to `FAILED` if absent) and
  `inspection.compliance_score`.

All rows link to `inspections.id` (internal UUID). No schema changes are
required to store ML output.

## 5. When the model is ready

1. Implement `process_image(image_path) -> dict` in `services/ml_service.py`.
2. Keep the signature and output structure from this document.
3. Run `python -m pytest tests/ -q` — the existing suite keeps working because
   it never depends on the model (it asserts `PENDING_ML`/`ml_pending` while
   the placeholder is in place).
4. Add ML-specific tests in a separate file if desired (e.g.
   `tests/test_ml_apply.py` exercising `apply_ml_result` with a fixture dict).

No changes to `api/scan.py`, the database, or the Flutter API contract are
needed.