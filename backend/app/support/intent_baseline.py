"""
Classic NLP baseline for intent recognition: TF-IDF features + logistic regression.

Trained on the "train" split of eval/intent_dataset.csv. Used as the fallback classifier when the
LLM is unavailable, and as the comparison baseline in eval/evaluate_intents.py.
"""
import csv
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion

DATASET_PATH = Path(__file__).resolve().parent.parent.parent / "eval" / "intent_dataset.csv"


def load_dataset(split: str | None = None) -> Tuple[List[str], List[str]]:
    """Load (texts, intents) from the labeled dataset, optionally filtered by split."""
    texts, labels = [], []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if split is None or row["split"] == split:
                texts.append(row["text"])
                labels.append(row["intent"])
    return texts, labels


def build_pipeline() -> Pipeline:
    # Word n-grams capture phrases ("where is my"), char n-grams make it robust to typos
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)),
    ])
    return Pipeline([
        ("features", features),
        ("clf", LogisticRegression(max_iter=2000, C=5.0, class_weight="balanced")),
    ])


@lru_cache()
def get_model() -> Pipeline:
    texts, labels = load_dataset("train")
    model = build_pipeline()
    model.fit(texts, labels)
    return model


def predict_intent(text: str) -> Tuple[str, float]:
    """Return (intent, probability) from the baseline classifier."""
    model = get_model()
    probs = model.predict_proba([text])[0]
    best = probs.argmax()
    return str(model.classes_[best]), float(probs[best])
