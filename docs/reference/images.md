# images

`client.images` is the image surface: turn a text prompt into a PNG, or edit
an existing image with a plain-language instruction. It exposes the
`image-gen` **capability lane** as two methods:

- [`images.generate`](#imagesgenerate): generate an image from a prompt and
  save it to a file.
- [`images.edit`](#imagesedit): edit a reference image with an instruction
  (no mask).

Two facts set this namespace apart from the rest of the SDK:

- **Its own routes, not `chat.completions`.** Generation hits
  `POST /v1/images/generations` and editing hits `POST /v1/images/edits`
  directly. You never pick a serving model, a GPU, or a step count; Pareta
  resolves the lane (`hidream-1` today), exactly as `model="auto"` does for
  chat.
- **Metered flat per call.** Every generation debits the same per-image
  price against your org balance — the model renders at full 2K quality
  internally regardless of the delivery size, so every size costs the same.
  Every edit debits the same per-edit price (edits cost more than
  generations: the reference roughly doubles the model's work). The
  `X-Pareta-Billed` response header carries the receipt in micro-USD. An
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

A generation takes ~12s when the lane is warm; the first request after a
quiet spell can take a few minutes while the model boots.

## images.edit

```python
pa.images.edit(image, prompt, *, seed=None) -> ImageGeneration
```

| Parameter | Type | Description |
|---|---|---|
| `image` | `str \| PathLike \| bytes` | The reference image: a file path, raw bytes, or an already-base64 string. PNG/JPEG, ≤25MB decoded. |
| `prompt` | `str` | The edit instruction, in plain language. Required, ≤4000 chars. Instruction-only — there is no mask parameter. |
| `seed` | `int \| None` | Pin the noise seed for reproducibility. |

TypeScript: `pa.images.edit(image, prompt, { seed? })` — `image` is a file
path (Node), `Uint8Array`/`ArrayBuffer`/`Blob`, or `{ base64 }`.

```python
pa.images.edit("product.png", "put the bottle on a marble surface").save("v2.png")
```

The output keeps the reference's aspect ratio (a ~1MP reference renders at
~4MP). A warm edit takes ~30s. Billed flat per edit.

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
