

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable

import structlog

_sm_logger = structlog.get_logger()

class AgentState(str, Enum):

    CREATED = "created"
    INITIALIZED = "initialized"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.CREATED:     {AgentState.INITIALIZED},
    AgentState.INITIALIZED: {AgentState.READY, AgentState.FAILED},
    AgentState.READY:       {AgentState.RUNNING, AgentState.FAILED},
    AgentState.RUNNING:     {AgentState.PAUSED, AgentState.COMPLETED, AgentState.FAILED},
    AgentState.PAUSED:      {AgentState.RUNNING, AgentState.COMPLETED, AgentState.FAILED},
    AgentState.COMPLETED:   set(),
    AgentState.FAILED:      {AgentState.READY},
}

@dataclass
class StateTransition:

    from_state: AgentState
    to_state: AgentState
    timestamp: float
    reason: str = ""

TransitionCallback = Callable[[AgentState, AgentState, str], Awaitable[None]]

class StateMachine:


    def __init__(self, initial_state: AgentState = AgentState.CREATED):
        self._state = initial_state
        self._history: list[StateTransition] = []
        self._callbacks: list[TransitionCallback] = []

    @property
    def state(self) -> AgentState:

        return self._state

    @property
    def history(self) -> list[StateTransition]:

        return list(self._history)

    @property
    def is_terminal(self) -> bool:

        return self._state in (AgentState.COMPLETED,)

    @property
    def is_active(self) -> bool:

        return self._state in (AgentState.RUNNING, AgentState.PAUSED)

    def on_transition(self, callback: TransitionCallback):

        self._callbacks.append(callback)

    def can_transition_to(self, target: AgentState) -> bool:

        return target in VALID_TRANSITIONS.get(self._state, set())

    async def transition_to(self, target: AgentState, reason: str = ""):


        if self._state == target:
            _sm_logger.debug(
                "【状态机】◇ 状态已是目标，跳过 transition（no-op）",
                当前状态=self._state.value,
                目标状态=target.value,
                原因=reason,
            )
            return

        if not self.can_transition_to(target):
            valid = VALID_TRANSITIONS.get(self._state, set())
            _sm_logger.error(
                "【状态机】❌ 非法状态转换，操作被拒绝",
                当前状态=self._state.value,
                目标状态=target.value,
                允许的目标=[s.value for s in valid],
                拒绝原因=reason,
            )
            raise InvalidTransitionError(
                f"非法状态转换: {self._state.value} → {target.value}，"
                f"允许的目标: {[s.value for s in valid]}"
            )

        from_state = self._state

        _sm_logger.info(
            f"【状态机】✅ 状态转换: {from_state.value} → {target.value}",
            原因=reason,
            历史转换次数=len(self._history),
        )


        transition = StateTransition(
            from_state=from_state,
            to_state=target,
            timestamp=time.time(),
            reason=reason,
        )
        self._history.append(transition)


        self._state = target


        for cb in self._callbacks:
            await cb(from_state, target, reason)

    async def reset(self, reason: str = "手动重置"):

        from_state = self._state
        _sm_logger.warning(
            f"【状态机】⚠️ 强制 RESET: {from_state.value} → created（绕过合法性校验）",
            原因=reason,
            历史转换次数=len(self._history),
        )
        transition = StateTransition(
            from_state=from_state,
            to_state=AgentState.CREATED,
            timestamp=time.time(),
            reason=reason,
        )
        self._history.append(transition)
        self._state = AgentState.CREATED

class InvalidTransitionError(Exception):

    pass
