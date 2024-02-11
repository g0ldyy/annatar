import os

import uvicorn

BUILD_VERSION: str = os.getenv("BUILD_VERSION", "UNKNOWN")
HOST: str = os.getenv("LISTEN_HOST", "0.0.0.0")
PORT: int = int(os.getenv("LISTEN_PORT", "8000"))
WORKERS = int(os.getenv("WORKERS", "2"))


if __name__ == "__main__":
    resource_attrs_raw: str = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    if resource_attrs_raw:
        resource_attrs: list[str] = resource_attrs_raw.split(",")
        resource_attrs.extend(
            [
                f"service.version={BUILD_VERSION}",
                "service.instance.id=annatar-vm",
            ]
        )
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(resource_attrs)

    uvicorn.run(
        "annatar.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        workers=WORKERS,
        loop="uvloop",
    )
