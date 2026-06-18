"""Pareta — Python client.

Deploy open-weights endpoints, run metered inference, browse the benchmark
catalog, and eval models on your own data.

    from pareta import Pareta
    pa = Pareta.from_env()                       # PARETA_API_KEY
    pa.chat.completions.create(model="ep_…", messages=[{"role": "user", "content": "hi"}])

Inference is OpenAI-compatible, so you can equally point the `openai` SDK at
`base_url` + your `pareta_sk_` key. The SDK's unique value is the control plane
(deploy / eval / discovery), landing slice by slice (see SDK_PLAN.md).
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
    Endpoint,
    Task,
    TaskMatch,
    TaskMatchCandidate,
    EvalSet,
    EvalRun,
    EvalResult,
    Leaderboard,
    LeaderboardEntry,
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
    "Endpoint",
    "Task",
    "TaskMatch",
    "TaskMatchCandidate",
    "EvalSet",
    "EvalRun",
    "EvalResult",
    "Leaderboard",
    "LeaderboardEntry",
    "FrontierModel",
]
