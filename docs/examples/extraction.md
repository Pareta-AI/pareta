# Extraction: documents and contracts

Pull structured fields out of documents — a scanned invoice, a PDF, a contract
— and get JSON back. You'll extract vendor/total/line-items from a real invoice
image, then key legal fields from a contract's text.

Extraction is a chat job: image or text in, JSON out, so it all goes through
`chat.completions.create(model="auto")`, OpenAI-compatible on the wire. One
interface, whatever the document looks like; each request is one debit against
the org balance regardless of internal routing.

## Setup

Install the SDK ([installation guide](../guide/installation.md)) and set
`PARETA_API_KEY`.

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

## Visual documents (images and PDFs)

A visual document goes in as OpenAI content parts: one `text` part stating the
fields you want, one `image_url` part carrying the pixels as a base64 data URI.
Pin `temperature=0` — extraction wants determinism, not creativity — and ask for
JSON only, so the response parses without ceremony. This example downloads a
real invoice from the public examples dataset and extracts five fields from it.

**Python**

```python
import base64, json, urllib.request

url = ("https://raw.githubusercontent.com/Pareta-AI/example-datasets"
       "/main/invoice-extraction/documents/0.jpg")
img_b64 = base64.b64encode(urllib.request.urlopen(url).read()).decode()

resp = pa.chat.completions.create(
    model="auto",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": 'Extract {"vendor", "invoice_no", "date", '
                                     '"total", "line_items"} as JSON. Return ONLY the JSON object.'},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ],
    }],
    temperature=0,
    max_tokens=1024,
)
fields = json.loads(resp.choices[0].message.content)
```

**TypeScript**

```typescript
const url = "https://raw.githubusercontent.com/Pareta-AI/example-datasets" +
            "/main/invoice-extraction/documents/0.jpg";
const imgB64 = Buffer.from(await (await fetch(url)).arrayBuffer()).toString("base64");

const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{
    role: "user",
    content: [
      { type: "text", text: 'Extract {"vendor", "invoice_no", "date", ' +
                            '"total", "line_items"} as JSON. Return ONLY the JSON object.' },
      { type: "image_url", image_url: { url: `data:image/jpeg;base64,${imgB64}` } },
    ],
  }],
  temperature: 0,
  max_tokens: 1024,
});
const fields = JSON.parse(resp.choices[0].message.content ?? "");
```

Expected output for that document:

```json
{
  "vendor": "Bradley-Andrade",
  "invoice_no": "97159829",
  "date": "2015-09-18",
  "total": 978.12,
  "line_items": [ ... ]
}
```

### PDFs

You can hand a PDF into the same `image_url` slot. When a base64 data URI
declares `application/pdf` — or its decoded bytes start with the `%PDF` magic,
so a wrong or missing MIME type is still caught — the platform rasterizes it
server-side before inference: the PDF block is replaced with one PNG image
block per rendered page, up to the **first 8 pages** (sibling keys like
`detail` are preserved on each page). For longer documents, split the PDF or
send pre-rasterized page images. A PDF that cannot be rendered returns a 400
with a clear message rather than forwarding raw bytes a vision model would
reject. Plain `http(s)` image
URLs and URL-encoded (non-base64) data URIs pass through untouched.

**Python**

```python
pdf_b64 = base64.b64encode(open("contract.pdf", "rb").read()).decode()

{"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_b64}"}}
```

**TypeScript**

```typescript
const pdfB64 = (await readFile("contract.pdf")).toString("base64");

({ type: "image_url", image_url: { url: `data:application/pdf;base64,${pdfB64}` } });
```

Full runnable example: [python/extraction/visual_document.py](https://github.com/Pareta-AI/examples/blob/main/python/extraction/visual_document.py) · [typescript/extraction/visual-document.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/extraction/visual-document.ts)

## Contract fields (text)

When the document is already text, there is nothing special to do: the contract
goes in as ordinary string content on the same chat surface. Name the fields,
give the model an explicit out (`null`) for anything the text does not state —
otherwise it will guess — and keep `temperature=0`. Sample contract text from
CUAD (Hendrycks et al.), CC-BY-4.0.

**Python**

```python
import json
from pathlib import Path

contract_text = Path("data/sample-contract.txt").read_text()

prompt = ('Extract {"parties", "agreement_date", "effective_date", "governing_law"} '
          "as JSON. parties is a list of legal entity names; dates are YYYY-MM-DD; "
          "use null for anything the text does not state. Return ONLY the JSON object.")

resp = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": f"{prompt}\n\n---\n\n{contract_text}"}],
    temperature=0,
    max_tokens=512,
)
fields = json.loads(resp.choices[0].message.content)
print(fields["parties"], fields["governing_law"])
```

**TypeScript**

```typescript
import { readFile } from "node:fs/promises";

const contractText = await readFile("data/sample-contract.txt", "utf8");

const prompt = 'Extract {"parties", "agreement_date", "effective_date", "governing_law"} ' +
               "as JSON. parties is a list of legal entity names; dates are YYYY-MM-DD; " +
               "use null for anything the text does not state. Return ONLY the JSON object.";

const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: `${prompt}\n\n---\n\n${contractText}` }],
  temperature: 0,
  max_tokens: 512,
});
const fields = JSON.parse(resp.choices[0].message.content ?? "");
console.log(fields.parties, fields.governing_law);
```

Full runnable example: [python/extraction/contract_fields.py](https://github.com/Pareta-AI/examples/blob/main/python/extraction/contract_fields.py) · [typescript/extraction/contract-fields.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/extraction/contract-fields.ts)

## See also

- [Inference (OpenAI-compatible)](../guide/inference.md) — the full chat surface: streaming, extra params, error handling.
- [Chat reference](../reference/chat.md) — `chat.completions.create` request and response shapes.
- [Document extraction end-to-end](./document-extraction.md) — the full document workflow, from your own files to production.
- Prove it on your own data: [evaluate on your data](./evaluate-on-your-data.md) — benchmark `"auto"` against frontier baselines on your own documents before you commit.
