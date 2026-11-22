"""
LiveKit voice agent for the ShopEase customer support bot.

Runs as its own process next to the FastAPI backend:
    cd backend
    python -m voice_agent.agent download-files   # once: fetch the Silero VAD model
    python -m voice_agent.agent dev              # connect to LiveKit Cloud and wait for calls

The backend's POST /voice/livekit-token dispatches this worker (agent_name "support-agent") into
a new room, passing {user_id, session_id} as job metadata. The agent then:
  - talks to the customer with OpenAI speech-to-text, LLM and text-to-speech
  - uses the same support tools as the text chat (app/support/tools.py), scoped to that customer
  - runs the NLP analysis + escalation rule on each user turn and logs it (app/support/engine.py)
  - measures response time (end of user speech -> agent starts speaking) for the metrics
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")  # LIVEKIT_* and OPENAI_API_KEY for the LiveKit plugins

from livekit.agents import (Agent, AgentServer, AgentSession, ChatContext, ChatMessage as LKChatMessage,
                            JobContext, JobProcess, RunContext, cli, function_tool, metrics)
from livekit.plugins import openai, silero

from app.config import settings
from app.database import SessionLocal, ensure_schema
from app.models import ChatMessage, ChatSession, MessageAnalysis, User
from app.support import tools
from app.support.engine import SUPPORT_PROMPT, VOICE_STYLE, analysis_note, get_history, record_user_turn

logger = logging.getLogger("support-voice-agent")

# How long a user turn may wait for the NLP analysis before the agent replies anyway.
# If the analysis finishes in time, an escalation note is injected into this reply.
ANALYSIS_WAIT_SECONDS = 1.2


class CallLogger:
    """Persists the voice conversation (messages, analysis, response times) to the database."""

    def __init__(self, user_id: int, session_id: int):
        self.user_id = user_id
        self.session_id = session_id
        self.last_sentiment: Optional[float] = None
        self._rows: List[int] = []         # MessageAnalysis ids, in user-turn order
        self._latencies: List[float] = []  # response times, in the same order
        self._lock = asyncio.Lock()

    def _record_user(self, text: str) -> Dict:
        db = SessionLocal()
        try:
            session = db.get(ChatSession, self.session_id)
            history = get_history(db, self.session_id)
            row, analysis, ticket = record_user_turn(db, session, self.user_id, text, history)
            db.commit()
            return {"row_id": row.id, "analysis": analysis, "ticket": ticket}
        finally:
            db.close()

    def _save_assistant(self, text: str) -> None:
        db = SessionLocal()
        try:
            db.add(ChatMessage(session_id=self.session_id, role="assistant", content=text))
            db.commit()
        finally:
            db.close()

    def _write_latencies(self, pairs: List[tuple]) -> None:
        db = SessionLocal()
        try:
            for row_id, ms in pairs:
                row = db.get(MessageAnalysis, row_id)
                if row:
                    row.response_time_ms = ms
            db.commit()
        finally:
            db.close()

    async def user_turn(self, text: str) -> Dict:
        result = await asyncio.to_thread(self._record_user, text)
        self.last_sentiment = result["analysis"].sentiment_score
        a = result["analysis"]
        logger.info(f"user: {text!r} -> intent={a.intent} sentiment={a.sentiment_score:+.2f} entities={a.entities}"
                    + (f" ESCALATED ticket #{result['ticket']['ticket_id']}" if result["ticket"] else ""))
        async with self._lock:
            self._rows.append(result["row_id"])
        await self._flush()
        return result

    async def assistant_message(self, text: str) -> None:
        if text.strip():
            await asyncio.to_thread(self._save_assistant, text)

    async def response_time(self, ms: float) -> None:
        async with self._lock:
            self._latencies.append(round(ms, 1))
        await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            n = min(len(self._rows), len(self._latencies))
            pairs = list(zip(self._rows[:n], self._latencies[:n]))
            self._rows, self._latencies = self._rows[n:], self._latencies[n:]
        if pairs:
            await asyncio.to_thread(self._write_latencies, pairs)


class SupportAgent(Agent):
    def __init__(self, call: CallLogger, customer_name: str):
        super().__init__(instructions=SUPPORT_PROMPT + VOICE_STYLE + f"\nThe customer's name is {customer_name}.")
        self.call = call

    async def _tool(self, func: Callable, **kwargs) -> Dict[str, Any]:
        def run():
            db = SessionLocal()
            try:
                ctx = tools.ToolContext(db=db, user_id=self.call.user_id, session_id=self.call.session_id,
                                        channel="voice", sentiment_score=self.call.last_sentiment)
                result = func(ctx, **kwargs)
                db.commit()
                return result
            finally:
                db.close()
        result = await asyncio.to_thread(run)
        logger.info(f"tool {func.__name__}({kwargs}) -> {str(result)[:200]}")
        return result

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: LKChatMessage) -> None:
        """Analyze each user turn; if it escalates in time, tell the LLM before it replies."""
        text = new_message.text_content or ""
        if not text.strip():
            return
        task = asyncio.create_task(self.call.user_turn(text))
        try:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=ANALYSIS_WAIT_SECONDS)
        except asyncio.TimeoutError:
            # Too slow for this reply: keep logging in the background and, if it escalates,
            # add the note to the agent's context so the next reply mentions the ticket
            task.add_done_callback(lambda t: asyncio.create_task(self._late_escalation_note(t)))
            return
        except Exception as e:
            logger.warning(f"Turn analysis failed: {e}")
            return
        if result["ticket"]:
            turn_ctx.add_message(role="system", content=analysis_note(result["analysis"], result["ticket"]))

    async def _late_escalation_note(self, task: asyncio.Task) -> None:
        if task.cancelled() or task.exception() or not task.result()["ticket"]:
            return
        result = task.result()
        chat_ctx = self.chat_ctx.copy()
        chat_ctx.add_message(role="system", content=analysis_note(result["analysis"], result["ticket"]))
        await self.update_chat_ctx(chat_ctx)

    @function_tool
    async def get_order_status(self, context: RunContext, order_number: str) -> Dict[str, Any]:
        """Get status, tracking and delivery details of one of the customer's orders.

        Args:
            order_number: The order number, e.g. ORD-10023. Spoken digits like "one zero zero two three" mean 10023.
        """
        return await self._tool(tools.get_order_status, order_number=order_number)

    @function_tool
    async def list_recent_orders(self, context: RunContext) -> Dict[str, Any]:
        """List the customer's recent orders. Use when they don't know the order number."""
        return await self._tool(tools.list_recent_orders)

    @function_tool
    async def search_products(self, context: RunContext, query: str) -> Dict[str, Any]:
        """Search the product catalog for price, stock and details.

        Args:
            query: Product name, category or feature to search for
        """
        return await self._tool(tools.search_products, query=query)

    @function_tool
    async def create_return_request(self, context: RunContext, order_number: str, reason: str,
                                    product: Optional[str] = None) -> Dict[str, Any]:
        """Create a return/refund request for an item from a delivered order. Confirm item and reason first.

        Args:
            order_number: The order number, e.g. ORD-10021
            reason: Why the customer is returning the item
            product: Name of the item to return, if the order has several items
        """
        return await self._tool(tools.create_return_request, order_number=order_number, reason=reason, product=product)

    @function_tool
    async def cancel_order(self, context: RunContext, order_number: str) -> Dict[str, Any]:
        """Cancel an order that has not shipped yet. Confirm with the customer first.

        Args:
            order_number: The order number, e.g. ORD-10024
        """
        return await self._tool(tools.cancel_order, order_number=order_number)

    @function_tool
    async def search_faq(self, context: RunContext, question: str) -> Dict[str, Any]:
        """Search store policies and FAQs: shipping, returns, refunds, payments, warranty, account.

        Args:
            question: The customer's question
        """
        return await self._tool(tools.search_faq, question=question)

    @function_tool
    async def escalate_to_human(self, context: RunContext, reason: str, summary: str = "") -> Dict[str, Any]:
        """Hand over to a human agent when the customer asks for one or the issue can't be solved.

        Args:
            reason: Why the conversation needs a human
            summary: Short summary of the issue for the human agent
        """
        return await self._tool(tools.escalate_to_human, reason=reason, summary=summary)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer(setup_fnc=prewarm)


async def _resolve_customer(ctx: JobContext) -> Dict:
    """User and session IDs come from the dispatch metadata set by POST /voice/livekit-token."""
    meta: Dict = {}
    if ctx.job.metadata:
        meta = json.loads(ctx.job.metadata)
    if "user_id" not in meta:
        participant = await ctx.wait_for_participant()
        meta = json.loads(participant.metadata or "{}")
    if "user_id" not in meta:
        raise RuntimeError("Room has no customer metadata; join through POST /voice/livekit-token")
    return meta


@server.rtc_session(agent_name=settings.LIVEKIT_AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    meta = await _resolve_customer(ctx)

    def load_customer():
        db = SessionLocal()
        try:
            user = db.get(User, meta["user_id"])
            return user.name if user else "there"
        finally:
            db.close()
    customer_name = await asyncio.to_thread(load_customer)
    call = CallLogger(user_id=int(meta["user_id"]), session_id=int(meta["session_id"]))
    logger.info(f"Call started: room={ctx.room.name} user={call.user_id} session={call.session_id}")

    session = AgentSession(
        stt=openai.STT(model="gpt-4o-mini-transcribe", language="en",
                       prompt="E-commerce support call. Order numbers look like ORD-10023."),
        llm=openai.LLM(model=settings.SUPPORT_MODEL, temperature=0.3),
        tts=openai.TTS(model="gpt-4o-mini-tts", voice="alloy",
                       instructions="Speak like a friendly, calm customer support agent."),
        vad=ctx.proc.userdata["vad"],
        max_tool_steps=4,
    )

    user_stopped_at: Dict[str, Optional[float]] = {"t": None}
    background: set = set()

    def spawn(coro) -> None:
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)

    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        metrics.log_metrics(ev.metrics)  # per-turn STT / LLM TTFT / TTS TTFB / end-of-utterance delay

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        if ev.old_state == "speaking" and ev.new_state == "listening":
            user_stopped_at["t"] = time.perf_counter()

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        # Response time = end of the customer's speech -> agent starts talking
        if ev.new_state == "speaking" and user_stopped_at["t"] is not None:
            spawn(call.response_time((time.perf_counter() - user_stopped_at["t"]) * 1000))
            user_stopped_at["t"] = None

    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = ev.item
        if getattr(item, "role", None) == "assistant" and getattr(item, "text_content", None):
            spawn(call.assistant_message(item.text_content))

    async def _on_shutdown() -> None:
        if background:
            await asyncio.gather(*background, return_exceptions=True)
        logger.info(f"Call ended: session={call.session_id}")
    ctx.add_shutdown_callback(_on_shutdown)

    await session.start(room=ctx.room, agent=SupportAgent(call, customer_name))
    await session.generate_reply(
        instructions=f"Greet {customer_name.split()[0]} warmly, say you are the ShopEase support assistant, "
                     "and ask how you can help today. One short sentence.")


if __name__ == "__main__":
    ensure_schema()
    cli.run_app(server)
