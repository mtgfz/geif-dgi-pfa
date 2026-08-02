"""
GEIF — Comparaison de modèles pré-entraînés (Transfer Learning)
====================================================================
Compare 3 architectures pré-entraînées sur ImageNet (transfer learning) pour
la classification visuelle des documents, en complément du CNN from-scratch
(train_cnn_classifier.py) :

    - MobileNetV2   : léger, rapide, bon compromis pour un déploiement modeste
    - ResNet50      : plus profond, référence historique du transfer learning
    - EfficientNetB0 : bon compromis précision/taille, plus récent

Principe : on gèle les couches pré-entraînées (features génériques apprises
sur ImageNet) et on n'entraîne qu'une petite tête de classification dessus.

⚠️ IMPORTANT — chaque architecture attend une normalisation d'image
DIFFÉRENTE (c'est une source d'erreur classique en transfer learning) :
ResNet50 attend une soustraction de moyenne façon Caffe, EfficientNet a son
propre schéma, MobileNetV2 attend du [-1, 1]. On utilise donc le
preprocess_input propre à chaque modèle plutôt qu'une simple division par
255 appliquée uniformément — sans ça, certains modèles n'apprennent
quasiment rien (loss qui stagne), ce qui n'a rien à voir avec leur qualité
réelle.

Usage :
    python compare_pretrained_models.py --dataset ../data/processed/synthetic_dataset --epochs 10
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from PIL import Image

IMG_SIZE = (128, 128)

ARCHITECTURES = {
    "MobileNetV2": (tf.keras.applications.MobileNetV2, tf.keras.applications.mobilenet_v2.preprocess_input),
    "ResNet50": (tf.keras.applications.ResNet50, tf.keras.applications.resnet50.preprocess_input),
    "EfficientNetB0": (tf.keras.applications.EfficientNetB0, tf.keras.applications.efficientnet.preprocess_input),
}


def load_images_and_labels(dataset_dir: str):
    """Charge les images en RGB, NON normalisées ici (0-255) — chaque
    architecture applique son propre preprocess_input juste avant
    l'entraînement, pour une comparaison équitable."""
    dataset_dir = Path(dataset_dir)
    with open(dataset_dir / "manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)

    images, labels = [], []
    for rec in manifest:
        img_path = dataset_dir / "images" / rec["filename"]
        img = Image.open(img_path).convert("RGB").resize(IMG_SIZE)
        images.append(np.array(img, dtype=np.float32))
        labels.append(rec["type_document"])

    X = np.array(images)
    return X, np.array(labels)


def build_transfer_model(base_architecture, n_classes: int, pretrained: bool = True):
    weights = "imagenet" if pretrained else None
    base_model = base_architecture(
        weights=weights, include_top=False, input_shape=(IMG_SIZE[0], IMG_SIZE[1], 3)
    )
    base_model.trainable = False  # on gèle les couches pré-entraînées

    model = models.Sequential([
        base_model,
        layers.GlobalAveragePooling2D(),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.3),
        layers.Dense(n_classes, activation="softmax"),
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model


def compare_all_architectures(dataset_dir: str, epochs: int, pretrained: bool = True):
    print("Chargement des images...")
    X_raw, y_raw = load_images_and_labels(dataset_dir)
    le = LabelEncoder()
    y = le.fit_transform(y_raw)

    idx_train, idx_test = train_test_split(
        np.arange(len(X_raw)), test_size=0.2, random_state=42, stratify=y
    )
    print(f"Train : {len(idx_train)} | Test : {len(idx_test)}\n")

    results = {}
    for name, (arch, preprocess_fn) in ARCHITECTURES.items():
        print(f"{'='*60}\n{name}\n{'='*60}")
        t0 = time.time()
        try:
            # Prétraitement SPÉCIFIQUE à cette architecture (voir docstring)
            X_processed = preprocess_fn(X_raw.copy())
            X_train, X_test = X_processed[idx_train], X_processed[idx_test]
            y_train, y_test = y[idx_train], y[idx_test]

            model = build_transfer_model(arch, n_classes=len(le.classes_), pretrained=pretrained)
            model.fit(X_train, y_train, validation_data=(X_test, y_test),
                      epochs=epochs, batch_size=8, verbose=2)
            test_loss, test_acc = model.evaluate(X_test, y_test, verbose=0)
            duration = time.time() - t0
            results[name] = {"accuracy": round(float(test_acc), 4), "duration_sec": round(duration, 1)}
            print(f"✅ {name} : accuracy={test_acc:.3f} en {duration:.1f}s\n")
        except Exception as e:
            results[name] = {"error": str(e)[:200]}
            print(f"❌ {name} a échoué : {str(e)[:200]}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="../data/processed/synthetic_dataset")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--no-pretrained", action="store_true",
                         help="Test structurel sans télécharger de vrais poids ImageNet")
    parser.add_argument("--out", default="./pretrained_comparison_results.json")
    args = parser.parse_args()

    results = compare_all_architectures(args.dataset, args.epochs, pretrained=not args.no_pretrained)

    print(f"\n{'='*60}\nRÉSUMÉ COMPARATIF\n{'='*60}")
    for name, res in results.items():
        print(f"{name}: {res}")

    best = max(
        (r for r in results.values() if "accuracy" in r),
        key=lambda r: r["accuracy"], default=None
    )
    if best:
        best_name = [n for n, r in results.items() if r == best][0]
        print(f"\n🏆 Meilleur modèle : {best_name} (accuracy={best['accuracy']})")

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Résultats sauvegardés : {args.out}")
