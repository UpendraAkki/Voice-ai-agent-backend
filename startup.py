"""
Azure Web App startup script for FastAPI backend
This file is used by Azure to start the FastAPI application
"""

import os
import uvicorn
from main import app

if __name__ == "__main__":
    # Azure Web App configuration
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
