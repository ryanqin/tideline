"""Agent capability bench for Tideline.

Measures whether a model — wrapped in our agent harness with our system
message and tool registry — actually does the right thing on canonical
Tideline tasks: calling the correct tool, with parseable args, in a
reasonable number of turns.

This is orthogonal to the translation accuracy bench (which scores
output text quality). The agent bench scores agent-loop behavior: tool
selection, format adherence, turn efficiency.

Run via:

    python -m tideline.bench --suite agent                  # mock smoke
    python -m tideline.bench --suite agent --runtime llama_cpp
"""
