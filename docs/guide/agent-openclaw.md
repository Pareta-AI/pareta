# Connect OpenClaw to Pareta

Pareta's Agent Auto endpoint is OpenAI-compatible on the wire. Point OpenClaw — or any agent runtime that speaks the OpenAI chat completions API — at it, set the model to `auto`, and Pareta handles the rest: it routes each turn to the right model, escalates to a frontier model on the turns that need it, and bills one debit per turn.

You don't pick a model, a GPU, or a provider. `auto` is the whole product.

## The three values

Point your runtime's OpenAI-compatible provider at:

| Setting | Value |
| --- | --- |
| Base URL | `https://api.pareta.ai/agent/v1` |
| API key | your `pareta_sk_…` key (mint one in the dashboard) |
| Model | `auto` |

That's the entire integration. Everything else — your system prompt, the full message history, your tool schemas — flows through unchanged.

## What Pareta does per turn

- **One endpoint, one model string.** `model` is the literal string `"auto"`. Pareta reads the shape of each turn and routes it to the right fleet member — general reasoning, coding, or vision — behind that one string. Real model ids never reach you.
- **Full transcript and tools pass through.** Your system prompt, the whole conversation, and your OpenAI-shape `tools` go straight to the chosen model; `tool_calls` come back in the same shape. Nothing is dropped, summarized, or rewritten — the model's output *is* the answer.
- **A frontier floor.** When a turn comes back low-confidence, Pareta re-runs *that turn* on a frontier model (with your tools intact) and returns it as the answer. You get open-weights price on the turns the open fleet handles well, and frontier quality only on the turns that earn it.
- **One debit per turn.** A turn bills once no matter how Pareta routed or escalated it; a turn that errors bills nothing. The `X-Pareta-Billed` response header carries the amount in micro-USD.
- **131,072-token context**, streaming, and tool calling are all supported.

## Connect with the OpenAI SDK

Any OpenAI-compatible client connects the same way OpenClaw does under the hood — set the base URL and key, then call chat completions with `model="auto"`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.pareta.ai/agent/v1",
    api_key="pareta_sk_…",
)

resp = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are a coding agent."},
        {"role": "user", "content": "List the files in the repo, then summarize the README."},
    ],
    tools=[
        {"type": "function", "function": {
            "name": "run_shell",
            "description": "Run a shell command in the workspace.",
            "parameters": {"type": "object",
                           "properties": {"cmd": {"type": "string"}},
                           "required": ["cmd"]}}},
    ],
    tool_choice="auto",
)
print(resp.choices[0].message.tool_calls)
```

Feed the tool results back as `role: "tool"` messages on the next call, exactly as you would with any OpenAI-compatible model. The conversation carries; Pareta keeps routing each turn.

## Connect with raw HTTP

```bash
curl https://api.pareta.ai/agent/v1/chat/completions \
  -H "Authorization: Bearer pareta_sk_…" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "What is the weather in Paris? Use the tool."}],
    "tools": [{"type": "function", "function": {
      "name": "get_weather",
      "parameters": {"type": "object",
                     "properties": {"city": {"type": "string"}},
                     "required": ["city"]}}}],
    "tool_choice": "auto"
  }'
```

## In OpenClaw

OpenClaw configures models through OpenAI-compatible providers. Add Pareta as a provider with the base URL and key above, and set the model to `auto` for any role you want Pareta to serve — the primary model, a subagent, or a utility model. Because `auto` routes per turn, one Pareta provider entry covers coding, general reasoning, and vision without you wiring up separate models.

For a copy-pasteable `openclaw.json` provider block and the full wire contract — request fields, session pinning, streaming shape, the billing header, and error codes — see the [Agent API reference](../reference/agent-api.md).

## How this differs from `/v1`

Pareta's `/v1` chat endpoint is the one-shot **task** lane: send a request, get one synthesized answer. `/agent/v1` is the **conversation-and-tools** lane for agent loops — it passes your transcript and tools through verbatim, turn after turn, and pins a conversation to a consistent route. Same API key, same one-debit-per-turn billing, same `auto` model string. Use `/agent/v1` when a runtime like OpenClaw is driving a multi-turn tool loop.
