"""
Intent classification accuracy (evaluation metric 1).

Evaluates both intent classifiers on the held-out "test" split of eval/intent_dataset.csv:
  - llm:      the structured-output LLM classifier used by the bot (app/support/nlp.py)
  - baseline: TF-IDF + logistic regression trained on the "train" split (app/support/intent_baseline.py)

Writes eval/results/intent_eval.json (read by GET /support/metrics and the Metrics page)
and, if matplotlib is installed, confusion-matrix PNGs.

Usage (from the backend directory):
    python eval/evaluate_intents.py               # test split only (36 utterances)
    python eval/evaluate_intents.py --llm-all     # also run the LLM on all 216 utterances
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from app.config import settings
from app.support.intent_baseline import build_pipeline, load_dataset
from app.support.nlp import INTENTS, classify_intent_llm

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def score(name: str, y_true, y_pred, latency_ms=None) -> dict:
    report = classification_report(y_true, y_pred, labels=INTENTS, output_dict=True, zero_division=0)
    result = {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "macro_f1": round(f1_score(y_true, y_pred, labels=INTENTS, average="macro", zero_division=0), 4),
        "test_size": len(y_true),
        "per_class": {k: {m: round(v, 3) for m, v in report[k].items()} for k in INTENTS},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=INTENTS).tolist(),
        "errors": [{"expected": t, "predicted": p} for t, p in zip(y_true, y_pred) if t != p],
    }
    if latency_ms is not None:
        result["avg_latency_ms"] = round(latency_ms, 1)
    print(f"\n=== {name}: accuracy {result['accuracy']:.1%}, macro-F1 {result['macro_f1']:.3f} (n={len(y_true)})")
    print(classification_report(y_true, y_pred, labels=INTENTS, zero_division=0))
    return result


def run_llm(texts):
    def one(text):
        start = time.perf_counter()
        try:
            label = classify_intent_llm(text)
        except Exception as e:
            print(f"LLM error on {text!r}: {e}")
            label = "other"
        return label, (time.perf_counter() - start) * 1000
    with ThreadPoolExecutor(max_workers=6) as pool:
        out = list(pool.map(one, texts))
    return [o[0] for o in out], sum(o[1] for o in out) / len(out)


def save_confusion_png(name: str, matrix) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(INTENTS)), INTENTS, rotation=45, ha="right")
    ax.set_yticks(range(len(INTENTS)), INTENTS)
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            if v:
                ax.text(j, i, v, ha="center", va="center", color="white" if v > max(map(max, matrix)) / 2 else "black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(f"Intent confusion matrix ({name})")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / f"confusion_{name}.png", dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm-all", action="store_true", help="Also evaluate the LLM on the full dataset")
    parser.add_argument("--skip-llm", action="store_true", help="Only evaluate the baseline (no API calls)")
    args = parser.parse_args()

    train_x, train_y = load_dataset("train")
    test_x, test_y = load_dataset("test")
    print(f"Dataset: {len(train_x)} train / {len(test_x)} test utterances, {len(INTENTS)} intents")

    results = {}
    model = build_pipeline().fit(train_x, train_y)
    start = time.perf_counter()
    baseline_pred = list(model.predict(test_x))
    results["baseline"] = score("baseline (TF-IDF + LogReg)", test_y, baseline_pred,
                                (time.perf_counter() - start) * 1000 / len(test_x))
    results["baseline"]["errors"] = [{"text": x, "expected": t, "predicted": p}
                                     for x, t, p in zip(test_x, test_y, baseline_pred) if t != p]

    if not args.skip_llm:
        llm_pred, latency = run_llm(test_x)
        results["llm"] = score(f"llm ({settings.SUPPORT_MODEL})", test_y, llm_pred, latency)
        results["llm"]["errors"] = [{"text": x, "expected": t, "predicted": p}
                                    for x, t, p in zip(test_x, test_y, llm_pred) if t != p]
        if args.llm_all:
            all_x, all_y = load_dataset()
            all_pred, latency = run_llm(all_x)
            results["llm_full_dataset"] = score("llm on full dataset", all_y, all_pred, latency)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {"evaluated_at": datetime.now(timezone.utc).isoformat(), "intents": INTENTS, "classifiers": results}
    (RESULTS_DIR / "intent_eval.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for name, r in results.items():
        save_confusion_png(name, r["confusion_matrix"])
    print(f"\nSaved {RESULTS_DIR / 'intent_eval.json'}")


if __name__ == "__main__":
    main()
