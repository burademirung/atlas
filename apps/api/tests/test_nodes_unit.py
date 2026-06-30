from langchain_core.language_models.fake_chat_models import FakeListChatModel

from atlas_api.agents import nodes
from atlas_api.agents.state import ResearchState


def test_as_text_handles_str_list_and_other() -> None:
    assert nodes._as_text("plain") == "plain"
    assert nodes._as_text([{"text": "a"}, "b", {"no": "text"}]) == "ab"
    assert nodes._as_text(123) == "123"


async def test_verify_node_no_sources_returns_empty() -> None:
    state: ResearchState = {"question": "q", "sources": []}
    out = await nodes.verify_node(state, model=FakeListChatModel(responses=["1"]))
    assert out == {"claims": []}
