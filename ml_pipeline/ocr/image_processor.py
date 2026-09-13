import cv2
from pathlib import Path


class ImageProcessor:

    def load_image(self, image_path):
        image = cv2.imread(str(image_path))

        if image is None:
            raise FileNotFoundError(
                f"Could not read image: {image_path}"
            )

        return image

    def preprocess(self, image):
        # Denoise
        image = cv2.GaussianBlur(
            image,
            (3, 3),
            0
        )

        # Improve contrast
        image = cv2.convertScaleAbs(
            image,
            alpha=1.2,
            beta=0
        )

        return image

    def process(self, image_path, output_path):
        image = self.load_image(image_path)

        processed = self.preprocess(image)

        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        success = cv2.imwrite(
            str(output_path),
            processed
        )

        if not success:
            raise IOError(
                f"Could not save processed image: {output_path}"
            )

        return processed