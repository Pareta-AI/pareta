# images

`client.images` is the image-generation surface: turn a text prompt into a
PNG. It exposes the `image-gen` **capability lane** as one method:

- [`images.generate`](#imagesgenerate): generate an image from a prompt and
  save it to a file.

Two facts set this namespace apart from the rest of the SDK:

- **Its own route, not `chat.completions`.** Generation hits
  `POST /v1/images/generations` directly. You never pick a serving model, a
  GPU, or a step count; Pareta resolves the lane (`hidream-1` today), exactly
  as `model="auto"` does for chat.
- **Metered flat per image.** Every generation debits the same per-image
  price against your org balance — the model renders at full 2K quality
  internally regardless of the delivery size, so every size costs the same.
  The `X-Pareta-Billed` response header carries the receipt in micro-USD. An
  empty balance raises [`InsufficientCreditsError`](exceptions.md) (402).

Calls go through the client's transport, so auth, retries, and typed error
mapping apply exactly as they do everywhere else.

All examples use the synchronous `Pareta` client. The method has an `async`
twin with the same signature on `AsyncPareta`.

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
img = pa.images.generate("a lighthouse on a rocky coast at dusk")
img.save("lighthouse.png")
img.size                        # "1024x1024" — the ACTUAL delivered size
```

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const img = await pa.images.generate("a lighthouse on a rocky coast at dusk");
await img.save("lighthouse.png");            // decoded bytes (Node)
```

---

## images.generate

```python
pa.images.generate(prompt, *, size=None, seed=None) -> ImageGeneration
```

| Parameter | Type | Description |
|---|---|---|
| `prompt` | `str` | What to render. Required, ≤4000 chars. |
| `size` | `str \| None` | Delivery size. Omit for `1024x1024`. Also: `2048x2048`, `2304x1728`, `1728x2304`, `2560x1440`, `1440x2560`. Every size bills the same flat price. |
| `seed` | `int \| None` | Pin the noise seed for reproducibility. |

TypeScript: `pa.images.generate(prompt, { size?, seed? })`.

A generation takes ~15s when the lane is warm; the first request after a
quiet spell can take a few minutes while the model boots.

## The ImageGeneration object

| Accessor | Type | Description |
|---|---|---|
| `.image` | `bytes` / `Uint8Array` | The generated image, base64-decoded PNG bytes. |
| `.b64_json` / `.b64Json` | `str \| None` | The raw base64 payload. |
| `.size` | `str \| None` | The actual delivered size (e.g. `"1024x1024"`). |
| `.model` | `str \| None` | The lane's public model name (`hidream-1`). |
| `.created` | `int \| None` | Unix timestamp. |
| `.save(path)` | — | Write the PNG to `path`. Returns the object for chaining. |

## CLI

```bash
pareta image "a red fox in the snow" --out fox.png --size 2048x2048
```

Billed flat per image — the table in [`pareta --help`](../guide/cli.md) lists
the options.
