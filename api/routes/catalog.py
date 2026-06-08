from fastapi import APIRouter

from gui.sherloq_app.services.dispatcher import list_tools

router = APIRouter()


@router.get("/tools")
def get_tools():
    return {"tools": list_tools(), "count": len(list_tools())}
