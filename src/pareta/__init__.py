"""Pareta — Python client.

One model id — ``"auto"`` — and Pareta plans each request, routes it to
benchmark-proven open specialists, verifies, and falls back to a frontier
model when that's the right call. One request, one bill.

    from pareta import Pareta
    pa = Pareta.from_env()                       # PARETA_API_KEY
    pa.chat.completions.create(model="auto", messages=[{"role": "user", "content": "hi"}])

Inference is OpenAI-compatible, so you can equally point the `openai` SDK at
`base_url` + your `pareta_sk_` key with ``model="auto"``. The SDK's unique
value is everything around that call: evals on your own data (with "auto" as
a first-class contender), auto metrics + frontier comparison, and task
discovery (``tasks.match``).
"""

from ._client import Pareta, AsyncPareta
from ._version import __version__
from ._exceptions import (
    ParetaError,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    BadRequestError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    ConflictError,
    InsufficientCreditsError,
    RateLimitError,
    EndpointNotReadyError,
)
from ._models import (
    ChatCompletion,
    ChatCompletionChunk,
    Choice,
    Message,
    Usage,
    Model,
    ModelList,
    Task,
    TaskMatch,
    TaskMatchCandidate,
    Capability,
    Transcription,
    Speech,
    Rerank,
    RerankResult,
    Embeddings,
    ImageGeneration,
    EvalSet,
    EvalRun,
    EvalResult,
    EvalItemResult,
    FrontierModel,
)

__all__ = [
    "Pareta",
    "AsyncPareta",
    "__version__",
    # errors
    "ParetaError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "BadRequestError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "InsufficientCreditsError",
    "RateLimitError",
    "EndpointNotReadyError",
    # models
    "ChatCompletion",
    "ChatCompletionChunk",
    "Choice",
    "Message",
    "Usage",
    "Model",
    "ModelList",
    "Task",
    "TaskMatch",
    "TaskMatchCandidate",
    "Capability",
    "Transcription",
    "Rerank",
    "RerankResult",
    "Embeddings",
    "ImageGeneration",
    "Speech",
    "EvalSet",
    "EvalRun",
    "EvalResult",
    "EvalItemResult",
    "FrontierModel",
]
