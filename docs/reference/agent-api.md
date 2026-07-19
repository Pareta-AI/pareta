# Agent API (`/agent/v1`) — OpenClaw and agent runtimes

The wire reference for Pareta's agent surface: an OpenAI-compatible chat
completions endpoint built for multi-turn tool loops. If you want the
narrative version — what the lane does per turn and why — read
[Connect OpenClaw to Pareta](../guide/agent-openclaw.md) first; this page is
the contract.

Base URL: `https://api.pareta.ai/agent/v1`. Authentication is a Bearer
`pareta_sk_…` key on every request, same as `/v1`.

## `GET /agent/v1/models`

Returns the one model the surface serves. Agent runtimes that size their
context accounting from `/models` (OpenClaw, Hermes) read the vLLM-style
extension fields.

```json
{
  "object": "list",
  "data": [{
    "id": "auto",
    "object": "model",
    "owned_by": "pareta",
    "created": 1784130000,
    "max_model_len": 131072,
    "context_window": 131072
  }]
}
```

## `POST /agent/v1/chat/completions`

One conversation turn. The transcript and tool schemas pass through to a
turn-routed fleet member verbatim; the response comes back in OpenAI shape
with `model: "auto"`.

### Request body

| Field | Behavior |
| --- | --- |
| `model` | `"auto"` or omitted. Any other value → `400`. |
| `messages` | Full transcript — `system`, `user`, `assistant` (including prior `tool_calls`), and `tool` results all pass through. Nothing is dropped or rewritten. |
| `tools`, `tool_choice`, `parallel_tool_calls` | OpenAI function-calling shape, passed through; `tool_calls` come back in the same shape. |
| `stream`, `stream_options` | SSE streaming (below). `include_usage` is forced on — the final chunk always carries `usage`. |
| `temperature`, `top_p`, `max_tokens`, `max_completion_tokens`, `stop`, `seed`, `presence_penalty`, `frequency_penalty`, `logprobs`, `top_logprobs`, `response_format` | Forwarded verbatim — the agent owns its sampling. `max_tokens` defaults to 8192 when omitted. |
| `n` | Only `1` (or omitted). `n > 1` → `400`. |
| anything else | Ignored, never a `400` — runtimes that attach vendor `extra_body` fields work unmodified. |

Context window: **131,072 tokens** per turn.

### Request headers

| Header | Behavior |
| --- | --- |
| `Authorization` | `Bearer pareta_sk_…` — required. |
| `Idempotency-Key` | Optional. A retried turn with the same key bills once. |
| `X-Pareta-Session` | Optional explicit conversation id. Pareta pins a conversation's route so consecutive turns don't re-derive routing (and an escalation can stick); without this header the pin key is derived from your org + system prompt + tool-schema names — the stable prefix agent runtimes re-send every turn. Pins expire after ~30 minutes idle; a modality change (an image turn in a text conversation) re-routes. |

### Response

A standard OpenAI chat completion. `model` is always `"auto"` — real model
ids never appear anywhere in the response. `usage` carries prompt and
completion tokens.

| Header | Meaning |
| --- | --- |
| `X-Pareta-Billed` | The turn's debit in micro-USD (non-streamed responses). A turn bills once no matter how it was routed or escalated; a failed turn bills nothing. |

### Streaming

Set `"stream": true`. The response is `text/event-stream` with OpenAI chunk
deltas — `tool_calls` stream in OpenAI shape — followed by a final chunk
carrying `usage`, then `data: [DONE]`.

### Routing and escalation

Every turn is routed by shape behind the single `auto` string: general
reasoning, coding, or vision. A turn that comes back low-confidence is re-run
on a frontier model **with your tools intact** and that answer is returned;
conversations that escalate repeatedly pin to the frontier route. None of
this changes the wire shape or the one-debit-per-turn billing.

### Errors

| Status | Meaning |
| --- | --- |
| `400` | Malformed JSON body, `model` other than `"auto"`, or `n > 1`. |
| `401` | Missing or invalid API key. |
| `402` | Insufficient balance. |
| `404` | The agent surface is not enabled. |
| `502` | The turn could not be completed (never a raw 500). |
| `503` | Temporarily unavailable — retry after the `Retry-After` header (30s). |

## OpenClaw provider block

OpenClaw configures models through OpenAI-compatible providers in
`~/.openclaw/openclaw.json`. This is a working provider entry (field names
can drift across OpenClaw versions — the three values that matter are the
base URL, the key, and `model: auto`):

```json
{
  "models": {
    "providers": {
      "pareta": {
        "baseUrl": "https://api.pareta.ai/agent/v1",
        "apiKey": "pareta_sk_…",
        "api": "openai-completions",
        "models": [{
          "id": "auto",
          "name": "Pareta Auto",
          "input": ["text", "image"],
          "contextWindow": 131072,
          "maxTokens": 8192
        }]
      }
    }
  }
}
```

Then point any agent role at it — as the primary model, keep a local
fallback if you like:

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "pareta/auto",
        "fallbacks": ["ollama/gpt-oss:120b"]
      }
    }
  }
}
```

Restart the OpenClaw gateway and every turn — chat, tool calls, images —
routes through Pareta. Because `auto` routes per turn, this one provider
entry covers coding, general reasoning, and vision; there is nothing else to
wire up.
