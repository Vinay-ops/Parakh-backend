"""Verify the _extract_from_tokens patching mechanism works correctly."""
import sys
sys.path.insert(0, r"C:\Users\Vinay Bhogal\Desktop\26034\backend")
sys.path.insert(0, r"C:\Users\Vinay Bhogal\Desktop\26034\legal-metrology\src\extraction")
sys.path.insert(0, r"C:\Users\Vinay Bhogal\Desktop\26034\legal-metrology\src\ocr")
sys.path.insert(0, r"C:\Users\Vinay Bhogal\Desktop\26034\legal-metrology\src\rules")
sys.path.insert(0, r"C:\Users\Vinay Bhogal\Desktop\26034\legal-metrology\src\report")

from pathlib import Path
from extractor import InformationExtractor

SCHEMA_PATH = Path(r"C:\Users\Vinay Bhogal\Desktop\26034\legal-metrology\data\rules\extraction_schema.json")

# Simulate what _extract_from_tokens does
tokens = [
    {"text": "MRP Rs. 50.00 incl. of all taxes", "confidence": 0.9, "bounding_box": [10, 10, 200, 30]},
    {"text": "Manufactured by ABC Foods Pvt Ltd", "confidence": 0.88, "bounding_box": [10, 50, 200, 70]},
    {"text": "Net Quantity 500 g", "confidence": 0.92, "bounding_box": [10, 90, 200, 110]},
    {"text": "Mfg Date: Jan 2025", "confidence": 0.85, "bounding_box": [10, 130, 200, 150]},
]

extractor = InformationExtractor.__new__(InformationExtractor)
extractor.ocr_result_path = None
extractor.schema_path = SCHEMA_PATH

_original_load = extractor.load_json


def _patched_load(path):
    if path is None:
        return tokens
    return _original_load(path)


extractor.load_json = _patched_load

result = extractor.extract()
print("=== EXTRACTION RESULT ===")
for k, v in result.items():
    if isinstance(v, dict):
        val = v.get("value")
        if val:
            print(f"  {k}: {val}")

print()
print("Patching mechanism: OK" if result else "ERROR: No result")
