import csv
import json
import re
from pathlib import Path


class RuleEngine:

    def __init__(
        self,
        rules_path,
        extracted_path,
        ocr_path,
        schema_path
    ):
        self.rules_path = Path(rules_path)
        self.extracted_path = Path(extracted_path)
        self.ocr_path = Path(ocr_path)
        self.schema_path = Path(schema_path)

    # =========================================================
    # LOAD DATA
    # =========================================================

    def load_rules(self):
        with open(
            self.rules_path,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:
            return list(csv.DictReader(file))

    def load_json(self, path):
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    # =========================================================
    # TEXT HELPERS
    # =========================================================

    def normalize(self, text):
        text = str(text or "").lower()

        text = re.sub(
            r"[^a-z0-9\s]",
            " ",
            text
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return text.strip()

    def get_ocr_text(self, ocr_data):
        return " ".join(
            str(item.get("text", ""))
            for item in ocr_data
        )

    # =========================================================
    # EXTRACTED FIELD HELPERS
    # =========================================================

    def field_value(
        self,
        extracted,
        field_name
    ):
        data = extracted.get(field_name)

        if data is None:
            return None

        if isinstance(data, dict):
            return data.get("value")

        return data

    def field_exists(
        self,
        extracted,
        field_name
    ):
        value = self.field_value(
            extracted,
            field_name
        )

        return (
            value is not None
            and str(value).strip() != ""
        )

    # =========================================================
    # EVIDENCE HELPERS
    # =========================================================

    def make_evidence(
        self,
        text,
        confidence=None,
        bounding_box=None,
        evidence_type="ocr"
    ):
        return {
            "text": str(text),
            "confidence": confidence,
            "bounding_box": bounding_box,
            "type": evidence_type
        }

    def find_ocr_evidence(
        self,
        ocr_data,
        search_text
    ):
        """
        Find OCR regions containing the supplied text.
        """

        evidence = []

        search_normalized = self.normalize(
            search_text
        )

        if not search_normalized:
            return evidence

        for item in ocr_data:

            text = str(
                item.get("text", "")
            ).strip()

            box = item.get(
                "bounding_box"
            )

            if not text or not box:
                continue

            normalized_text = self.normalize(
                text
            )

            if (
                search_normalized in normalized_text
                or normalized_text in search_normalized
            ):

                evidence.append(
                    self.make_evidence(
                        text=text,
                        confidence=item.get(
                            "confidence"
                        ),
                        bounding_box=box
                    )
                )

        return evidence

    def get_field_evidence(
        self,
        extracted,
        field_name
    ):
        """
        Retrieves bounding boxes already associated
        with an extracted field.
        """

        field_data = extracted.get(
            field_name
        )

        if not isinstance(
            field_data,
            dict
        ):
            return []

        evidence = []

        for item in field_data.get(
            "evidence",
            []
        ):

            label = item.get(
                "label"
            )

            value = item.get(
                "value"
            )

            if label:

                evidence.append(
                    self.make_evidence(
                        text=label.get(
                            "text",
                            ""
                        ),
                        confidence=label.get(
                            "confidence"
                        ),
                        bounding_box=label.get(
                            "bounding_box"
                        ),
                        evidence_type="label"
                    )
                )

            if value:

                evidence.append(
                    self.make_evidence(
                        text=value.get(
                            "text",
                            ""
                        ),
                        confidence=value.get(
                            "confidence"
                        ),
                        bounding_box=value.get(
                            "bounding_box"
                        ),
                        evidence_type="value"
                    )
                )

        return evidence

    def field_evidence(
        self,
        extracted,
        ocr_data,
        field_name
    ):
        """
        Prefer extraction evidence.
        Fall back to OCR search if necessary.
        """

        evidence = self.get_field_evidence(
            extracted,
            field_name
        )

        if evidence:
            return evidence

        value = self.field_value(
            extracted,
            field_name
        )

        if value:
            return self.find_ocr_evidence(
                ocr_data,
                str(value)
            )

        return []

    # =========================================================
    # REQUIRED FIELD CHECK
    # =========================================================

    def check_required_fields(
        self,
        extracted,
        fields,
        ocr_data
    ):
        missing = []
        evidence = []

        for field in fields:

            if not self.field_exists(
                extracted,
                field
            ):
                missing.append(field)

            else:
                evidence.extend(
                    self.field_evidence(
                        extracted,
                        ocr_data,
                        field
                    )
                )

        if missing:

            return {
                "status": "VERIFY",
                "reason": (
                    "Required declaration/information "
                    "could not be reliably verified"
                ),
                "missing_fields": missing,
                "evidence": evidence
            }

        return {
            "status": "COMPLIANT",
            "reason": (
                "Required declaration/information "
                "was detected"
            ),
            "evidence": evidence
        }

    # =========================================================
    # MRP
    # =========================================================

    def check_mrp(
        self,
        extracted,
        ocr_data,
        ocr_text
    ):
        if not self.field_exists(
            extracted,
            "mrp"
        ):

            return {
                "status": "VERIFY",
                "reason": (
                    "MRP declaration could not be reliably verified"
                ),
                "missing_fields": ["mrp"],
                "evidence": []
            }

        evidence = self.field_evidence(
            extracted,
            ocr_data,
            "mrp"
        )

        normalized_text = self.normalize(
            ocr_text
        )

        tax_phrases = [
            "inclusive of all taxes",
            "incl of all taxes",
            "incl all taxes",
            "all taxes"
        ]

        tax_wording_found = any(
            phrase in normalized_text
            for phrase in tax_phrases
        )

        if tax_wording_found:

            return {
                "status": "COMPLIANT",
                "reason": (
                    "MRP and tax-inclusive wording "
                    "were detected"
                ),
                "evidence": evidence
            }

        return {
            "status": "VERIFY",
            "reason": (
                "MRP was detected but required "
                "tax-inclusive wording could not be reliably verified"
            ),
            "evidence": evidence
        }

    # =========================================================
    # NET QUANTITY
    # =========================================================

    def check_quantity(
        self,
        extracted,
        ocr_data
    ):
        value = self.field_value(
            extracted,
            "net_quantity"
        )

        evidence = self.field_evidence(
            extracted,
            ocr_data,
            "net_quantity"
        )

        if not value:

            return {
                "status": "VERIFY",
                "reason": (
                    "Net quantity could not be reliably verified"
                ),
                "missing_fields": [
                    "net_quantity"
                ],
                "evidence": evidence
            }

        value_text = str(value)

        if not re.search(
            r"\d",
            value_text
        ):

            return {
                "status": "VERIFY",
                "reason": (
                    "Net quantity was extracted, but its numeric "
                    "value could not be reliably verified"
                ),
                "evidence": evidence
            }

        unit_pattern = (
            r"\b(?:"
            r"kg|g|gm|mg|ug|µg|"
            r"l|ml|cl|"
            r"litre|liter|litres|liters|"
            r"pcs|pc|pieces|piece|"
            r"n|u"
            r")\b"
        )

        if re.search(
            unit_pattern,
            value_text,
            re.IGNORECASE
        ):

            return {
                "status": "COMPLIANT",
                "reason": (
                    "Numeric net quantity and "
                    "standard unit detected"
                ),
                "evidence": evidence
            }

        return {
            "status": "VERIFY",
            "reason": (
                "Numeric net quantity detected, "
                "but a standard unit could not be "
                "confidently associated with it"
            ),
            "evidence": evidence
        }

    # =========================================================
    # MANUFACTURER / PACKER / IMPORTER
    # =========================================================

    def check_manufacturer_details(
        self,
        extracted,
        ocr_data
    ):

        return self.check_required_fields(
            extracted,
            [
                "manufacturer_packer_importer",
                "address"
            ],
            ocr_data
        )

    # =========================================================
    # MANUFACTURING / PACKING DATE
    # =========================================================

    def check_manufacturing_date(
        self,
        extracted,
        ocr_data
    ):

        field_name = (
            "manufacturing_or_packing_date"
        )

        evidence = self.field_evidence(
            extracted,
            ocr_data,
            field_name
        )

        if not self.field_exists(
            extracted,
            field_name
        ):

            return {
                "status": "VERIFY",
                "reason": (
                    "Manufacturing/packing date could not be "
                    "reliably verified"
                ),
                "missing_fields": [
                    field_name
                ],
                "evidence": evidence
            }

        value = str(
            self.field_value(
                extracted,
                field_name
            )
        )

        date_pattern = (
            r"\b\d{1,4}"
            r"[-/.]"
            r"\d{1,2}"
            r"[-/.]"
            r"\d{1,4}\b"
        )

        if not re.search(
            date_pattern,
            value
        ):

            return {
                "status": "VERIFY",
                "reason": (
                    "Manufacturing/packing date "
                    "detected but its format requires "
                    "verification"
                ),
                "evidence": evidence
            }

        return {
            "status": "COMPLIANT",
            "reason": (
                "Manufacturing/packing date detected"
            ),
            "evidence": evidence
        }

    # =========================================================
    # CONSUMER CARE
    # =========================================================

    def check_consumer_care(
        self,
        extracted,
        ocr_data
    ):

        evidence = self.field_evidence(
            extracted,
            ocr_data,
            "consumer_care"
        )

        if not self.field_exists(
            extracted,
            "consumer_care"
        ):

            return {
                "status": "VERIFY",
                "reason": (
                    "Consumer care details could not be reliably "
                    "verified"
                ),
                "missing_fields": [
                    "consumer_care"
                ],
                "evidence": evidence
            }

        return {
            "status": "COMPLIANT",
            "reason": (
                "Consumer care details detected"
            ),
            "evidence": evidence
        }

    # =========================================================
    # PRODUCT NAME
    # =========================================================

    def check_product_name(
        self,
        extracted,
        ocr_data
    ):

        if self.field_exists(
            extracted,
            "product_name"
        ):

            return {
                "status": "COMPLIANT",
                "reason": (
                    "Generic product name detected"
                ),
                "evidence": self.field_evidence(
                    extracted,
                    ocr_data,
                    "product_name"
                )
            }

        return {
            "status": "VERIFY",
            "reason": (
                "Generic product name requires "
                "dedicated extraction/verification"
            ),
            "evidence": []
        }

    # =========================================================
    # QUANTITY MODIFIERS
    # =========================================================

    def check_quantity_modifiers(
        self,
        ocr_data,
        ocr_text
    ):

        normalized = self.normalize(
            ocr_text
        )

        prohibited_words = [
            "minimum",
            "average",
            "about",
            "approximately",
            "approx"
        ]

        found = []

        for word in prohibited_words:

            if re.search(
                r"\b"
                + re.escape(word)
                + r"\b",
                normalized
            ):
                found.append(word)

        evidence = []

        for word in found:

            evidence.extend(
                self.find_ocr_evidence(
                    ocr_data,
                    word
                )
            )

        if found:

            return {
                "status": "VIOLATION",
                "reason": (
                    "Potentially prohibited quantity "
                    "modifier detected"
                ),
                "detected_terms": found,
                "evidence": evidence
            }

        return {
            "status": "COMPLIANT",
            "reason": (
                "No prohibited quantity modifier "
                "was detected"
            ),
            "evidence": []
        }

    # =========================================================
    # MANUAL / UNKNOWN RULE
    # =========================================================

    def check_manual_rule(self):

        return {
            "status": "VERIFY",
            "reason": (
                "Requires human visual/physical "
                "verification"
            ),
            "evidence": []
        }

    def check_unknown_rule(self):

        return {
            "status": "VERIFY",
            "reason": (
                "Rule requires additional evidence "
                "not currently available to the "
                "automated engine"
            ),
            "evidence": []
        }

    # =========================================================
    # DETERMINE CHECK TYPE
    # =========================================================

    def determine_check_type(
        self,
        rule
    ):

        parameter = self.normalize(
            rule.get(
                "Declaration/Parameter to Check",
                ""
            )
        )

        requirement = self.normalize(
            rule.get(
                "Simplified Requirement",
                ""
            )
        )

        legal_requirement = self.normalize(
            rule.get(
                "Legal Requirement",
                ""
            )
        )

        detection_method = self.normalize(
            rule.get(
                "Detection Method",
                ""
            )
        )

        combined = " ".join(
            [
                parameter,
                requirement,
                legal_requirement
            ]
        )

        # Manual checks
        if (
            "manual review" in detection_method
            and "automated" not in detection_method
        ):
            return "manual"

        # MRP
        if (
            "mrp" in combined
            or "maximum retail price" in combined
            or "retail sale price" in combined
        ):
            return "mrp"

        # Quantity
        if "net quantity" in combined:

            if (
                "exaggerated" in combined
                or "misleading" in combined
                or "minimum" in combined
                or "approximately" in combined
            ):
                return "quantity_modifier"

            return "quantity"

        # Manufacturer / packer / importer
        if (
            "manufacturer" in combined
            or "packer" in combined
            or "importer" in combined
        ):
            return "manufacturer"

        # Product name
        if (
            "generic name" in combined
            or "common name" in combined
            or "product identity" in combined
        ):
            return "product_name"

        # Date
        if (
            "manufactur" in combined
            or "packing date" in combined
            or "month and year" in combined
        ):
            return "date"

        # Consumer care
        if (
            "consumer care" in combined
            or "consumer complaints" in combined
            or "telephone number" in combined
            or "contact address" in combined
        ):
            return "consumer_care"

        return "unknown"

    # =========================================================
    # EVALUATE RULE
    # =========================================================

    def evaluate_rule(
        self,
        rule,
        extracted,
        ocr_data,
        ocr_text
    ):

        check_type = self.determine_check_type(
            rule
        )

        if check_type == "manual":
            return self.check_manual_rule()

        if check_type == "mrp":
            return self.check_mrp(
                extracted,
                ocr_data,
                ocr_text
            )

        if check_type == "quantity":
            return self.check_quantity(
                extracted,
                ocr_data
            )

        if check_type == "manufacturer":
            return self.check_manufacturer_details(
                extracted,
                ocr_data
            )

        if check_type == "product_name":
            return self.check_product_name(
                extracted,
                ocr_data
            )

        if check_type == "date":
            return self.check_manufacturing_date(
                extracted,
                ocr_data
            )

        if check_type == "consumer_care":
            return self.check_consumer_care(
                extracted,
                ocr_data
            )

        if check_type == "quantity_modifier":
            return self.check_quantity_modifiers(
                ocr_data,
                ocr_text
            )

        return self.check_unknown_rule()

    # =========================================================
    # RUN
    # =========================================================

    def run(self):

        rules = self.load_rules()

        extracted = self.load_json(
            self.extracted_path
        )

        ocr_data = self.load_json(
            self.ocr_path
        )

        self.load_json(
            self.schema_path
        )

        ocr_text = self.get_ocr_text(
            ocr_data
        )

        results = []

        for rule in rules:

            evaluation = self.evaluate_rule(
                rule,
                extracted,
                ocr_data,
                ocr_text
            )

            result = {
                "rule_id": rule.get(
                    "Rule ID"
                ),
                "rule": rule.get(
                    "Rule/Clause No."
                ),
                "requirement": rule.get(
                    "Simplified Requirement"
                ),
                "applicable_condition": rule.get(
                    "Applicable Product/Condition"
                ),
                "status": evaluation.get(
                    "status"
                ),
                "reason": evaluation.get(
                    "reason"
                ),
                "severity": rule.get(
                    "Severity"
                ),
                "evidence_required": rule.get(
                    "Evidence Required"
                ),
                "source": rule.get(
                    "Source/Page No."
                ),
                "notes": rule.get(
                    "Notes/Exceptions"
                ),
                "evidence": evaluation.get(
                    "evidence",
                    []
                )
            }

            if "missing_fields" in evaluation:

                result["missing_fields"] = (
                    evaluation["missing_fields"]
                )

            if "detected_terms" in evaluation:

                result["detected_terms"] = (
                    evaluation["detected_terms"]
                )

            results.append(
                result
            )

        return results

    # =========================================================
    # SAVE
    # =========================================================

    def save(
        self,
        results,
        output_path
    ):

        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                results,
                file,
                indent=4,
                ensure_ascii=False
            )