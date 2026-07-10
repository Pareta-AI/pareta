# Medical coding (ICD-10)

Turn a clinical discharge summary into ICD-10-CM codes with one chat call. The
summary goes to `model="auto"` as plain text; the prompt pins the output to a
strict JSON array of `{"code", "description"}` objects; you parse the array and
have structured codes.

Medical coding is a text-in, structured-text-out job, so it rides the standard
OpenAI-compatible chat surface — the one interface for every text workload.
`"auto"` is the only model id; the completion is metered against your org
balance, one debit per request regardless of internal routing.

## Setup

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();   // reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

See [installation](../guide/installation.md) for keys and environment.

## Code a discharge summary

The whole contract lives in the prompt: demand a bare JSON array of
`{"code", "description"}` objects and nothing else. Set `temperature=0` —
coding is a deterministic mapping from documentation to codes, and you want the
same summary to produce the same codes every run. `max_tokens` just needs
headroom for the array; 512 covers a typical inpatient stay.

**Python**

```python
PROMPT = (
    "Assign ICD-10-CM codes for the discharge summary below. Respond with "
    'ONLY a JSON array of {"code", "description"} objects — no prose, '
    "no markdown.\n\n" + DISCHARGE_SUMMARY
)

resp = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": PROMPT}],
    temperature=0,
    max_tokens=512,
)
raw = resp.choices[0].message.content or ""
```

**TypeScript**

```typescript
const PROMPT =
  "Assign ICD-10-CM codes for the discharge summary below. Respond with " +
  'ONLY a JSON array of {"code", "description"} objects — no prose, ' +
  "no markdown.\n\n" + DISCHARGE_SUMMARY;

const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: PROMPT }],
  temperature: 0,
  max_tokens: 512,
});
const raw = resp.choices[0].message.content ?? "";
```

Full runnable example: [python/icd-coding/icd_coding.py](https://github.com/Pareta-AI/examples/blob/main/python/icd-coding/icd_coding.py) · [typescript/icd-coding/icd-coding.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/icd-coding/icd-coding.ts)

## Parse the JSON robustly

The prompt demands bare JSON, but the single most common drift is a response
wrapped in a ` ```json ` fence. Strip a leading fence before parsing, then
validate that the payload really is an array — anything else should fail loudly
rather than flow downstream as half-parsed codes.

**Python**

```python
import json

def parse_codes(text: str) -> list[dict]:
    t = text.strip()
    if t.startswith("```"):                      # ```json fence — the common drift
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    codes = json.loads(t)
    if not isinstance(codes, list):
        raise ValueError(f"expected a JSON array, got {type(codes).__name__}")
    return codes

for c in parse_codes(raw):
    print(f"{c.get('code', '?'):10} {c.get('description', '')}")
```

**TypeScript**

```typescript
function parseCodes(text: string): Array<{ code?: string; description?: string }> {
  let t = text.trim();
  if (t.startsWith("```")) {                     // ```json fence — the common drift
    t = t.includes("\n") ? t.slice(t.indexOf("\n") + 1) : "";
    const close = t.lastIndexOf("```");
    if (close !== -1) t = t.slice(0, close);
  }
  const codes = JSON.parse(t);
  if (!Array.isArray(codes)) throw new Error(`expected a JSON array, got ${typeof codes}`);
  return codes;
}

for (const c of parseCodes(raw)) {
  console.log(`${(c.code ?? "?").padEnd(10)} ${c.description ?? ""}`);
}
```

Full runnable example: [python/icd-coding/icd_coding.py](https://github.com/Pareta-AI/examples/blob/main/python/icd-coding/icd_coding.py) · [typescript/icd-coding/icd-coding.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/icd-coding/icd-coding.ts)

## Nothing to pick

There is no coding model in this example because there is nothing to name:
`"auto"` recognizes medical-coding traffic and routes it internally to the
right serving path, per request, server-side. Your code stays a plain chat call
with a JSON contract — the routing is Pareta's job, not a parameter.

Full runnable example: [python/icd-coding/icd_coding.py](https://github.com/Pareta-AI/examples/blob/main/python/icd-coding/icd_coding.py) · [typescript/icd-coding/icd-coding.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/icd-coding/icd-coding.ts)

## See also

- [Inference (OpenAI-compatible)](../guide/inference.md) — the full chat surface, streaming, extra params.
- [Chat reference](../reference/chat.md) — `chat.completions.create` request and response shapes.
- [Streaming chat](./streaming-chat.md) — token-by-token output for long generations.
- [Evaluating on your data](./evaluate-on-your-data.md) — benchmark `"auto"` on your own summaries, metered like inference.
