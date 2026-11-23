# LLM Configuration Guide for RouteIQ

## Overview

RouteIQ uses LLM-guided evolution to discover and evaluate routing heuristics. The system supports two modes:

1. **Mock Mode** — Uses predefined test candidates (no API key required)
2. **Live Mode** — Connects to a real LLM provider to generate novel heuristics

This guide explains how to configure Live Mode.

## Quick Start

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your provider credentials:
   ```env
   LLM_PROVIDER=openai
   LLM_API_KEY=sk-your-actual-key-here
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_MODEL=gpt-4
   LLM_TEMPERATURE=0.7
   ```

3. Restart the backend:
   ```bash
   py -m uvicorn api.main:app --reload
   ```

4. Verify configuration:
   - Open the RouteIQ homepage
   - Check "System Status" section
   - Live LLM should show: `✅ configured` with provider/model info

## Supported Providers

### OpenAI
```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4
```

**Recommended models:**
- `gpt-4` — Best quality, higher cost
- `gpt-4-turbo` — Faster, good quality
- `gpt-3.5-turbo` — Fastest, lowest cost

### Groq
```env
LLM_PROVIDER=groq
LLM_API_KEY=gsk-...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-70b-versatile
```

**Recommended models:**
- `llama-3.1-70b-versatile` — Best for code generation
- `mixtral-8x7b-32768` — Alternative option

### Anthropic Claude (via OpenAI-compatible endpoint)
```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_MODEL=claude-3-5-sonnet-20241022
```

### Local Models (Ollama, LM Studio, etc.)
```env
LLM_PROVIDER=local
LLM_API_KEY=not-needed
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=codellama
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_PROVIDER` | No | `openai` | Provider identifier (openai, groq, anthropic, local) |
| `LLM_API_KEY` | Yes* | — | API key for your provider (* not required for local models) |
| `LLM_BASE_URL` | Yes | — | API endpoint URL (must support OpenAI chat completions format) |
| `LLM_MODEL` | Yes | — | Model identifier (e.g., `gpt-4`, `llama-3.1-70b-versatile`) |
| `LLM_TEMPERATURE` | No | `0.7` | Sampling temperature (0.0-1.0) |
| `LLM_TIMEOUT` | No | `30.0` | Request timeout in seconds |

## Security Best Practices

### ✅ DO:
- Keep `.env` in `.gitignore` (already configured)
- Use separate API keys for development and production
- Rotate keys periodically
- Set usage limits in your provider dashboard
- Monitor API usage and costs

### ❌ DON'T:
- Commit `.env` files to Git
- Share API keys in chat, email, or screenshots
- Use production keys in development
- Leave default example keys in `.env`

## Verification

### Check Configuration Status

**Via Frontend:**
1. Open RouteIQ homepage (http://localhost:5173)
2. Look at "System Status" section
3. Live LLM should show:
   - ✅ If configured: Provider and model info
   - ⚪ If not configured: "Configure .env"

**Via API:**
```bash
curl http://localhost:8000/api/system/status
```

Response (configured):
```json
{
  "live_llm": {
    "status": "configured",
    "message": "Provider: openai, Model: gpt-4",
    "provider": "openai",
    "model": "gpt-4"
  }
}
```

Response (not configured):
```json
{
  "live_llm": {
    "status": "not_configured",
    "message": "Configure .env to enable",
    "provider": null,
    "model": null
  }
}
```

**Important:** API never returns the API key — only configuration status.

### Test Evolution with Mock Mode

Before using Live Mode, test with Mock Mode to verify the system works:

1. In Evolution panel, select **Mock** mode
2. Click "Run Evolution"
3. Verify fitness chart and candidate visualization appear
4. Check that valid/invalid candidates are correctly identified

### Test Evolution with Live Mode

Once configured:

1. In Evolution panel, select **Live** mode
2. Configure experiment parameters
3. Click "Run Evolution"
4. Monitor:
   - Generation progress
   - Candidate validity (valid/invalid counts)
   - Fitness progression
   - API usage (check provider dashboard)

## Troubleshooting

### "Configure .env to enable"

**Cause:** `.env` file missing or incomplete

**Solution:**
1. Verify `.env` file exists in repository root
2. Check all required fields are set
3. Restart backend after editing `.env`

### "API key required for provider 'openai'"

**Cause:** `LLM_API_KEY` is empty or not set

**Solution:**
1. Check `.env` has `LLM_API_KEY=sk-...`
2. Verify no extra spaces around the `=` sign
3. Restart backend

### Evolution fails with "Connection error"

**Possible Causes:**
- Invalid API key
- Network connectivity issue
- Provider service downtime
- Rate limit exceeded

**Solution:**
1. Verify API key is correct
2. Check provider dashboard for usage/limits
3. Try again after a few minutes
4. Check backend logs for detailed error

### Generated heuristics are all invalid

**Possible Causes:**
- Model not good at code generation
- Temperature too high (producing nonsense)
- Prompt needs refinement

**Solution:**
1. Try a code-specialized model (e.g., `gpt-4`, `codellama`)
2. Lower temperature to 0.2-0.5 for more deterministic output
3. Check generated code in Evolution panel for common errors

## Cost Estimation

### OpenAI GPT-4
- **Per candidate:** ~1,000-2,000 tokens
- **Per generation (4 candidates):** ~$0.10-0.20
- **Full evolution (3 generations):** ~$0.30-0.60

### Groq (Free Tier)
- **Rate Limits:** 30 requests/minute, 14,400 tokens/minute
- **Cost:** Free (as of 2024)
- **Suitable for:** Development and testing

### Local Models
- **Cost:** Hardware only (no API fees)
- **Speed:** Depends on your hardware
- **Quality:** May be lower than commercial models

## Development vs Production

### Development
```env
# Use fast, cheap model for testing
LLM_MODEL=gpt-3.5-turbo
LLM_TEMPERATURE=0.7
```

### Production Research
```env
# Use best model for final experiments
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.5
```

## Mock Mode vs Live Mode

| Feature | Mock Mode | Live Mode |
|---------|-----------|-----------|
| API Key Required | ❌ No | ✅ Yes |
| Real LLM Calls | ❌ No | ✅ Yes |
| Cost | Free | Varies by provider |
| Candidate Diversity | Fixed (8 predefined) | Novel each run |
| Use Case | Testing, demos | Research, evaluation |
| Configuration | None | `.env` file |

## Additional Resources

- **OpenAI API:** https://platform.openai.com/docs
- **Groq API:** https://console.groq.com/docs
- **Ollama (Local):** https://ollama.ai/
- **LM Studio (Local):** https://lmstudio.ai/

## Support

If you encounter issues:
1. Check backend logs: `py -m uvicorn api.main:app --reload`
2. Verify `.env` configuration
3. Test Mock mode first
4. Check provider API status pages
5. Review this guide for troubleshooting steps

**Remember:** This is a research capstone project. Mock mode is always available for testing and demonstrations even without LLM credentials.
