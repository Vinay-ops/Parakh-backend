"""Test multi-side inspection processing."""
import sys
sys.path.insert(0, r"C:\Users\Vinay Bhogal\Desktop\26034\backend")
from services.ml_service import process_inspection

TEST_IMAGE = r"C:\Users\Vinay Bhogal\Desktop\26034\legal-metrology\data\input\image.png"

# Test 2-side
print("=== 2-SIDE TEST ===")
result = process_inspection(
    "TEST-MULTISIDE-2",
    [("front", TEST_IMAGE), ("back", TEST_IMAGE)]
)
pi = result["product_information"]
comp = result["compliance"]
for k, v in pi.items():
    if v is not None and v != [] and v != "":
        print(f"  {k}: {v}")
status = comp["status"]
score = comp["score"]
rule_count = len(comp["rules"])
print(f"compliance: {status} score={score} rules={rule_count}")
print("2-SIDE PASSED" if rule_count > 0 else "2-SIDE WARNING: no rules")

print()

# Test 4-side
print("=== 4-SIDE TEST ===")
result = process_inspection(
    "TEST-MULTISIDE-4",
    [
        ("front", TEST_IMAGE),
        ("back", TEST_IMAGE),
        ("left", TEST_IMAGE),
        ("right", TEST_IMAGE),
    ]
)
pi = result["product_information"]
comp = result["compliance"]
for k, v in pi.items():
    if v is not None and v != [] and v != "":
        print(f"  {k}: {v}")
status = comp["status"]
score = comp["score"]
rule_count = len(comp["rules"])
print(f"compliance: {status} score={score} rules={rule_count}")
print("4-SIDE PASSED" if rule_count > 0 else "4-SIDE WARNING: no rules")
