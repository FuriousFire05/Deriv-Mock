from fastapi import FastAPI, HTTPException

from app.models import TriageRequest, TriageResult
from app.triage import TriageConfigurationError, TriageProviderError, triage_message


app = FastAPI(title="Support Triage API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/triage", response_model=TriageResult)
def triage(request: TriageRequest) -> TriageResult:
    try:
        return triage_message(request.message)
    except TriageConfigurationError:
        raise HTTPException(503, "Triage service is unavailable.") from None
    except TriageProviderError:
        raise HTTPException(502, "Triage service could not process the message.") from None
