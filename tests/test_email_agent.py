import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.agents.email_agent import EmailAgent
from app.ai.base import AIProvider
from app.ai.schemas import AgentStep, ToolCall


class FakeAIProvider(AIProvider):
    def __init__(self, steps: list[AgentStep]):
        self.steps = steps
        self.call_count = 0

    def complete(self, *args, **kwargs):
        raise NotImplementedError()

    def complete_structured(self, system_prompt, user_prompt, schema, **kwargs):
        if self.call_count >= len(self.steps):
            raise Exception("FakeAIProvider ran out of steps")
        step = self.steps[self.call_count]
        self.call_count += 1
        return step


def test_agent_happy_path():
    steps = [
        AgentStep(
            thought="I need to search for emails.",
            tool_call=ToolCall(tool_name="search_emails", arguments={"query": "test"}),
        ),
        AgentStep(
            thought="I have the results, I can answer now.",
            final_answer="Found some emails.",
            sources=["msg1"],
        ),
    ]
    provider = FakeAIProvider(steps)
    session = MagicMock()
    user_id = uuid.uuid4()
    agent = EmailAgent(provider, session, user_id)

    with patch.object(agent, "_execute_tool") as mock_exec:
        mock_exec.return_value = [{"message_id": "msg1", "subject": "Test Email"}]
        answer = agent.answer("Find test emails")

    assert answer.text == "Found some emails."
    assert answer.source_message_ids == ["msg1"]
    assert provider.call_count == 2
    mock_exec.assert_called_once_with("search_emails", {"query": "test"})


def test_agent_max_hops():
    # Make it return tool calls endlessly
    steps = [
        AgentStep(
            thought="Searching...",
            tool_call=ToolCall(tool_name="search_emails", arguments={"query": "test"}),
        )
    ] * EmailAgent.MAX_TOOL_HOPS
    
    provider = FakeAIProvider(steps)
    session = MagicMock()
    user_id = uuid.uuid4()
    agent = EmailAgent(provider, session, user_id)

    with patch.object(agent, "_execute_tool") as mock_exec:
        mock_exec.return_value = []
        answer = agent.answer("Find test emails")

    assert answer.text == "I couldn't find a reliable answer in your emails."
    assert provider.call_count == EmailAgent.MAX_TOOL_HOPS


def test_agent_unknown_tool():
    steps = [
        AgentStep(
            thought="Calling fake tool",
            tool_call=ToolCall(tool_name="fake_tool", arguments={}),
        ),
        AgentStep(
            thought="It failed, so I will answer fallback",
            final_answer="I tried fake tool and failed.",
        )
    ]
    provider = FakeAIProvider(steps)
    session = MagicMock()
    user_id = uuid.uuid4()
    agent = EmailAgent(provider, session, user_id)

    answer = agent.answer("Do something")
    
    assert answer.text == "I tried fake tool and failed."
    assert provider.call_count == 2
