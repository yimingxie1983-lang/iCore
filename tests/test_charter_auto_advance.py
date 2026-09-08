from cancer_claw.agent.engine.agent import Agent
from cancer_claw.config import settings


class _FakeResult:
    def __init__(self, data: dict):
        self.success = True
        self.data = data


def test_charter_auto_advance_enabled_by_default():
    assert settings.charter.auto_advance_stages is True
    assert settings.charter.auto_advance_max_stages >= 1


def test_track_and_should_auto_advance():
    old = settings.charter.auto_advance_stages
    settings.charter.auto_advance_stages = True
    try:
        agent = Agent.__new__(Agent)
        agent.id = "test"
        agent._charter_stage_just_advanced = False
        agent._charter_stage_done_index = 0
        agent._charter_stage_done_name = ""
        agent._charter_stage_next_index = 0
        agent._charter_stage_next_name = ""
        agent._charter_all_done = False
        agent._auto_advance_count = 0

        assert not agent._should_auto_advance_after_completion()

        agent._track_charter_advance_from_tool_result(
            "task_charter",
            _FakeResult(
                {
                    "stage_done_index": 1,
                    "stage_done": "数据准备",
                    "stage_next_index": 2,
                    "stage_next_name": "训练",
                    "all_done": False,
                }
            ),
        )
        assert agent._charter_stage_just_advanced
        assert agent._charter_stage_next_index == 2
        assert agent._should_auto_advance_after_completion()

        msg = agent._build_auto_advance_continue_message()
        assert "阶段 1「数据准备」" in msg
        assert "阶段 2「训练」" in msg
        assert "ask_user" in msg

        agent._track_charter_advance_from_tool_result(
            "task_charter",
            _FakeResult(
                {
                    "stage_done_index": 2,
                    "stage_done": "训练",
                    "stage_next_index": 0,
                    "stage_next_name": "",
                    "all_done": True,
                }
            ),
        )
        assert agent._charter_all_done
        assert not agent._should_auto_advance_after_completion()
    finally:
        settings.charter.auto_advance_stages = old


def test_auto_advance_respects_cap():
    old = (
        settings.charter.auto_advance_stages,
        settings.charter.auto_advance_max_stages,
    )
    settings.charter.auto_advance_stages = True
    settings.charter.auto_advance_max_stages = 1
    try:
        agent = Agent.__new__(Agent)
        agent.id = "test"
        agent._charter_stage_just_advanced = True
        agent._charter_stage_done_index = 1
        agent._charter_stage_done_name = "A"
        agent._charter_stage_next_index = 2
        agent._charter_stage_next_name = "B"
        agent._charter_all_done = False
        agent._auto_advance_count = 1
        assert not agent._should_auto_advance_after_completion()
    finally:
        settings.charter.auto_advance_stages = old[0]
        settings.charter.auto_advance_max_stages = old[1]
