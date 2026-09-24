from haystack.tools import ComponentTool
from haystack.utils import Secret
from haystack_integrations.components.websearch.serperdev import SerperDevWebSearch


def build_web_search_tool(top_k: int = 4) -> ComponentTool:
    return ComponentTool(
        component=SerperDevWebSearch(
            api_key=Secret.from_env_var("SERPERDEV_API_KEY"),
            top_k=top_k,
        ),
        name="web_search",
        description="Search the web for current information on any topic",
    )
