import uvicorn
import os
import sys

# Ensure the root of the project is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if __name__ == "__main__":
    print("Starting Ingestion Platform Backend server on http://127.0.0.1:8081")
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8081, reload=True)
