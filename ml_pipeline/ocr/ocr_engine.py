from paddleocr import PaddleOCR


class OCREngine:

    def __init__(self):
        self.ocr = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False
        )

    def extract(self, image):
        results = self.ocr.predict(image)
        return results