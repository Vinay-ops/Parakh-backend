import json
from pathlib import Path


class OCRParser:

    @staticmethod
    def parse(results):
        parsed = []

        for result in results:
            data = result.json

            if not data or "res" not in data:
                continue

            res = data["res"]

            texts = res.get("rec_texts", [])
            scores = res.get("rec_scores", [])
            boxes = res.get("rec_boxes", [])

            for text, score, box in zip(texts, scores, boxes):
                parsed.append({
                    "text": str(text),
                    "confidence": float(score),
                    "bounding_box": box
                })

        return parsed

    @staticmethod
    def save(data, output_path):
        output_path = Path(output_path)
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
                data,
                file,
                indent=4,
                ensure_ascii=False
            )