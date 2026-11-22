"""
NLP layer for the customer support bot: intent recognition, named entity extraction and sentiment.

The primary classifier is a single structured-output LLM call. Rule-based (regex) entity
extraction runs on every message and is merged with the LLM entities. If the LLM call fails,
the TF-IDF + logistic regression baseline in intent_baseline.py and a small sentiment lexicon
are used instead, so the bot keeps working without the API.
"""
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from app.config import settings
from app.services.document_service import get_openai_client

logger = logging.getLogger(__name__)

INTENTS = [
    "faq",             # policy / general questions (shipping, refunds, payments, warranty, account)
    "order_status",    # where is my order, tracking, delivery date
    "return_request",  # return / refund / exchange an item
    "cancel_order",    # cancel an order
    "product_info",    # product availability, price, details
    "talk_to_human",   # explicitly asks for a person
    "complaint",       # negative experience without a clear actionable request
    "greeting",        # hi / thanks / bye
    "other",           # out of scope
]

# Order numbers look like ORD-10023. Speech-to-text often produces "order 10023" or "order number 10023".
ORDER_RE = re.compile(r"\b(?:ORD|order(?:\s*(?:number|no\.?|id|#))?)[\s#:\-]*(\d{5})\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")
AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr|\$)\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)", re.IGNORECASE)

NEGATIVE_WORDS = {
    "worst", "terrible", "horrible", "awful", "angry", "furious", "useless", "pathetic", "disgusting",
    "broken", "damaged", "late", "never", "scam", "fraud", "hate", "disappointed", "frustrated",
    "ridiculous", "unacceptable", "rude", "waste", "defective", "wrong", "bad", "poor",
}
POSITIVE_WORDS = {
    "thanks", "thank", "great", "awesome", "perfect", "love", "excellent", "good", "helpful",
    "appreciate", "nice", "wonderful", "happy",
}

ANALYSIS_PROMPT = f"""You are the NLP component of an e-commerce customer support bot.
Analyze the customer's latest message (use the recent conversation only to resolve references).
Return ONLY a JSON object with these keys:
- "intent": one of {INTENTS}
- "confidence": number 0-1
- "entities": object with any of these keys that are present:
    "order_number" (format ORD-12345), "product" (product name), "reason" (return/cancel/complaint reason),
    "date", "email", "phone", "amount"
- "sentiment_label": "positive", "neutral" or "negative"
- "sentiment_score": number from -1 to 1, calibrated like this:
    -1.0 to -0.7: angry, abusive, shouting, threatening to leave, or demanding escalation in frustration
    -0.6 to -0.3: clearly unhappy but calm, e.g. politely reporting a broken, late or wrong item
    -0.2 to 0.2: neutral requests and questions
     0.3 to 1.0: friendly, thankful, satisfied

Intent guidance: questions about policies (shipping times, refund policy, payment methods, warranty,
account) are "faq". Asking where an order is or when it arrives is "order_status". Wanting to return,
exchange or get a refund for an item is "return_request". Explicitly asking for a human/agent/person is
"talk_to_human" even if angry. Venting without a concrete request is "complaint"."""


@dataclass
class Analysis:
    intent: str
    confidence: float
    entities: Dict[str, str] = field(default_factory=dict)
    sentiment_label: str = "neutral"
    sentiment_score: float = 0.0
    classifier: str = "llm"

    def to_dict(self) -> Dict:
        return asdict(self)


def normalize_order_number(text: str) -> Optional[str]:
    """Return ORD-xxxxx for any order number mention in the text, or None."""
    match = ORDER_RE.search(text or "")
    if match:
        return f"ORD-{match.group(1)}"
    digits = re.fullmatch(r"\s*#?(\d{5})\s*", text or "")
    return f"ORD-{digits.group(1)}" if digits else None


def extract_entities_regex(text: str) -> Dict[str, str]:
    """Rule-based named entity extraction for the patterns that regex handles reliably."""
    entities: Dict[str, str] = {}
    order_number = normalize_order_number(text)
    if order_number:
        entities["order_number"] = order_number
    if m := EMAIL_RE.search(text):
        entities["email"] = m.group(0)
    if m := PHONE_RE.search(text):
        entities["phone"] = m.group(0)
    if m := AMOUNT_RE.search(text):
        entities["amount"] = m.group(1)
    return entities


def lexicon_sentiment(text: str) -> tuple[str, float]:
    """Very small lexicon-based sentiment fallback."""
    words = re.findall(r"[a-z']+", text.lower())
    neg = sum(w in NEGATIVE_WORDS for w in words)
    pos = sum(w in POSITIVE_WORDS for w in words)
    # Shouting and repeated exclamation marks push towards negative
    if text.count("!") >= 2 or (len(text) > 8 and text.isupper()):
        neg += 1
    score = 0.0 if neg == pos == 0 else (pos - neg) / (pos + neg)
    score = max(-1.0, min(1.0, score * min(1.0, 0.4 + 0.3 * (pos + neg))))
    label = "negative" if score <= -0.2 else "positive" if score >= 0.2 else "neutral"
    return label, round(score, 2)


def _llm_analyze(message: str, history: Optional[List[Dict]]) -> Analysis:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI client not configured")

    context = ""
    if history:
        context = "Recent conversation:\n" + "\n".join(
            f"{m['role']}: {m['content'][:300]}" for m in history[-4:]
        ) + "\n\n"

    response = client.chat.completions.create(
        model=settings.SUPPORT_MODEL,
        messages=[
            {"role": "system", "content": ANALYSIS_PROMPT},
            {"role": "user", "content": f"{context}Customer message: {message}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=300,
    )
    data = json.loads(response.choices[0].message.content)

    intent = data.get("intent", "other")
    if intent not in INTENTS:
        intent = "other"
    entities = {k: str(v) for k, v in (data.get("entities") or {}).items() if v not in (None, "", [])}
    score = float(data.get("sentiment_score", 0.0))
    label = data.get("sentiment_label") or ("negative" if score < -0.2 else "positive" if score > 0.2 else "neutral")
    return Analysis(
        intent=intent,
        confidence=float(data.get("confidence", 0.8)),
        entities=entities,
        sentiment_label=label,
        sentiment_score=max(-1.0, min(1.0, score)),
        classifier="llm",
    )


def classify_intent_llm(message: str) -> str:
    """Intent only, used by the evaluation script."""
    return _llm_analyze(message, None).intent


def analyze(message: str, history: Optional[List[Dict]] = None) -> Analysis:
    """
    Analyze one customer message.

    Args:
        message: The customer's message (typed or transcribed)
        history: Optional recent messages [{"role": ..., "content": ...}] to resolve references

    Returns:
        Analysis with intent, confidence, entities, sentiment and which classifier produced it
    """
    regex_entities = extract_entities_regex(message)
    try:
        result = _llm_analyze(message, history)
    except Exception as e:
        logger.warning(f"LLM analysis failed, falling back to baseline classifier: {e}")
        from app.support.intent_baseline import predict_intent
        intent, confidence = predict_intent(message)
        label, score = lexicon_sentiment(message)
        result = Analysis(intent=intent, confidence=confidence, sentiment_label=label,
                          sentiment_score=score, classifier="baseline")

    # Regex entities are more reliable for structured values, so they win on conflicts
    if "order_number" in result.entities:
        normalized = normalize_order_number(result.entities["order_number"])
        if normalized:
            result.entities["order_number"] = normalized
    result.entities.update(regex_entities)
    return result
