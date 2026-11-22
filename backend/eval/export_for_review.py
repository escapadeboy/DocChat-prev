"""
Response appropriateness (evaluation metric 2, manual).

Exports a random sample of real bot turns (customer message + bot reply + detected intent) to
eval/results/appropriateness_review.csv with empty rubric columns. Reviewers score each turn 1-5:
  correct  - the facts / action are right (order status, policy, return created, ...)
  helpful  - it resolves or clearly moves the customer's issue forward
  polite   - tone is courteous and empathetic
Save the filled file as eval/results/appropriateness_reviewed.csv; GET /support/metrics and the
Metrics page then report the averages.

Usage (from the backend directory):
    python eval/export_for_review.py --n 50
"""
import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import ChatMessage, MessageAnalysis

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="Number of turns to sample")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        turns = []
        for analysis in db.query(MessageAnalysis).order_by(MessageAnalysis.id).all():
            user_msg = db.get(ChatMessage, analysis.message_id)
            reply = (db.query(ChatMessage)
                     .filter(ChatMessage.session_id == analysis.session_id, ChatMessage.id > analysis.message_id,
                             ChatMessage.role == "assistant")
                     .order_by(ChatMessage.id).first())
            if user_msg and reply:
                turns.append({"turn_id": analysis.id, "channel": analysis.channel, "intent": analysis.intent,
                              "sentiment": analysis.sentiment_label, "escalated": analysis.escalated,
                              "customer_message": user_msg.content, "bot_reply": reply.content})
    finally:
        db.close()

    random.Random(args.seed).shuffle(turns)
    sample = sorted(turns[:args.n], key=lambda t: t["turn_id"])

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / "appropriateness_review.csv"
    fields = list(sample[0].keys()) + ["correct", "helpful", "polite", "notes"] if sample else []
    with open(out, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel shows ₹ correctly
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sample)
    print(f"Exported {len(sample)} of {len(turns)} turns to {out}")
    print("Score correct/helpful/polite 1-5, then save as appropriateness_reviewed.csv in the same folder.")


if __name__ == "__main__":
    main()
