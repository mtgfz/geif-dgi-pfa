"""
GEIF - Classification automatique du type de document
=========================================================
Pipeline TF-IDF + Régression Logistique pour prédire le type de document
fiscal à partir du texte extrait par OCR.

Entraînement :
    python classifier.py train --corpus ../data/training_corpus.json --model ./model.joblib

Inférence (utilisé par l'API) :
    from classifier import DocumentClassifier
    clf = DocumentClassifier.load("./model.joblib")
    label, confidence = clf.predict(raw_text)
"""
import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


class DocumentClassifier:
    def __init__(self, pipeline: Pipeline | None = None):
        self.pipeline = pipeline

    @classmethod
    def train(cls, texts, labels, test_size=0.2):
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)),
            ("clf", LogisticRegression(max_iter=1000)),
        ])
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=test_size, random_state=42, stratify=labels
        )
        pipeline.fit(X_train, y_train)
        report = classification_report(y_test, pipeline.predict(X_test))
        print(report)
        return cls(pipeline), report

    def predict(self, text: str):
        proba = self.pipeline.predict_proba([text])[0]
        classes = self.pipeline.classes_
        best_idx = proba.argmax()
        return classes[best_idx], float(proba[best_idx])

    def save(self, path):
        joblib.dump(self.pipeline, path)

    @classmethod
    def load(cls, path):
        pipeline = joblib.load(path)
        return cls(pipeline)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["train"])
    parser.add_argument("--corpus", default="../data/training_corpus.json")
    parser.add_argument("--model", default="./model.joblib")
    args = parser.parse_args()

    if args.action == "train":
        with open(args.corpus, encoding="utf-8") as f:
            corpus = json.load(f)
        texts = [d["text"] for d in corpus]
        labels = [d["label"] for d in corpus]

        clf, report = DocumentClassifier.train(texts, labels)
        clf.save(args.model)
        print(f"✅ Modèle sauvegardé : {args.model}")

        # Quick sanity check on a training example
        sample_text, sample_label = texts[0], labels[0]
        pred, conf = clf.predict(sample_text)
        print(f"\nSanity check → attendu: {sample_label} | prédit: {pred} (confiance {conf:.2f})")
