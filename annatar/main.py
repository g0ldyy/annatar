from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from annatar import instrumentation, logging, middleware, routes, web

logging.init()
instrumentation.init()
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# XXX These are executed in reverse order
app.add_middleware(middleware.Metrics)
app.add_middleware(middleware.RequestLogger)
app.add_middleware(middleware.RequestID)

app.add_route("/metrics", instrumentation.metrics_handler)


# handle CORS preflight requests
@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request, rest_of_path: str) -> Response:
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
        },
    )


# set CORS headers
@app.middleware("http")
async def add_CORS_header(request: Request, call_next: Any):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    return response


app.include_router(routes.router)
app.include_router(web.router)
instrumentation.instrument_fastapi(app)
