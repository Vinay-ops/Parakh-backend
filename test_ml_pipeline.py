"""End-to-end test of the ML/OCR pipeline using the real test image."""
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Add backend directory to path
sys.path.insert(0, r"C:\Users\Vinay Bhogal\Desktop\26034\backend")

from services.ml_service import process_inspection, MLNotIntegratedError

TEST_IMAGE = r"C:\Users\Vinay Bhogal\Desktop\26034\legal-metrology\data\input\image.png"

def run_test():
    print("=" * 60)
    print("PARAKH ML PIPELINE END-TO-END TEST")
    print("=" * 60)
    
    try:
        print(f"\nRunning process_inspection on: {TEST_IMAGE}")
        result = process_inspection("TEST-001", [("front", TEST_IMAGE)])
        
        pi = result["product_information"]
        comp = result["compliance"]
        
        print("\n=== PRODUCT INFORMATION ===")
        found_fields = 0
        for k, v in pi.items():
            if v is not None and v != [] and v != "":
                print(f"  {k}: {v}")
                found_fields += 1
        if found_fields == 0:
            print("  (no fields extracted)")
        
        print(f"\n=== COMPLIANCE ===")
        status = comp["status"]
        score = comp["score"]
        rules = comp["rules"]
        print(f"  status: {status}")
        print(f"  score: {score}")
        print(f"  rules evaluated: {len(rules)}")
        
        for r in rules:
            rule_name = r["rule_name"]
            rule_status = r["status"]
            reason = r["reason"]
            print(f"    [{rule_status}] {rule_name}: {reason}")
        
        print("\n=== SUMMARY ===")
        print(f"  Fields extracted: {found_fields}")
        print(f"  Rules evaluated: {len(rules)}")
        print(f"  Compliance status: {status}")
        print(f"  Score: {score}")
        
        if len(rules) > 0:
            print("\n  TEST PASSED: ML pipeline produced real output")
        else:
            print("\n  WARNING: No compliance rules evaluated")
            
    except MLNotIntegratedError as e:
        print(f"\n  BLOCKED: ML dependencies not available: {e}")
        print("  Install: pip install paddlepaddle paddleocr opencv-python-headless")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n  FAILED with unexpected error: {e}")

if __name__ == "__main__":
    run_test()
