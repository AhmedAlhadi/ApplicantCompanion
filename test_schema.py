import os
import json
import httpx
from pydantic import BaseModel
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from app.schemas.agents import JDAnalysisResult
from app.llm.json_schema import openai_strict_schema

def test_openrouter():
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"
    }
    
    schema = JDAnalysisResult.model_json_schema()
    strict_schema = openai_strict_schema(schema)
    
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "test",
                "strict": True,
                "schema": strict_schema
            }
        }
    }
    
    resp = httpx.post(url, headers=headers, json=payload)
    print("Status:", resp.status_code)
    print("Response:", resp.text)

if __name__ == "__main__":
    test_openrouter()