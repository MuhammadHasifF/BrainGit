"""Top-level message router.

Picks an agent based on the message's topic. Push-only topics (daily
routine, evening recap) ignore incoming user messages — those are
written by the scheduler.

Agents are constructed lazily and cached for the process lifetime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brainbot.agents.base import BaseAgent
from brainbot.telegram.topics import PUSH_ONLY, TopicName
from brainbot.utils.logging import get_logger

if TYPE_CHECKING:
    from brainbot.telegram.webhook import IncomingMessage


log = get_logger(__name__)

_agents: dict[TopicName, BaseAgent] = {}


def _agent_for(topic: TopicName) -> BaseAgent:
    if topic in _agents:
        return _agents[topic]

    # Local imports to avoid circular dependencies.
    from brainbot.agents.brain_agent import BrainAgent
    from brainbot.agents.calendar_agent import CalendarAgent
    from brainbot.agents.email_agent import EmailAgent
    from brainbot.agents.general_agent import GeneralAgent
    from brainbot.agents.todo_agent import TodoAgent

    table: dict[TopicName, type[BaseAgent]] = {
        TopicName.EMAILS: EmailAgent,
        TopicName.CALENDAR: CalendarAgent,
        TopicName.TODOS: TodoAgent,
        TopicName.SECOND_BRAIN: BrainAgent,
        TopicName.QUICK_NOTES: BrainAgent,  # quick notes auto-save into the brain
        TopicName.GENERAL: GeneralAgent,
    }
    cls = table.get(topic, GeneralAgent)
    _agents[topic] = cls()
    return _agents[topic]


async def route(msg: "IncomingMessage") -> None:
    """Dispatch a parsed message to the right agent."""
    if msg.topic in PUSH_ONLY:
        log.info("ignored_push_only_topic", topic=msg.topic.value)
        return

    agent = _agent_for(msg.topic)
    await agent.handle(msg)
