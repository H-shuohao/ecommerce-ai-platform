from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(include_in_schema=False)
WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


@router.get("/demo", response_class=FileResponse)
async def agent_demo() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")
