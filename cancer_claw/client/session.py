"""跑一轮对话并流式产出事件。"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from cancer_claw.agent.engine.agent import Agent
from cancer_claw.services.identity.deps import LOCAL_SUPERUSER


async def resolve_session(
    agent: Agent,
    *,
    session_id: str | None,
    force_new: bool,
    pending_user_message: str,
) -> dict[str, Any]:
    from cancer_claw.interfaces.routes.chat import _resolve_session_for_chat

    return await _resolve_session_for_chat(
        agent,
        session_id,
        force_new=force_new,
        pending_user_message=pending_user_message,
    )


async def run_turn(
    agent: Agent,
    message: str,
    *,
    session_id: str | None = None,
    force_new: bool = False,
    verbose: bool = False,
    current_user: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    import contextlib
    import io

    carrier = agent.clone_for_session()
    carrier._current_user = dict(current_user or getattr(agent, "_current_user", None) or LOCAL_SUPERUSER)
    await carrier.initialize()
    await carrier.prepare()

    started = await resolve_session(
        carrier,
        session_id=session_id,
        force_new=force_new,
        pending_user_message=message,
    )
    yield started

    quiet = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(io.StringIO())
    with quiet:
        async for ev in carrier.chat_stream(message):
            yield ev
