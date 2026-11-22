"""
Evaluation metrics for the support bot, computed from logged conversations and feedback.

Covers the four capstone metrics:
  - Intent classification accuracy  (offline, from eval/results/intent_eval.json)
  - Response appropriateness        (manual review, from eval/results/appropriateness_reviewed.csv)
  - Average response time           (message_analysis.response_time_ms, per channel)
  - User satisfaction score         (feedback table, per channel)
"""
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models import ChatSession, Feedback, MessageAnalysis, SupportTicket

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "results"
RUBRIC_COLUMNS = ["correct", "helpful", "polite"]


def _latency_stats(values: List[float]) -> Dict:
    if not values:
        return {"count": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None}
    arr = np.array(values)
    return {"count": len(values), "mean_ms": round(float(arr.mean()), 1),
            "p50_ms": round(float(np.percentile(arr, 50)), 1), "p95_ms": round(float(np.percentile(arr, 95)), 1)}


def _satisfaction(rows: List[Feedback]) -> Dict:
    if not rows:
        return {"count": 0, "average_rating": None, "resolved_pct": None, "distribution": {str(i): 0 for i in range(1, 6)}}
    resolved = [r.resolved for r in rows if r.resolved is not None]
    dist = Counter(r.rating for r in rows)
    return {"count": len(rows), "average_rating": round(sum(r.rating for r in rows) / len(rows), 2),
            "resolved_pct": round(100 * sum(resolved) / len(resolved), 1) if resolved else None,
            "distribution": {str(i): dist.get(i, 0) for i in range(1, 6)}}


def _intent_eval() -> Optional[Dict]:
    path = RESULTS_DIR / "intent_eval.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {name: {"accuracy": r["accuracy"], "macro_f1": r["macro_f1"], "test_size": r["test_size"]}
            for name, r in data.get("classifiers", {}).items()} | {"evaluated_at": data.get("evaluated_at")}


def _appropriateness() -> Optional[Dict]:
    path = RESULTS_DIR / "appropriateness_reviewed.csv"
    if not path.exists():
        return None
    scores: Dict[str, List[float]] = {c: [] for c in RUBRIC_COLUMNS}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for c in RUBRIC_COLUMNS:
                try:
                    scores[c].append(float(row.get(c) or ""))
                except ValueError:
                    pass
    reviewed = max((len(v) for v in scores.values()), default=0)
    if not reviewed:
        return None
    per_dim = {c: round(sum(v) / len(v), 2) for c, v in scores.items() if v}
    return {"reviewed_turns": reviewed, "scores": per_dim,
            "overall": round(sum(per_dim.values()) / len(per_dim), 2)}


def compute_metrics(db: Session) -> Dict:
    analyses = db.query(MessageAnalysis).all()
    feedback = db.query(Feedback).all()
    sessions = db.query(ChatSession).filter(ChatSession.channel.isnot(None)).all()
    tickets = db.query(SupportTicket).all()

    channels = ["text", "voice"]
    response_time = {ch: _latency_stats([a.response_time_ms for a in analyses
                                         if a.channel == ch and a.response_time_ms is not None]) for ch in channels}
    response_time["all"] = _latency_stats([a.response_time_ms for a in analyses if a.response_time_ms is not None])

    satisfaction = {ch: _satisfaction([f for f in feedback if f.channel == ch]) for ch in channels}
    satisfaction["all"] = _satisfaction(feedback)

    active_sessions = {a.session_id for a in analyses}
    escalated_sessions = {a.session_id for a in analyses if a.escalated}

    return {
        "intent_accuracy": _intent_eval(),
        "appropriateness": _appropriateness(),
        "response_time": response_time,
        "satisfaction": satisfaction,
        "volume": {
            "sessions": len(active_sessions),
            "sessions_by_channel": dict(Counter(s.channel for s in sessions if s.id in active_sessions)),
            "user_turns": len(analyses),
        },
        "intent_distribution": dict(Counter(a.intent for a in analyses).most_common()),
        "classifier_usage": dict(Counter(a.classifier or "llm" for a in analyses)),
        "sentiment_distribution": dict(Counter(a.sentiment_label or "neutral" for a in analyses)),
        "average_sentiment": round(float(np.mean([a.sentiment_score for a in analyses if a.sentiment_score is not None])), 2)
        if analyses else None,
        "escalation": {
            "escalated_sessions": len(escalated_sessions),
            "rate_pct": round(100 * len(escalated_sessions) / len(active_sessions), 1) if active_sessions else None,
            "open_tickets": sum(t.status != "resolved" for t in tickets),
            "tickets_by_priority": dict(Counter(t.priority for t in tickets)),
        },
    }
