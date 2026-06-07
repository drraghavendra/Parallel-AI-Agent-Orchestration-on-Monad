from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from parser import AdvancedSolidityASTProfiler
import uvicorn

app = FastAPI(
    title="Monad Parallel-Native Optimizer Engine Backend",
    version="2.2.0"
)

# Active Cross-Origin Resource Sharing protocol limits
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RefactorPayload(BaseModel):
    source_code: str

@app.get("/api/v2/health")
async def health_check():
    return {
        "status": "online",
        "service": "Monad Parallel-Native Optimizer Engine Backend",
        "version": app.version
    }

@app.post("/api/v2/optimize-profile")
async def process_profiler_request(payload: RefactorPayload):
    if not payload.source_code.strip():
        raise HTTPException(status_code=400, detail="Solidity execution source field cannot be left blank.")
    
    try:
        compiled_profile = AdvancedSolidityASTProfiler.deep_profile_source(payload.source_code)
        return compiled_profile
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Internal Parser Error: {str(err)}")

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
