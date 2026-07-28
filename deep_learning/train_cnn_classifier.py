"""
GEIF — Classification visuelle des documents (Deep Learning / CV)
======================================================================
Complète le classifieur texte (TF-IDF + Régression Logistique) par un
classifieur qui regarde directement l'IMAGE du document — sa mise en page
(position des blocs, densité de texte, structure visuelle) plutôt que son
contenu textuel. Utile quand l'OCR est de mauvaise qualité (scan bruité) :
la mise en page reste identifiable même si le texte est mal lu.

Architecture : petit CNN (3 blocs conv/pool) entraîné sur les images du
dataset synthétique, redimensionnées en niveaux de gris.

Usage :
    python train_cnn_classifier.py --dataset ../data/processed/synthetic_dataset --epochs 15
"""
import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from PIL import Image

IMG_SIZE = (128, 128)


def load_images_and_labels(dataset_dir: str):
    dataset_dir = Path(dataset_dir)
    with open(dataset_dir / "manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)

    images, labels = [], []
    for rec in manifest:
        img_path = dataset_dir / "images" / rec["filename"]
        img = Image.open(img_path).convert("L").resize(IMG_SIZE)
        images.append(np.array(img) / 255.0)
        labels.append(rec["type_document"])

    X = np.array(images).reshape(-1, IMG_SIZE[0], IMG_SIZE[1], 1)
    return X, np.array(labels)


def build_cnn(n_classes: int):
    model = models.Sequential([
        layers.Input(shape=(IMG_SIZE[0], IMG_SIZE[1], 1)),
        layers.Conv2D(16, (3, 3), activation="relu"),
        layers.MaxPooling2D((2, 2)),
        layers.Conv2D(32, (3, 3), activation="relu"),
        layers.MaxPooling2D((2, 2)),
        layers.Conv2D(64, (3, 3), activation="relu"),
        layers.MaxPooling2D((2, 2)),
        layers.Flatten(),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.3),
        layers.Dense(n_classes, activation="softmax"),
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="../data/processed/synthetic_dataset")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--model-out", default="./cnn_layout_classifier.keras")
    args = parser.parse_args()

    print("Chargement des images...")
    X, y_raw = load_images_and_labels(args.dataset)

    le = LabelEncoder()
    y = le.fit_transform(y_raw)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"Train : {len(X_train)} images | Test : {len(X_test)} images")

    model = build_cnn(n_classes=len(le.classes_))
    model.summary()

    history = model.fit(
        X_train, y_train,
        validation_data=(X_test, y_test),
        epochs=args.epochs,
        batch_size=8,
        verbose=2,
    )

    test_loss, test_acc = model.evaluate(X_test, y_test, verbose=0)
    print(f"\n✅ Accuracy test : {test_acc*100:.1f}%")

    model.save(args.model_out)
    print(f"✅ Modèle sauvegardé : {args.model_out}")

    # Sauvegarde du mapping label <-> index pour l'inférence
    with open(Path(args.model_out).parent / "label_classes.json", "w") as f:
        json.dump(list(le.classes_), f)
