"""Opt-in pytest plugin: -p tests.offline_guard. Blocks external HTTP and dotenv."""
import os
from unittest.mock import patch


def forbidden(*args, **kwargs):
    raise AssertionError("External HTTP or environment-file access forbidden in offline verification")


def pytest_configure(config):
    # Remove inherited live configuration without displaying its values.
    for name in list(os.environ):
        if name.startswith('LLM_'):
            del os.environ[name]
    config._offline_patches = [
        patch('dotenv.load_dotenv', forbidden),
        patch('dotenv.dotenv_values', forbidden),
        patch('httpx.HTTPTransport.handle_request', forbidden),
        patch('httpx.AsyncHTTPTransport.handle_async_request', forbidden),
    ]
    for guard in config._offline_patches:
        guard.start()


def pytest_unconfigure(config):
    for guard in reversed(getattr(config, '_offline_patches', [])):
        guard.stop()
