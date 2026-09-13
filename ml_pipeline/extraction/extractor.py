import json
import re
from pathlib import Path
from difflib import SequenceMatcher


class InformationExtractor:

    def __init__(self, ocr_result_path, schema_path):
        self.ocr_result_path = Path(ocr_result_path)
        self.schema_path = Path(schema_path)

    # =========================================================
    # I/O
    # =========================================================

    def load_json(self, path):
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def save(self, data, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        return str(output_path)

    # =========================================================
    # TEXT HELPERS
    # =========================================================

    def normalize(self, text):
        text = str(text or "").lower()
        text = re.sub(r"[^a-z0-9@./:+%\-₹€£¥$\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def similarity(self, a, b):
        return SequenceMatcher(None, self.normalize(a), self.normalize(b)).ratio()

    # =========================================================
    # GEOMETRY
    # =========================================================

    def center(self, box):
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def bh(self, box):
        return max(1.0, box[3] - box[1])

    def bw(self, box):
        return max(1.0, box[2] - box[0])

    def voverlap(self, a, b):
        t = max(a[1], b[1])
        bot = min(a[3], b[3])
        ov = max(0, bot - t)
        h = min(self.bh(a), self.bh(b))
        return ov / h

    def distance(self, a_box, b_box):
        ax, ay = self.center(a_box)
        bx, by = self.center(b_box)
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

    # =========================================================
    # LABEL MATCHING (simple)
    # =========================================================

    @staticmethod
    def _condense(s):
        return re.sub(r"[\s\-]+", "", s or "")

    def match_label(self, text, labels):
        norm = self.normalize(text)
        if not norm:
            return None
        cnorm = self._condense(norm)
        for lab in labels:
            nl = self.normalize(lab)
            if not nl:
                continue
            cnl = self._condense(nl)
            if nl == norm:
                return lab
            if nl in norm:
                if len(nl) >= 4:
                    return lab
                pat = r"(?:^|[^a-z0-9])" + re.escape(nl) + r"(?:$|[^a-z0-9])"
                if re.search(pat, norm):
                    return lab
            if len(cnl) >= 4 and cnl in cnorm:
                return lab
            if len(nl) >= 5 and self.similarity(norm, nl) >= 0.84:
                return lab
        return None

    # =========================================================
    # VALUE-TYPE VALIDATION (lightweight, not paranoid)
    # =========================================================

    def is_price(self, text):
        t = str(text)
        if re.search(r"[₹€£¥$]|rs\.?\b|inr\b|usd\b|eur\b|gbp\b", t, re.IGNORECASE):
            if re.search(r"\d", t):
                return True
        m = re.search(r"(?:^|\s)\d{1,6}[.,]\d{2}(?:\s|$)", t)
        if m:
            if re.search(r"\b(?:g|gm|kg|mg|ml|l|kcal|%)", t, re.IGNORECASE):
                return False
            return True
        return False

    def is_quantity(self, text):
        t = str(text)
        tn = self.normalize(t)
        if re.search(r"\blic(?:\.|ence|ense)?\s*no\.?\b", tn):
            return False
        if re.search(r"\blic\b.*\bno\b", tn):
            return False
        found = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*"
            r"(kg|kgs|g|gm|gms|mg|ug|µg|l|lt|ltr|ml|cl|"
            r"litre|liter|litres|liters|pc|pcs|piece|pieces)\b",
            t,
            re.IGNORECASE,
        )
        if not found:
            return False
        unit = found.group(2)
        pos = found.end(2)
        next_chars = t[pos:pos + 3].lstrip()
        if len(unit) == 1:
            if next_chars.startswith(".") or next_chars.startswith(":"):
                return False
        digits = re.sub(r"\D", "", found.group(1))
        if len(digits) >= 10:
            return False
        return True

    def is_date(self, text):
        t = str(text)
        patterns = [
            r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b",
            r"\b\d{1,2}[-/]\d{2,4}\b",
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{2,4}\b",
            r"\b\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{2,4}\b",
            r"\b\d{1,2}(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{2,4}\b",
        ]
        for p in patterns:
            if re.search(p, t, re.IGNORECASE):
                return True
        m = re.search(r"(?:^|[\s:,\-])((?:19|20)\d{2})(?:$|[\s,;])", t)
        if m:
            if not re.search(r"\d+[.,]\d+", t):
                return True
        return False

    def is_contact(self, text):
        t = str(text)
        if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t):
            return True
        stripped = re.sub(r"[\s\-()+]", "", t)
        digits = re.sub(r"\D", "", stripped)
        if 10 <= len(digits) <= 12:
            if len(digits) == 10 and digits[0] in "6789":
                return True
            if re.search(r"(?:^|[\s:,])\+?\d{0,3}\s*[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}(?:$|[\s,;])", t):
                return True
            if re.search(r"(?:1800|1860)[\s-]?\d{2,3}[\s-]?\d{3,4}", t):
                return True
        return False

    def is_address(self, text):
        tr = str(text)
        tn = self.normalize(text)
        if self.is_organization(text):
            return False
        terms = [
            "road", "rd", "street", "st", "lane", "ln", "nagar",
            "area", "estate", "industrial", "indl", "village",
            "district", "dist", "state", "india", "pin", "pincode",
            "east", "west", "north", "south", "central", "sector",
            "block", "phase", "layout", "colony", "marg", "chowk",
            "plaza", "complex", "building", "tower", "floor",
            "plot", "survey", "taluka", "taluk", "post",
            "karnataka", "maharashtra", "gujarat", "rajasthan",
            "tamil", "telangana", "andhra", "kerala", "punjab",
            "haryana", "delhi", "mumbai", "bengaluru", "bangalore",
            "chennai", "hyderabad", "pune", "hubballi", "ballari",
            "mysuru", "mysore", "kochi", "ahmedabad", "surat",
            "jaipur", "lucknow", "kanpur", "nagpur", "indore",
            "thane", "kalyan", "vasai", "navi", "avenue", "ave",
            "boulevard", "blvd", "drive", "dr", "place", "way",
            "house", "society", "soc", "flat", "apt",
        ]
        has_pin = bool(re.search(r"\b\d{6}\b", tr))
        has_state = bool(
            re.search(
                r"\b(MH|KA|GJ|RJ|TN|TS|AP|KL|PB|HR|DL|UP|MP|BR|OR|WB|AS|JH|CG|UK|HP|GA)\b",
                tr,
            )
        )
        has_intl_post = bool(
            re.search(
                r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}|\d{5}(-\d{4})?|\d{4}\s*[A-Z]{2})\b",
                tr,
            )
        )
        has_term = any(
            re.search(r"(?:^|[^a-z0-9])" + re.escape(t) + r"(?:$|[^a-z0-9])", tn)
            for t in terms
        )
        if has_pin and (has_term or has_state):
            return True
        if has_intl_post and has_term:
            return True
        if has_state and has_term:
            return True
        if has_term and re.search(r"\b\d+\b", tn):
            return True
        return False

    def is_organization(self, text):
        tn = self.normalize(text)
        strong = {
            "pvt", "private", "limited", "ltd", "llp", "inc",
            "incorporated", "corp", "corporation", "gmbh", "ag",
            "sa", "spa", "srl", "srls", "nv", "bv", "oy", "ab",
            "as", "llc", "lp",
        }
        soft = [
            "industries", "products", "company", "enterprise",
            "enterprises", "process", "foods", "food", "group",
            "holdings", "breweries", "pharmaceuticals", "pharma",
            "textiles", "engineering", "chemicals", "cosmetics",
            "electronics", "automotive", "mfg", "manufacturing",
            "manufacturers", "exporters", "importers", "trading",
            "traders", "distributors", "distillery", "dairy",
            "bakery", "confectionery", "wafers",
        ]
        sc = sum(
            1
            for t in strong
            if re.search(r"(?:^|[^a-z0-9])" + re.escape(t) + r"(?:$|[^a-z0-9])", tn)
        )
        so = sum(
            1
            for t in soft
            if re.search(r"(?:^|[^a-z0-9])" + re.escape(t) + r"(?:$|[^a-z0-9])", tn)
        )
        if sc >= 1 and re.search(r"[a-z]", tn):
            return True
        if sc + so >= 2:
            return True
        return False

    def valid_value(self, value_type, text):
        if not text:
            return False
        t = str(text).strip()
        if value_type == "currency":
            return self.is_price(t)
        if value_type == "quantity":
            return self.is_quantity(t)
        if value_type == "date":
            return self.is_date(t)
        if value_type == "contact":
            return self.is_contact(t)
        if value_type == "address":
            return self.is_address(t) and not self.is_organization(t)
        if value_type == "organization":
            return self.is_organization(t) and not self.is_address(t)
        if value_type == "text":
            return len(t) >= 2
        return False

    # =========================================================
    # SAME-LINE VALUE EXTRACTION
    # =========================================================

    def value_after_label(self, text, label):
        original = str(text or "")
        norm = self.normalize(original)
        nlabel = self.normalize(label or "")
        if not nlabel or nlabel not in norm:
            return None
        pat = re.compile(re.escape(nlabel), re.IGNORECASE)
        m = pat.search(norm)
        if not m:
            return None
        nl_start = m.start()
        label_start = 0
        label_end = len(original)
        best = None
        for w in range(max(1, len(label) - 2), len(original) + 1):
            found = False
            for s in range(0, len(original) - w + 1):
                snip = original[s:s + w]
                if self.normalize(snip) == nlabel:
                    label_start = s
                    label_end = s + w
                    found = True
                    break
            if found:
                best = (label_start, label_end)
                break
        if best:
            label_start, label_end = best
        else:
            ratio = len(original) / max(1, len(norm))
            label_start = min(len(original) - 1, int(nl_start * ratio))
            label_end = label_start + len(label)
        rest = original[label_end:].strip()
        rest = re.sub(r"^[\s:=\-]+", "", rest).strip()
        return rest or None

    # =========================================================
    # NEARBY GEOMETRIC SEARCH (fallback)
    # =========================================================

    NUTRITION_CONTEXT_WORDS = {
        "serving", "nutrition", "nutritional", "per 100", "per100",
        "amount per", "of which", "energy", "protein", "fat",
        "carbohydrate", "carbohydrates", "sugar", "sugars",
        "fiber", "fibre", "cholesterol", "sodium", "potassium",
        "calcium", "iron", "vitamin", "calorie", "calories",
        "kcal", "kj", "trans fat", "saturated", "polyunsaturated",
        "monounsaturated", "added sugars", "dietary fiber",
        "dietary fibre",
    }

    def _in_nutrition_context(self, text):
        tn = self.normalize(text)
        if not tn:
            return False
        for w in self.NUTRITION_CONTEXT_WORDS:
            if w in tn:
                return True
        return False

    def _cache_nutrition_anchors(self, ocr_data):
        if getattr(self, "_nutrition_anchors_cache_id", None) != id(ocr_data):
            anchors = []
            for item in ocr_data:
                t = str(item.get("text", ""))
                if self._in_nutrition_context(t):
                    box = item.get("bounding_box")
                    if box:
                        anchors.append(box)
            self._nutrition_anchors = anchors
            self._nutrition_anchors_cache_id = id(ocr_data)
        return self._nutrition_anchors

    def _box_near_nutrition(self, box, ocr_data, px=120):
        if not box:
            return False
        anchors = self._cache_nutrition_anchors(ocr_data)
        cx, cy = self.center(box)
        for ab in anchors:
            ax, ay = self.center(ab)
            if ((cx - ax) ** 2 + (cy - ay) ** 2) ** 0.5 < px:
                return True
        return False

    @staticmethod
    def _clean_date_string(text):
        if not text:
            return text
        s = str(text).strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[,;:]\s*$", "", s)
        m = re.match(
            r"^(.*?"
            r"(?:\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|"
            r"\d{1,2}[-/]\d{2,4}|"
            r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{2,4}|"
            r"\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{2,4}|"
            r"\d{1,2}(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\d{2,4}|"
            r"(?:19|20)\d{2})"
            r")",
            s,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
        return s

    def _sort_neighbors(
        self,
        label_idx,
        ocr_data,
        value_type,
        exclude_indices=None,
        reject_nutrition_context=False,
    ):
        if exclude_indices is None:
            exclude_indices = set()
        label_item = ocr_data[label_idx]
        lb = label_item.get("bounding_box")
        if not lb:
            return []
        lx, ly = self.center(lb)
        lh = self.bh(lb)
        lw = self.bw(lb)
        max_dx = max(500, lw * 7)
        max_dy = max(160, lh * 6)
        out = []
        for i, item in enumerate(ocr_data):
            if i == label_idx or i in exclude_indices:
                continue
            t = str(item.get("text", "")).strip()
            box = item.get("bounding_box")
            if not t or not box:
                continue
            if not self.valid_value(value_type, t):
                continue
            if reject_nutrition_context and self._in_nutrition_context(t):
                continue
            if reject_nutrition_context and self._box_near_nutrition(box, ocr_data, px=140):
                continue
            vx, vy = self.center(box)
            if abs(vx - lx) > max_dx or abs(vy - ly) > max_dy:
                continue
            overlap = self.voverlap(lb, box)
            right_bonus = 30 if vx >= lx - lw * 0.5 else 0
            below_bonus = 30 if vy >= ly - lh * 0.3 else 0
            conf = float(item.get("confidence", 0.0) or 0.0)
            nutrition_penalty = 300 if self._in_nutrition_context(t) else 0
            score = (
                overlap * 80
                + right_bonus
                + below_bonus
                + conf * 20
                - self.distance(lb, box) * 0.02
                - nutrition_penalty
            )
            out.append(
                {
                    "index": i,
                    "text": t,
                    "confidence": conf,
                    "bounding_box": box,
                    "score": score,
                }
            )
        out.sort(key=lambda c: c["score"], reverse=True)
        return out

    def find_associated_value(
        self,
        label_idx,
        value_type,
        ocr_data,
        reject_nutrition_context=False,
    ):
        label_item = ocr_data[label_idx]
        lab = label_item.get("_matched_label")
        same = self.value_after_label(label_item.get("text"), lab) if lab else None
        if same and self.valid_value(value_type, same):
            if reject_nutrition_context and self._in_nutrition_context(same):
                same = None
        if same and self.valid_value(value_type, same) and reject_nutrition_context:
            if self._box_near_nutrition(
                label_item.get("bounding_box"), ocr_data, px=140
            ):
                same = None
        if same and self.valid_value(value_type, same):
            out = {
                "index": label_idx,
                "text": same,
                "confidence": label_item.get("confidence"),
                "bounding_box": label_item.get("bounding_box"),
                "score": 900.0,
            }
            if value_type == "date":
                out["text"] = self._clean_date_string(out["text"])
            return out
        neighbors = self._sort_neighbors(
            label_idx,
            ocr_data,
            value_type,
            reject_nutrition_context=reject_nutrition_context,
        )
        if neighbors and neighbors[0]["score"] >= -50.0:
            top = dict(neighbors[0])
            if value_type == "date":
                top["text"] = self._clean_date_string(top["text"])
            return top
        return None

    # =========================================================
    # ORG + ADDRESS FINDERS
    # =========================================================

    def find_organization_near(self, label_idx, ocr_data):
        label_item = ocr_data[label_idx]
        lab = label_item.get("_matched_label")
        same = self.value_after_label(label_item.get("text"), lab) if lab else None
        if same and self.valid_value("organization", same):
            return {
                "index": label_idx,
                "text": same,
                "confidence": label_item.get("confidence"),
                "bounding_box": label_item.get("bounding_box"),
                "score": 900.0,
            }
        neighbors = self._sort_neighbors(label_idx, ocr_data, "organization")
        if neighbors and neighbors[0]["score"] >= -50.0:
            return neighbors[0]
        return None

    def find_address_near(self, anchor, ocr_data):
        if not anchor:
            return None
        abox = anchor.get("bounding_box")
        if not abox:
            return None
        ax, ay = self.center(abox)
        ah = self.bh(abox)
        aw = self.bw(abox)
        max_dx = max(450, aw * 8)
        max_dy = max(180, ah * 7)
        candidates = []
        anchor_norm = self.normalize(anchor.get("text", ""))
        for i, item in enumerate(ocr_data):
            t = str(item.get("text", "")).strip()
            box = item.get("bounding_box")
            if not t or not box:
                continue
            if not self.valid_value("address", t):
                continue
            if self.normalize(t) == anchor_norm:
                continue
            if self.is_organization(t):
                continue
            cx, cy = self.center(box)
            if abs(cx - ax) > max_dx or abs(cy - ay) > max_dy:
                continue
            if cy < ay - ah * 0.3:
                continue
            conf = float(item.get("confidence", 0.0) or 0.0)
            score = 100 + conf * 20 - self.distance(abox, box) * 0.02
            candidates.append(
                {
                    "index": i,
                    "text": t,
                    "confidence": conf,
                    "bounding_box": box,
                    "score": score,
                }
            )
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[0] if candidates else None

    def build_evidence(self, label_item, value_item=None):
        ev = {
            "label": {
                "text": label_item.get("text"),
                "confidence": label_item.get("confidence"),
                "bounding_box": label_item.get("bounding_box"),
            }
        }
        if value_item:
            ev["value"] = {
                "text": value_item.get("text"),
                "confidence": value_item.get("confidence"),
                "bounding_box": value_item.get("bounding_box"),
            }
        return ev

    # =========================================================
    # ROLES
    # =========================================================

    def _find_label_matches(self, ocr_data, labels):
        matches = []
        for i, item in enumerate(ocr_data):
            t = str(item.get("text", "")).strip()
            if not t:
                continue
            matched = self.match_label(t, labels)
            if matched:
                item2 = dict(item)
                item2["_matched_label"] = matched
                matches.append({"index": i, "label": matched, "item": item2})
        return matches

    def _extract_role(self, role, ocr_data):
        role_name = role.get("role")
        labels = role.get("labels", [])
        result = {
            "organization": None,
            "address": None,
            "organization_confidence": None,
            "address_confidence": None,
            "status": "NOT_FOUND",
            "evidence": [],
        }
        matches = self._find_label_matches(ocr_data, labels)
        if not matches:
            return result
        best_org = None
        best_label_item = None
        best_match = None
        for m in matches:
            ocr_data_copy = list(ocr_data)
            ocr_data_copy[m["index"]] = m["item"]
            org = self.find_organization_near(m["index"], ocr_data_copy)
            if org:
                if best_org is None or org["score"] > best_org["score"]:
                    best_org = org
                    best_label_item = m["item"]
                    best_match = m
        if best_org:
            result["organization"] = best_org["text"]
            result["organization_confidence"] = best_org["confidence"]
            result["status"] = "OK"
            result["evidence"].append(self.build_evidence(best_label_item, best_org))
            addr = self.find_address_near(best_org, ocr_data)
            if not addr and best_match:
                ocr_data_copy = list(ocr_data)
                ocr_data_copy[best_match["index"]] = best_match["item"]
                label_addr_value = self.value_after_label(
                    best_match["item"].get("text"), best_match["label"]
                )
                if label_addr_value and self.valid_value("address", label_addr_value):
                    addr = {
                        "text": label_addr_value,
                        "confidence": best_match["item"].get("confidence"),
                        "bounding_box": best_match["item"].get("bounding_box"),
                    }
            if addr:
                result["address"] = addr["text"]
                result["address_confidence"] = addr["confidence"]
                result["evidence"].append(
                    {
                        "value": {
                            "text": addr["text"],
                            "confidence": addr["confidence"],
                            "bounding_box": addr["bounding_box"],
                        }
                    }
                )
        else:
            if any(float(m["item"].get("confidence", 0) or 0) >= 0.75 for m in matches):
                result["status"] = "VERIFY"
        return result

    # =========================================================
    # FALLBACK: IF NO ROLE LABELS FOUND, PICK BEST ORG+ADDR
    # =========================================================

    def _fallback_organization(self, ocr_data):
        candidates = []
        for i, item in enumerate(ocr_data):
            t = str(item.get("text", "")).strip()
            if self.valid_value("organization", t):
                conf = float(item.get("confidence", 0) or 0)
                score = conf * 100
                candidates.append((score, item))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # =========================================================
    # MAIN EXTRACTION
    # =========================================================

    def extract(self):
        ocr_data = self.load_json(self.ocr_result_path)
        schema = self.load_json(self.schema_path)

        extracted = {}
        roles = schema.get("roles", [])
        roles_results = {}
        any_role_label_found = False
        for role in roles:
            rn = role.get("role")
            if not rn:
                continue
            rr = self._extract_role(role, ocr_data)
            roles_results[rn] = rr
            if rr["status"] != "NOT_FOUND":
                any_role_label_found = True

        # legacy manufacturer_packer_importer: prefer roles; fallback to pure org detection
        mp_value = None
        mp_confidence = None
        mp_evidence = []
        for pref in (
            "manufacturer",
            "packer",
            "importer",
            "marketed_by",
            "manufactured_for",
        ):
            r = roles_results.get(pref)
            if r and r.get("organization"):
                mp_value = r["organization"]
                mp_confidence = r["organization_confidence"]
                mp_evidence = r.get("evidence", [])
                break

        if not mp_value and not any_role_label_found:
            fallback_org = self._fallback_organization(ocr_data)
            if fallback_org:
                mp_value = fallback_org.get("text")
                mp_confidence = fallback_org.get("confidence")
                mp_evidence = [{"label": None, "value": {
                    "text": fallback_org.get("text"),
                    "confidence": fallback_org.get("confidence"),
                    "bounding_box": fallback_org.get("bounding_box"),
                }}]

        extracted["manufacturer_packer_importer"] = {
            "value": mp_value,
            "confidence": mp_confidence,
            "evidence": list(mp_evidence),
            "status": "OK" if mp_value else "NOT_FOUND",
        }

        for rn, rd in roles_results.items():
            extracted[rn] = {
                "value": rd.get("organization"),
                "confidence": rd.get("organization_confidence"),
                "address": rd.get("address"),
                "address_confidence": rd.get("address_confidence"),
                "status": rd.get("status", "NOT_FOUND"),
                "evidence": rd.get("evidence", []),
            }

        # address aggregation from roles
        role_address_text = None
        role_address_conf = None
        role_address_ev = []
        for pref in (
            "manufacturer",
            "packer",
            "importer",
            "marketed_by",
            "manufactured_for",
        ):
            r = roles_results.get(pref)
            if r and r.get("address"):
                role_address_text = r["address"]
                role_address_conf = r["address_confidence"]
                role_address_ev = r.get("evidence", [])
                break

        if not role_address_text and mp_value:
            dummy_anchor = {
                "text": mp_value,
                "bounding_box": None,
                "confidence": mp_confidence,
            }
            # need a real bounding box — find the OCR item matching mp_value
            for item in ocr_data:
                if str(item.get("text", "")).strip() == mp_value:
                    dummy_anchor["bounding_box"] = item.get("bounding_box")
                    dummy_anchor["confidence"] = item.get("confidence")
                    break
            if dummy_anchor["bounding_box"]:
                fa = self.find_address_near(dummy_anchor, ocr_data)
                if fa:
                    role_address_text = fa["text"]
                    role_address_conf = fa["confidence"]
                    role_address_ev = [{"value": {
                        "text": fa["text"],
                        "confidence": fa["confidence"],
                        "bounding_box": fa["bounding_box"],
                    }}]

        # schema fields loop
        for field in schema.get("fields", []):
            fn = field.get("name")
            labels = field.get("labels", [])
            value_type = field.get("value_type", "text")

            result = {
                "value": None,
                "confidence": None,
                "evidence": [],
                "status": "NOT_FOUND",
            }

            if fn == "manufacturer_packer_importer":
                continue

            if fn == "address":
                if role_address_text:
                    result["value"] = role_address_text
                    result["confidence"] = role_address_conf
                    result["evidence"] = list(role_address_ev)
                    result["status"] = "OK"

            if result["value"] is None:
                matches = self._find_label_matches(ocr_data, labels)
                best_value = None
                best_label_item = None
                best_score = -1e18
                reject_nutrition = fn in (
                    "net_quantity",
                    "net_weight",
                    "net_content",
                    "quantity",
                )
                for m in matches:
                    ocr_data_copy = list(ocr_data)
                    ocr_data_copy[m["index"]] = m["item"]
                    v = self.find_associated_value(
                        m["index"],
                        value_type,
                        ocr_data_copy,
                        reject_nutrition_context=reject_nutrition,
                    )
                    if v:
                        sc = float(v.get("score", 0) or 0)
                        if sc > best_score:
                            best_score = sc
                            best_value = v
                            best_label_item = m["item"]
                if best_value:
                    result["value"] = best_value["text"]
                    result["confidence"] = best_value["confidence"]
                    result["evidence"].append(self.build_evidence(best_label_item, best_value))
                    result["status"] = "OK"
                else:
                    if any(float(m["item"].get("confidence", 0) or 0) >= 0.75 for m in matches):
                        result["status"] = "VERIFY"

            extracted[fn] = result

        # consumer care last-ditch: any valid contact with label nearby
        cc = extracted.get("consumer_care")
        if cc and cc.get("value") is None:
            cc_labels = schema_field_labels(schema, "consumer_care")
            label_matches = self._find_label_matches(ocr_data, cc_labels) or []
            for i, item in enumerate(ocr_data):
                t = str(item.get("text", "")).strip()
                conf = float(item.get("confidence", 0) or 0)
                if self.valid_value("contact", t) and conf >= 0.5:
                    any_close = False
                    for m in label_matches:
                        lb = m["item"].get("bounding_box", [0, 0, 0, 0])
                        cb = item.get("bounding_box", [0, 0, 0, 0])
                        if self.distance(lb, cb) < 500:
                            any_close = True
                            break
                    if not label_matches:
                        any_close = True
                    if any_close:
                        cc["value"] = t
                        cc["confidence"] = conf
                        cc["evidence"].append({
                            "value": {
                                "text": t,
                                "confidence": conf,
                                "bounding_box": item.get("bounding_box"),
                            }
                        })
                        cc["status"] = "OK"
                        break

        if "other_declarations" in extracted:
            od = extracted["other_declarations"]
            od["value"] = None
            od["status"] = "NOT_FOUND"

        return extracted


def schema_field_labels(schema, field_name):
    for f in schema.get("fields", []):
        if f.get("name") == field_name:
            return f.get("labels", [])
    return []
