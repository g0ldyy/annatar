import os

import uvicorn

if __name__ == "__main__":
    workers = int(os.getenv("WORKERS", "2"))

    # Start Uvicorn with the specified number of workers
    uvicorn.run("annatar.main:app", host="0.0.0.0", reload=False, workers=workers)
