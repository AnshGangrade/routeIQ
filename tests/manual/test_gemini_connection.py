"""
Manual test for Gemini API connectivity.

This test verifies that the configured Gemini endpoint works correctly.
It makes a minimal real API call to confirm:
1. Endpoint URL is correct
2. API key is valid
3. Model name is supported
4. Response format is compatible

Run manually with: pytest tests/manual/test_gemini_connection.py -v -s
"""

import pytest
import os
from dotenv import load_dotenv


def test_gemini_connection():
    """
    Test Gemini API connection with minimal request.
    
    This confirms that:
    - .env file is loaded correctly
    - Base URL is correct for Gemini
    - API key is valid
    - Model name is supported
    """
    load_dotenv()
    
    provider = os.getenv("LLM_PROVIDER", "openai")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    
    print("\n" + "=" * 70)
    print("Gemini Connection Test")
    print("=" * 70)
    print(f"Provider: {provider}")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print(f"API Key: {'*' * 20 if api_key else 'NOT SET'}")
    print("=" * 70)
    
    # Validate configuration
    assert api_key, "LLM_API_KEY not set in .env file"
    assert base_url, "LLM_BASE_URL not set in .env file"
    assert model, "LLM_MODEL not set in .env file"
    
    # Make minimal request
    import httpx
    
    endpoint = f"{base_url}/chat/completions"
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Say 'test' and nothing else."
            }
        ],
        "temperature": 0.0,
        "max_tokens": 10
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    print(f"\nSending request to: {endpoint}")
    print(f"Model: {model}")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            
            print(f"\nResponse Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Response Body:\n{response.text[:500]}")
                
                # Check for common errors
                if response.status_code == 401:
                    pytest.fail(
                        "401 Unauthorized: API key is invalid or not configured correctly. "
                        "Check your Gemini API key in .env file."
                    )
                elif response.status_code == 404:
                    pytest.fail(
                        f"404 Not Found: Endpoint '{endpoint}' not found. "
                        f"Check if LLM_BASE_URL is correct for Gemini's OpenAI-compatible endpoint."
                    )
                elif response.status_code == 400:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("error", {}).get("message", response.text[:200])
                        pytest.fail(
                            f"400 Bad Request: {error_msg}\n"
                            f"This may indicate an unsupported model name. "
                            f"Current model: {model}\n"
                            f"Try: gemini-2.0-flash-exp or gemini-1.5-flash"
                        )
                    except:
                        pytest.fail(f"400 Bad Request: {response.text[:200]}")
                else:
                    pytest.fail(f"HTTP {response.status_code}: {response.text[:200]}")
            
            response.raise_for_status()
            data = response.json()
            
            # Verify response format
            assert "choices" in data, "Response missing 'choices' field"
            assert len(data["choices"]) > 0, "Response has no choices"
            
            message = data["choices"][0].get("message", {})
            content = message.get("content", "")
            
            print(f"\n✓ Connection successful!")
            print(f"Response content: {content[:100]}")
            
            if "usage" in data:
                print(f"Token usage: {data['usage']}")
            
            print("\n" + "=" * 70)
            print("SUCCESS: Gemini API is configured correctly")
            print("=" * 70)
            
    except httpx.ConnectError as e:
        pytest.fail(
            f"Connection failed: {e}\n"
            f"Check your internet connection and verify the base URL."
        )
    except httpx.TimeoutException:
        pytest.fail(
            f"Request timed out after 30 seconds. "
            f"Check your internet connection and Gemini API status."
        )
    except Exception as e:
        pytest.fail(f"Unexpected error: {type(e).__name__}: {e}")


@pytest.mark.skip(reason="Manual test - informational only")
def test_gemini_configuration_guide():
    """
    Print configuration guidance for Gemini API.
    
    Run with: pytest tests/manual/test_gemini_connection.py::test_gemini_configuration_guide -v -s
    """
    guide = """
    ════════════════════════════════════════════════════════════════════
    Gemini API Configuration Guide for RouteIQ
    ════════════════════════════════════════════════════════════════════
    
    Google Gemini provides an OpenAI-compatible API endpoint. Configure
    your .env file as follows:
    
    1. Get your API key:
       - Go to: https://aistudio.google.com/app/apikey
       - Create or copy your API key
    
    2. Configure .env file:
       
       LLM_PROVIDER=openai
       LLM_API_KEY=YOUR_GEMINI_API_KEY_HERE
       LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
       LLM_MODEL=gemini-2.0-flash-exp
       LLM_TEMPERATURE=0.7
       LLM_TIMEOUT=60.0
    
    3. Available Models (as of 2024):
       - gemini-2.0-flash-exp (recommended, fast)
       - gemini-1.5-flash (stable)
       - gemini-1.5-pro (more capable)
    
    4. Important Notes:
       - Provider should be "openai" (using OpenAI-compatible endpoint)
       - Base URL includes /openai path for compatibility
       - Model names are case-sensitive
       - Never commit .env file to Git
    
    5. Test your configuration:
       - Remove @pytest.mark.skip from test_gemini_connection above
       - Run: pytest tests/manual/test_gemini_connection.py::test_gemini_connection -v -s
    
    ════════════════════════════════════════════════════════════════════
    """
    print(guide)
    

if __name__ == "__main__":
    # Allow running as script for quick testing
    test_gemini_configuration_guide()
