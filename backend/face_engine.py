"""Face engine for Reunite.

Primary: DeepFace (SFace model) if the `deepface` package is installed.
Fallback: OpenCV's built-in YuNet detector + SFace recogniser (same SFace
model DeepFace uses, run directly through OpenCV, so no TensorFlow needed).

Both paths are pre-trained: no model training is required.
"""
from __future__ import annotations

import os
import numpy as np
import cv2

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
YUNET = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")
SFACE = os.path.join(MODEL_DIR, "face_recognition_sface_2021dec.onnx")

# SFace cosine similarity threshold recommended by OpenCV for "same person".
SAME_PERSON_COSINE = 0.363


class FaceEngine:
    def __init__(self) -> None:
        self.backend = "none"
        self._deepface = None
        self._detector = None
        self._recognizer = None
        try:
            from deepface import DeepFace  # type: ignore

            self._deepface = DeepFace
            self.backend = "deepface"
        except Exception:
            if os.path.exists(YUNET) and os.path.exists(SFACE):
                self._detector = cv2.FaceDetectorYN.create(YUNET, "", (320, 320), 0.8, 0.3, 5000)
                self._recognizer = cv2.FaceRecognizerSF.create(SFACE, "")
                self.backend = "opencv-sface"

    @property
    def available(self) -> bool:
        return self.backend != "none"

    def embed(self, image_bytes: bytes) -> np.ndarray | None:
        """Return a normalised face embedding for the largest face, or None."""
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        # Keep detection fast and consistent on big phone photos.
        h, w = img.shape[:2]
        scale = 1024 / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)))

        if self.backend == "deepface":
            try:
                reps = self._deepface.represent(img, model_name="SFace", detector_backend="opencv")
                if not reps:
                    return None
                best = max(reps, key=lambda r: r["facial_area"]["w"] * r["facial_area"]["h"])
                vec = np.asarray(best["embedding"], dtype=np.float32)
            except Exception:
                return None
        elif self.backend == "opencv-sface":
            h, w = img.shape[:2]
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(img)
            if faces is None or len(faces) == 0:
                return None
            face = max(faces, key=lambda f: f[2] * f[3])
            aligned = self._recognizer.alignCrop(img, face)
            vec = self._recognizer.feature(aligned).flatten().astype(np.float32)
        else:
            return None

        n = np.linalg.norm(vec)
        return vec / n if n else None

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))

    @staticmethod
    def confidence(cos: float) -> float:
        """Map cosine similarity to a 0-100 confidence score.

        Calibrated so the OpenCV same-person threshold (0.363) sits at 50%,
        ~0.55 reads as ~90% and clearly different faces fall well below 25%.
        """
        z = (cos - SAME_PERSON_COSINE) * 12.0
        return round(100.0 / (1.0 + np.exp(-z)), 1)


engine = FaceEngine()
