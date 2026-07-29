"""
GEIF - Construction du corpus d'entraînement
==============================================
Lance l'OCR sur l'ensemble du dataset synthétique et sauvegarde le texte
brut + label associé, pour entraîner le classifieur de type de document.
"""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "cv_ocr"))
from ocr import extract_text  # noqa: E402


def build_corpus(dataset_dir: str, out_path: str):
    dataset_dir = Path(dataset_dir)
    with open(dataset_dir / "manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)

    corpus = []
    for i, record in enumerate(manifest):
        img_path = dataset_dir / "images" / record["filename"]
        text = extract_text(str(img_path))
        corpus.append({
            "filename": record["filename"],
            "text": text,
            "label": record["type_document"],
            "is_anomaly": record["_is_anomaly"],
        })
        if (i + 1) % 10 == 0:
            print(f"  ...{i+1}/{len(manifest)} documents traités")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    print(f"✅ Corpus sauvegardé : {out_path} ({len(corpus)} documents)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="./synthetic_dataset")
    parser.add_argument("--out", default="./training_corpus.json")
    args = parser.parse_args()
    build_corpus(args.dataset, args.out)
