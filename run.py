#!/usr/bin/env python3
"""
Simple script to run the FastAPI voice agent middleware server
"""

import uvicorn
import os
from pathlib import Path

if __name__ == "__main__":
    # Set the working directory to the backend folder
    backend_dir = Path(__file__).parent
    os.chdir(backend_dir)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True
    )
