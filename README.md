# Support Triage API

A small FastAPI service that uses an OpenAI model to classify support messages,
assign priority, summarize the issue, recommend a next action, and indicate whether
human intervention is needed.

## Prerequisites and installation

Install Python 3.13+ and `uv`. The repository's `.python-version` selects Python
3.13. Run all commands from the repository root; examples use PowerShell.

```powershell
uv sync --locked
```

This creates `.venv` and installs the locked application and test dependencies.

## Configuration

Set the required key in the same PowerShell session used to start the server:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

Optionally override the model (the default is `gpt-5.6-luna`):

```powershell
$env:OPENAI_MODEL = "gpt-5.6-luna"
```

The configured model must support the Responses API and structured outputs.
Credentials must not be committed. `.env` files are ignored by Git, but the
application does not automatically load them; set environment variables explicitly.

## Run

```powershell
uv run --locked python -m uvicorn app.main:app
```

The server listens at `http://127.0.0.1:8000`. Use a second terminal for requests.

## HTTP examples

Health check (does not check provider connectivity or require an API key):

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

Response: `{"status":"healthy"}`

Triage a message:

```powershell
$body = @{ message = "My withdrawal is delayed." } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/triage" -ContentType "application/json" -Body $body
```

Example JSON response (actual classification and wording may vary):

```json
{
  "category": "withdrawal",
  "priority": "high",
  "summary": "Customer reports a delayed withdrawal.",
  "recommended_action": "Ask for the transaction reference and investigate its status.",
  "requires_human": true
}
```

Categories: `deposit`, `withdrawal`, `account`, `trading`, `technical`, `other`.
Priorities: `low`, `medium`, `high`, `critical`.
Missing, empty, whitespace-only, or non-string messages return HTTP 422.
Missing configuration returns HTTP 503 with
`{"detail":"Triage service is unavailable."}`. Provider failures or unusable
output return HTTP 502 with
`{"detail":"Triage service could not process the message."}`.

## Tests

```powershell
uv run --locked python -m pytest -q
```

Tests use FastAPI TestClient and a mocked provider transport while exercising the
real SDK parser. They require no API key and make no real network calls. Coverage
includes successful requests, input validation, model configuration, provider
errors, timeouts, refusals, incomplete responses, and invalid output.

## Architecture and design decisions

- `app/main.py`: HTTP routes and stable, sanitized error responses.
- `app/models.py`: Pydantic request validation and an exact six-field response
  schema with allowed categories/priorities and non-empty summary/action strings.
- `app/triage.py`: environment configuration, prompt, and isolated OpenAI call
  using `responses.parse(text_format=TriageResult)`. The model performs triage;
  there is no Python keyword routing. SDK retries are disabled and the client
  timeout is 30 seconds.
- `tests/test_api.py`: HTTP-boundary tests with only the external provider
  transport replaced. `uv.lock` records dependency versions.

## Limitations

Actual classification quality depends on the configured OpenAI model and message
context. Schema validation guarantees structure, not factual accuracy or correct
judgment. Automated tests validate integration behavior, not live classification
quality. Live triage requires provider access and incurs provider latency and
usage costs. Messages are sent to OpenAI with `store=False`; this is not a
guarantee of zero provider retention. Recommended actions are suggestions only:
the service does not execute actions, create tickets, or persist results.
