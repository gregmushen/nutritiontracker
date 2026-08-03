from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from setproctitle import setproctitle

from app.auth import require_auth, require_multi_user
from app.config import settings
from app.database import get_connection, init_schema
from app.repositories.foods import FoodRepository
from app.routes.activity import router as activity_router
from app.routes.diary import router as diary_router
from app.routes.foods import router as foods_router
from app.routes.imports import router as imports_router
from app.routes.journal import router as journal_router
from app.routes.kitchen import router as kitchen_router
from app.routes.recipes import router as recipes_router
from app.routes.stats import router as stats_router
from app.routes.users import router as users_router
from app.routes.weight import router as weight_router

STATIC_DIR = Path(__file__).parent / "static"
LANDING_PAGE_PATH = STATIC_DIR / "index.html"
FAVICON_PATH = STATIC_DIR / "favicon.svg"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setproctitle("Nutrition Tracker Service")
    conn = get_connection()
    init_schema(conn)
    FoodRepository(conn).ensure_fts()
    app.state.db = conn
    yield
    conn.close()


app = FastAPI(
    title="Nutrition Tracker",
    version=settings.api_version,
    description="""Open-source REST API for nutrition tracking.

Designed to be called by AI agents to log and query nutrition data.

**Data sources:** Pre-loaded USDA FoodData Central and OpenFoodFacts databases.

**Key endpoints:**
- `/foods/search` — search 500k+ foods by name with prefix matching
- `/foods/barcode/{barcode}` — look up by EAN/UPC barcode
- `/diary/{date}/entries` — log what you ate
- `/stats/daily/{date}` — get today's nutrition totals
- `/weight` — track body weight
- `/recipes` — build recipes with auto-computed nutrition math

**Schema:** Full OpenAPI 3.0 schema at `/openapi.json`.
""",
    lifespan=lifespan,
)

_auth = [Depends(require_auth)]
app.include_router(foods_router, dependencies=_auth)
app.include_router(diary_router, dependencies=_auth)
app.include_router(stats_router, dependencies=_auth)
app.include_router(journal_router, dependencies=_auth)
app.include_router(weight_router, dependencies=_auth)
app.include_router(recipes_router, dependencies=_auth)
app.include_router(kitchen_router, dependencies=_auth)
app.include_router(activity_router, dependencies=_auth)
app.include_router(imports_router, dependencies=_auth)
app.include_router(
    users_router, dependencies=[Depends(require_auth), Depends(require_multi_user)]
)


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root():
    return FileResponse(LANDING_PAGE_PATH, media_type="text/html")


@app.api_route("/favicon.svg", methods=["GET", "HEAD"], include_in_schema=False)
def favicon():
    return FileResponse(FAVICON_PATH, media_type="image/svg+xml")


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.api_version}
