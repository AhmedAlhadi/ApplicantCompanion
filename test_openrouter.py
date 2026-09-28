import os
import json
import httpx

def test_openrouter():
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "test",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False
                }
            }
        }
    }
    resp = httpx.post(url, headers=headers, json=payload)
    print(resp.status_code)
    print(resp.text)

if __name__ == "__main__":
    test_openrouter()