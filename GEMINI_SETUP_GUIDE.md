# Gemini API Setup Guide for RouteIQ

## Overview

RouteIQ can use Google's Gemini models for LLM-guided heuristic evolution through Gemini's OpenAI-compatible API endpoint.

## Quick Setup

### 1. Get Your API Key

1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy your API key (starts with `AI...`)

### 2. Configure .env File

Edit the `.env` file in the project root:

```bash
# RouteIQ runtime LLM configuration
LLM_PROVIDER=openai
LLM_API_KEY=YOUR_ACTUAL_API_KEY_HERE
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-2.0-flash-exp
LLM_TEMPERATURE=0.7
LLM_TIMEOUT=60.0
```

**Important:**
- Replace `YOUR_ACTUAL_API_KEY_HERE` with your actual Gemini API key
- Do NOT use quotes around the API key value
- Keep LLM_PROVIDER as `openai` (this uses the OpenAI-compatible endpoint)

### 3. Available Models

| Model Name | Speed | Quality | Use Case |
|------------|-------|---------|----------|
| `gemini-2.0-flash-exp` | Fast | Good | **Recommended** for RouteIQ |
| `gemini-1.5-flash` | Fast | Good | Stable alternative |
| `gemini-1.5-pro` | Slower | Better | More complex heuristics |

### 4. Verify Configuration

Run the connection test (after removing `@pytest.mark.skip`):

```bash
pytest tests/manual/test_gemini_connection.py::test_gemini_connection -v -s
```

Or use the system status endpoint after starting the backend:

```bash
uvicorn api.main:app --reload
# Visit: http://localhost:8000/api/system/status
```

## Common Issues

### Issue: "404 Not Found"

**Cause:** Incorrect base URL

**Solution:** Verify you're using:
```
https://generativelanguage.googleapis.com/v1beta/openai
```

Not: `https://generativelanguage.googleapis.com/v1beta` (missing /openai)

### Issue: "401 Unauthorized"

**Cause:** Invalid or missing API key

**Solutions:**
1. Check API key is copied correctly from AI Studio
2. Ensure no spaces or quotes in .env file
3. Verify API key hasn't been revoked

### Issue: "Model not found" or "Invalid model"

**Cause:** Incorrect model name

**Solution:** Use one of the exact model names listed above. Model names are case-sensitive.

Common mistake: `gemini-3.8-flash` (does not exist)
Correct: `gemini-2.0-flash-exp`

### Issue: API key appears in logs or errors

**Cause:** Sensitive data exposure

**Solution:** The LLM client automatically redacts API keys from error messages. If you see an API key exposed, this is a bug - please report it.

## Testing Without API Key

RouteIQ supports mock mode for testing without making real API calls:

```python
# In evolution request
{
    "mode": "mock",  # Instead of "live"
    "num_generations": 3,
    ...
}
```

Mock mode:
- Uses pre-defined heuristic templates
- No API calls or costs
- Useful for testing and demos
- Results are deterministic

## Security Best Practices

1. **Never commit .env:** Already in `.gitignore`
2. **Never paste API keys in chat:** Kiro (the IDE assistant) does not need your runtime API key
3. **Rotate keys regularly:** Generate new keys periodically
4. **Monitor usage:** Check Google AI Studio for API usage and quotas
5. **Use environment-specific keys:** Different keys for dev/production if needed

## Cost Management

Gemini pricing (as of 2024):
- Flash models: Very low cost per token
- Pro models: Higher cost but still reasonable

RouteIQ evolution runs typically:
- 3 generations × 4 candidates = 12 API calls
- ~1000 tokens per request
- Total cost: Usually < $0.10 per evolution run

Configure smaller runs during development:
```python
{
    "num_generations": 2,        # Instead of 5
    "candidates_per_generation": 3,  # Instead of 5
    "mode": "mock"              # For testing
}
```

## Architecture Notes

### Two Separate LLMs

RouteIQ uses **two completely separate LLMs**:

1. **Kiro (Development Time):** Claude Sonnet, used by the IDE to write RouteIQ's code
   - Never accessed by the running application
   - Your Anthropic API key stays in VS Code settings
   - Not configured in .env

2. **Runtime LLM (Application):** Configured Gemini model, used by RouteIQ when running
   - Generates routing heuristics during evolution
   - Configured in .env
   - Never accessed by Kiro

**These must NEVER be mixed.**

### Provider Configuration

The `LLM_PROVIDER=openai` setting tells RouteIQ to use the OpenAI-compatible client, which works with:
- OpenAI GPT models (original use case)
- **Google Gemini** (via OpenAI-compatible endpoint)
- Groq models
- Local models with OpenAI-compatible APIs
- Any other OpenAI-compatible endpoint

The actual provider is determined by the `LLM_BASE_URL`, not the provider name.

## Next Steps

After configuration:

1. **Verify connection:** Run the manual test
2. **Test mock mode:** Ensure evolution works without API calls
3. **Test live mode:** Run a small evolution with `mode: "live"`
4. **Monitor results:** Check that candidates are valid and evaluated
5. **Tune parameters:** Adjust temperature, generations, candidates

## Support

If you encounter issues:

1. Check this guide's "Common Issues" section
2. Verify configuration with the connection test
3. Try mock mode to isolate configuration issues
4. Check Google AI Studio for API key status and quotas
5. Review backend logs for detailed error messages

## References

- [Google AI Studio](https://aistudio.google.com/)
- [Gemini API Documentation](https://ai.google.dev/docs)
- [OpenAI API Compatibility](https://ai.google.dev/api/generate-content#openai-compatibility)
