"""FastAPI entry point"""

import logging

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("next_star_hunter")

app = FastAPI(
    title="Next Star Hunter API",
    description="Backend API for the Next Star Hunter chatbot service.",
    version="0.1.0",
    docs_url="/docs",
)


@app.get("/health", tags=["system"])
async def health_check():
    """Return a lightweight status response for local and deployment checks."""
    logger.info("request_received path=/health")
    return {"status": "ok", "service": "next-star-hunter"}
