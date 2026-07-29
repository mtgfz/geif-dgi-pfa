"""
GEIF — Inférence du CNN de classification visuelle
=======================================================
Module léger pour charger le CNN entraîné (train_cnn_classifier.py) et
prédire le type de document à partir de son image, sans dépendre du texte
OCR. Utilisé par l'API en complément du classifieur texte (ensemble).
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

IMG_SIZE = (128, 128)

_model = None
_classes = None


def _lazy_load(model_path: str, classes_path: str):
    global _model, _classes
    if _model is None:
        import tensorflow as tf  # import différé : ne charge TensorFlow que si utilisé
        _model = tf.keras.models.load_model(model_path)
        with open(classes_path) as f:
            _classes = json.load(f)
    return _model, _classes


def predict_from_image(image_path: str, model_path: str, classes_path: str):
    """Retourne (label_prédit, confiance) à partir de l'image seule."""
    model, classes = _lazy_load(model_path, classes_path)

    img = Image.open(image_path).convert("L").resize(IMG_SIZE)
    arr = np.array(img) / 255.0
    arr = arr.reshape(1, IMG_SIZE[0], IMG_SIZE[1], 1)

    proba = model.predict(arr, verbose=0)[0]
    best_idx = int(np.argmax(proba))
    return classes[best_idx], float(proba[best_idx])


def is_available(model_path: str, classes_path: str) -> bool:
    return Path(model_path).exists() and Path(classes_path).exists()
