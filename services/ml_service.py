"""ML integration interface — PLACEHOLDER ONLY.

The ML team owns the implementation of this module. The contract is:

    process_image(image_path: str) -> dict

It receives a local filesystem path to the stored product image and MUST
return a dict matching ML_RESULT_SCHEMA below (see docs/ML_INTEGRATION.md for
the full specification and examples).

When implementing, keep the signature and return shape unchanged so that
neither the Flutter API contract nor the database schema needs to change.
Until then, process_image raises NotImplementedError and /api/scan records the
inspection with compliance_status = "PENDING_ML". No fake predictions exist
anywhere in this codebase.
"""
from typing import Any, Optional

# The exact structure the ML team must return. `validate_result` normalizes it
# and `inspection_service.apply_ml_result` persists exactly this shape, so the
# schema and the persistence layer always agree.
ML_RESULT_SCHEMA: dict = {
    "product_information": {
        "common_product_name": Optional[str],
        "manufacturer_name": Optional[str],
        "manufacturer_address": Optional[str],
        "packer_name": Optional[str],
        "packer_address": Optional[str],
        "importer_name": Optional[str],
        "importer_address": Optional[str],
        "multi_product_names": list,
        "multi_product_quantities": list,
        "net_quantity_value": Optional[float],
        "net_quantity_unit": Optional[str],
        "number_count": Optional[int],
        "mrp": Optional[float],
        "mrp_tax_wording": Optional[str],
        "manufacture_or_import_date": Optional[str],
        "consumer_care_name": Optional[str],
        "consumer_care_address": Optional[str],
        "consumer_care_phone": Optional[str],
        "consumer_care_email": Optional[str],
        "commodity_dimensions": Optional[str],
    },
    "compliance": {
        "status": Optional[str],  # "COMPLIANT" | "NON_COMPLIANT" | None
        "score": Optional[float],
        "rules": list,  # [{"rule_name", "status", "reason", "required_value", "detected_value", "bounding_box"}]
    },
}


class MLNotIntegratedError(NotImplementedError):
    """Raised while the ML model has not been integrated yet."""


def process_image(image_path: str) -> dict:
    """Run OCR / product extraction / compliance analysis on a product image.

    TODO(ML team): implement this function. Do not change the signature or the
    return structure (ML_RESULT_SCHEMA). The backend persists the returned
    product_information into `extracted_information` and each compliance rule
    into `compliance_results`, so the Flutter app needs no changes.
    """
    raise MLNotIntegratedError("ML model is not integrated yet")


def validate_result(result: Any) -> dict:
    """Normalize and structurally validate raw ML output.

    The ML team can rely on this: anything missing/None is stored as NULL and
    an empty rules list simply means no per-rule results were produced. The
    returned dict always has the canonical shape:
        {"product_information": {...}, "compliance": {"status", "score", "rules"}}
    """
    if not isinstance(result, dict):
        raise ValueError("ML result must be a dict")
    product_information = result.get("product_information") or {}
    compliance = result.get("compliance") or {}
    if not isinstance(product_information, dict) or not isinstance(compliance, dict):
        raise ValueError("ML result keys 'product_information' and 'compliance' must be dicts")
    rules = compliance.get("rules") or []
    if not isinstance(rules, list):
        raise ValueError("compliance.rules must be a list")
    return {
        "product_information": product_information,
        "compliance": {
            "status": compliance.get("status"),
            "score": compliance.get("score"),
            "rules": rules,
        },
    }