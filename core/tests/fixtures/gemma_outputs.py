"""Gemma 4 function-calling fixtures aligned with official documentation.

Sources (pulled 2026-05-08, official doc last updated 2026-04-08 UTC):
- https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4
- https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4

TOKEN REFERENCE (asymmetric pipe placement on open/close):
    Turn:           <|turn>ROLE ... <turn|>     (ROLE: system | user | model | tool)
    Tool def:       <|tool> ... <tool|>
    Tool call:      <|tool_call> ... <tool_call|>
    Tool response:  <|tool_response> ... <tool_response|>
    String:         <|"|>                       (symmetric, used as both opener/closer)
    Multimodal:     <|image|>  <|audio|>
    Thinking:       <|think|>                   (placed in system instruction)
    Channel:        <|channel> ... <channel|>   (channel name "thought" for reasoning)

INNER MINI-GRAMMAR (NOT JSON):
    call:FUNC_NAME{key:value,key:<|"|>string value<|"|>,...}
    declaration:FUNC_NAME{key:<|"|>type<|"|>,...}
    response:FUNC_NAME{key:value,key:<|"|>string value<|"|>,...}

    - numbers and bools are written naked (no quotes)
    - strings ALWAYS wrapped in <|"|>...<|"|> token pair
    - keys are bare identifiers (no quotes)
    - braces use literal { and } (no escaping inside string bodies needed; the
      <|"|> tokens unambiguously delimit string literals)

EARLY STOP: <|tool_response> acts as an additional stop sequence for the
inference engine — the model halts naturally after emitting <tool_call|> on
the developer-turn boundary, no manual buffer-watching required.
"""

# --- Tool calls -------------------------------------------------------------

# Smallest possible: a no-arg tool call. This is what Mock will emit in Step 2
# to drive the parser through its first happy path.
NOOP_CALL = "<|tool_call>call:noop{}<tool_call|>"

# Single tool call with a single string argument.
WEATHER_CALL = (
    '<|tool_call>call:get_current_weather{location:<|"|>Tokyo, JP<|"|>}<tool_call|>'
)

# Mixed argument types — string, string, number — exercising the grammar.
TRANSLATE_CALL = (
    '<|tool_call>call:translate{'
    'text:<|"|>こんにちは<|"|>,'
    'target_lang:<|"|>zh<|"|>,'
    'temperature:0.3'
    '}<tool_call|>'
)

# Natural-language preamble followed by a tool call. The parser must split
# these cleanly: the NL part goes to delivery; the tool call goes to L2.
NL_PLUS_TOOL = (
    "I'll check the weather for you.\n"
    '<|tool_call>call:get_current_weather{location:<|"|>Tokyo, JP<|"|>}<tool_call|>'
)


# --- Tool responses (what the developer feeds back) ------------------------

WEATHER_RESPONSE = (
    '<|tool_response>response:get_current_weather{'
    'temperature:15,weather:<|"|>sunny<|"|>}<tool_response|>'
)


# --- Tool declarations (sent in the system turn / prompt header) -----------

# How a single tool's schema appears in the prompt. Note the same
# mini-grammar — types are written as quoted strings via <|"|>.
WEATHER_DECLARATION = (
    '<|tool>declaration:get_current_weather{'
    'location:<|"|>string<|"|>}<tool|>'
)


# --- Full multi-turn message reconstruction --------------------------------

# Plausible end-to-end exchange. Marked PROVISIONAL until verified against
# real Gemma 4 GGUF output — exact role label for tool injection and exact
# whitespace handling are inferred from the docs but not yet confirmed.
FULL_TURN_PROVISIONAL = """<|turn>system
You are a helpful assistant.
<|tool>declaration:get_current_weather{location:<|"|>string<|"|>}<tool|>
<turn|>
<|turn>user
What's the weather in Tokyo?<turn|>
<|turn>model
<|tool_call>call:get_current_weather{location:<|"|>Tokyo, JP<|"|>}<tool_call|><turn|>
<|turn>tool
<|tool_response>response:get_current_weather{temperature:15,weather:<|"|>sunny<|"|>}<tool_response|><turn|>
<|turn>model
The weather in Tokyo is sunny with a temperature of 15°C.<turn|>"""


# --- TODOs to resolve once we have a real Gemma 4 GGUF in hand -------------
#
# 1. Verify the role label for tool-result injection. We assume "tool" but
#    it could be "user" with a tool_response wrapper. Capture from a real run.
# 2. Capture an actual multi-tool-call output (single model turn emitting 2+
#    tool calls). Docs only show single-call examples.
# 3. Capture a thinking-mode output to verify <|think|> activation flow and
#    confirm <|channel>...<channel|> wrapping with channel name "thought".
# 4. Verify whether llama-cpp-python honors GGUF-embedded chat template for
#    Gemma 4 tool serialization, OR whether we need to manually construct the
#    <|tool>declaration:...{...}<tool|> blocks before passing to the model.
# 5. Verify that the special tokens are recognized as single tokens in the
#    GGUF tokenizer (not split into multiple subwords) — critical for stop
#    sequence detection and token counting.
