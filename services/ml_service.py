"""ML integration interface — PLACEHOLDER ONLY.

The ML team owns the implementation of this module. The contracts are:

    process_inspection(inspection_id: str, side_images: list[tuple[str, str]]) -> dict

    process_image(image_path: str) -> dict  (legacy single-image interface)

`process_inspection` receives:
  - inspection_id: the public INSP-... identifier (for logging/correlation)
  - side_images: list of (side_label, local_file_path) tuples, e.g.
      [("front", "/tmp/parakh_abc_front.jpg"), ("back", "/tmp/parakh_abc_back.jpg")]

It MUST return a dict matching ML_RESULT_SCHEMA below.

Until implemented, both functions raise MLNotIntegratedError and /api/inspections/{id}/process
records the inspection as PENDING_ML. No fake predictions exist anywhere.
"""
from typing import Any, Optional

# The exact structure the ML team must return.
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


def process_inspection(inspection_id: str, side_images: list[tuple[str, str]]) -> dict:
    """Run OCR / product extraction / compliance analysis on multi-side package images.

    Args:
        inspection_id: Public INSP-... identifier for logging/correlation.
        side_images: List of (side_label, local_file_path) tuples ordered by
                     side_order. Example:
                       [("front", "/tmp/parakh_abc_front.jpg"),
                        ("back",  "/tmp/parakh_abc_back.jpg"),
                        ("left",  "/tmp/parakh_abc_left.jpg"),
                        ("right", "/tmp/parakh_abc_right.jpg")]

    Returns:
        dict matching ML_RESULT_SCHEMA. The ML team aggregates information from
        all sides into a single product_information dict and a single compliance
        result. Side-specific bounding boxes can be included in compliance rules.

    TODO(ML team): implement this function. Keep the signature and return
    structure from this docstring. Do not change ML_RESULT_SCHEMA.
    """
    raise MLNotIntegratedError("ML model is not integrated yet")


def process_image(image_path: str) -> dict:
    """Legacy single-image interface — kept for backward compatibility.

    New code should call process_inspection() with side_images.

    TODO(ML team): implement or delegate to process_inspection.
    """
    raise MLNotIntegratedError("ML model is not integrated yet")


def validate_result(result: Any) -> dict:
    """Normalize and structurally validate raw ML output.

    The ML team can rely on this: anything missing/None is stored as NULL and
    an empty rules list simply means no per-rule results were produced.
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