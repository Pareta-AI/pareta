# Text classification

Turn `model="auto"` into a production text classifier: a closed label set in the system prompt, a few labeled examples, `temperature=0`, and a one-word answer your code can branch on. This page builds two of them — a banking-support intent classifier and a hate-speech moderation gate that routes violations to human review.

Classification is a chat-shaped job, so it goes to the one chat interface: `pa.chat.completions.create(model="auto", ...)`, OpenAI-compatible on the wire. There is nothing to pick and nothing to deploy — auto routes every request server-side, and each call is one metered debit against your org balance regardless of internal routing.

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

See [installation](../guide/installation.md) for getting the SDK and key in place.

## Intent classification

A closed label set is the whole contract: the system prompt names every allowed label and demands the label alone, `temperature=0` makes the answer repeatable, and a membership check after the call guarantees no stray token ever escapes the set. The few-shot pairs are the part worth your attention — on pattern tasks like intent routing, the examples in the prompt move accuracy far more than any sampling knob. When the classifier keeps confusing two intents, add a pair that shows the right answer; that is the tuning loop.

**Python**

```python
LABELS = ("card_arrival", "card_not_working", "lost_or_stolen_card", "transfer_failed",
          "balance_inquiry", "exchange_rate", "top_up_failed", "other")

SYSTEM = (
    "You classify banking-support messages into exactly one intent label: "
    + ", ".join(LABELS)
    + ". Reply with the label only — lowercase, no punctuation, no explanation. "
    "If no label fits, reply: other."
)

FEW_SHOT = (  # the lever on pattern tasks — swap pairs to steer the classifier
    ("My new card was supposed to arrive two weeks ago and it still hasn't", "card_arrival"),
    ("The shop terminal declined my card even though my account has money", "card_not_working"),
    ("I made a transfer to my landlord yesterday and it bounced back", "transfer_failed"),
)

def classify(text: str) -> str:
    messages = [{"role": "system", "content": SYSTEM}]
    for user, label in FEW_SHOT:
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": label})
    messages.append({"role": "user", "content": text})

    resp = pa.chat.completions.create(
        model="auto", messages=messages, temperature=0, max_tokens=8,
    )
    label = (resp.choices[0].message.content or "").strip().lower()
    return label if label in LABELS else "other"   # closed set, enforced
```

**TypeScript**

```typescript
const LABELS = ["card_arrival", "card_not_working", "lost_or_stolen_card", "transfer_failed",
  "balance_inquiry", "exchange_rate", "top_up_failed", "other"] as const;
type Label = (typeof LABELS)[number];

const SYSTEM =
  "You classify banking-support messages into exactly one intent label: " +
  LABELS.join(", ") +
  ". Reply with the label only — lowercase, no punctuation, no explanation. " +
  "If no label fits, reply: other.";

const FEW_SHOT: Array<[string, Label]> = [   // the lever on pattern tasks
  ["My new card was supposed to arrive two weeks ago and it still hasn't", "card_arrival"],
  ["The shop terminal declined my card even though my account has money", "card_not_working"],
  ["I made a transfer to my landlord yesterday and it bounced back", "transfer_failed"],
];

async function classify(text: string): Promise<Label> {
  const messages = [{ role: "system", content: SYSTEM }];
  for (const [user, label] of FEW_SHOT) {
    messages.push({ role: "user", content: user }, { role: "assistant", content: label });
  }
  messages.push({ role: "user", content: text });

  const resp = await pa.chat.completions.create({
    model: "auto", messages, temperature: 0, max_tokens: 8,
  });
  const label = (resp.choices[0].message.content ?? "").trim().toLowerCase();
  return (LABELS as readonly string[]).includes(label) ? (label as Label) : "other";
}
```

`max_tokens=8` caps each answer at the label itself, and one call classifies one utterance — a batch is just a loop. The fallback to `other` matters more than it looks: your downstream `switch` never sees an unexpected string, no matter what the model emits.

Full runnable example: [python/classification/intent.py](https://github.com/Pareta-AI/examples/blob/main/python/classification/intent.py) · [typescript/classification/intent.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/classification/intent.ts)

## Content moderation (hate speech)

Moderation is the same recipe with three labels — `hate`, `offensive`, `neither` — and one extra obligation: acting on the verdict. The prompt carries a one-line definition per label because the hate/offensive boundary (group-directed vs. individual-directed hostility) is exactly what untrained judgment gets wrong, and the two classes usually get different handling downstream. The strict one-word output is what makes the branch after the call safe to write.

**Python**

```python
LABELS = ("hate", "offensive", "neither")

SYSTEM = (
    "You are a content-moderation classifier. Label the text with exactly one of:\n"
    "hate — demeans or attacks a group of people based on a group identity\n"
    "offensive — insulting, hostile, or demeaning toward an individual, but not group-based\n"
    "neither — none of the above\n"
    "Reply with the label only — one lowercase word, no punctuation, no explanation."
)

def moderate(text: str) -> str:
    resp = pa.chat.completions.create(
        model="auto",
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": text}],
        temperature=0,
        max_tokens=4,
    )
    label = (resp.choices[0].message.content or "").strip().lower()
    return label if label in LABELS else "offensive"   # fail closed → human review

review_queue = []
for text in incoming_texts:
    label = moderate(text)
    if label != "neither":
        review_queue.append((label, text))   # violations go to a human
```

**TypeScript**

```typescript
const LABELS = ["hate", "offensive", "neither"] as const;
type Label = (typeof LABELS)[number];

const SYSTEM = [
  "You are a content-moderation classifier. Label the text with exactly one of:",
  "hate — demeans or attacks a group of people based on a group identity",
  "offensive — insulting, hostile, or demeaning toward an individual, but not group-based",
  "neither — none of the above",
  "Reply with the label only — one lowercase word, no punctuation, no explanation.",
].join("\n");

async function moderate(text: string): Promise<Label> {
  const resp = await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "system", content: SYSTEM }, { role: "user", content: text }],
    temperature: 0,
    max_tokens: 4,
  });
  const label = (resp.choices[0].message.content ?? "").trim().toLowerCase();
  return (LABELS as readonly string[]).includes(label) ? (label as Label) : "offensive";
}

const reviewQueue: Array<[Label, string]> = [];
for (const text of incomingTexts) {
  const label = await moderate(text);
  if (label !== "neither") reviewQueue.push([label, text]);   // violations go to a human
}
```

Note the failure direction: an answer outside the label set is coerced to `offensive`, not `neither`, so anything the classifier fumbles still reaches human eyes. Fail-open moderation is the one bug this recipe cannot afford.

Full runnable example: [python/classification/moderation.py](https://github.com/Pareta-AI/examples/blob/main/python/classification/moderation.py) · [typescript/classification/moderation.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/classification/moderation.ts)

## See also

- [Inference (OpenAI-compatible)](../guide/inference.md) — the full chat surface behind `model="auto"`.
- [Chat reference](../reference/chat.md) — request params and response schema.
- [Streaming chat completions](./streaming-chat.md) — token-by-token output for longer generations.
- Prove it on your own data: [run an eval](./evaluate-on-your-data.md) that benchmarks `"auto"` against frontier baselines on your own labeled texts.
