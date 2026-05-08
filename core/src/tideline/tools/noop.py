from typing import Any

from tideline.tools.base import Tool


class NoopTool(Tool):
    """A do-nothing tool. Used since Step 2 to drive the turn loop end-to-end."""

    name = "noop"
    capability = "noop"
    schema: dict[str, str] = {}
    description = "A no-op tool that does nothing and returns 'noop done'."

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        return "noop done"
