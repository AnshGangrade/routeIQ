"""
Tests for LLM client HTTP integration.

Tests HTTP request construction, error handling, and response parsing
using mocked HTTP responses. No real API calls or API keys required.
"""

import pytest
import httpx
from unittest.mock import Mock, patch
from engine.llm.client import LLMClient
from engine.llm.models import LLMConfig, LLMProvider, GenerationRequest


@pytest.fixture
def openai_config():
    """OpenAI-style configuration."""
    return LLMConfig(
        provider=LLMProvider.OPENAI,
        api_key="test-key-12345",
        base_url="https://api.example.com/v1",
        model="gpt-4",
        temperature=0.7,
        timeout=30.0
    )


@pytest.fixture
def gemini_config():
    """Gemini OpenAI-compatible configuration."""
    return LLMConfig(
        provider=LLMProvider.OPENAI,  # Uses OpenAI-compatible endpoint
        api_key="test-gemini-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-3.8-flash",
        temperature=0.5,
        timeout=30.0
    )


class TestLLMClientHTTP:
    """Test LLM client HTTP interactions."""
    
    def test_endpoint_construction(self, openai_config):
        """Test that endpoint URL is constructed correctly."""
        client = LLMClient(openai_config)
        
        # The endpoint should be base_url + /chat/completions
        expected_endpoint = "https://api.example.com/v1/chat/completions"
        
        # Mock the HTTP client to capture the request
        with patch.object(client.client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "choices": [
                    {"message": {"content": "test response"}}
                ],
                "usage": {"total_tokens": 10}
            }
            mock_post.return_value = mock_response
            
            request = GenerationRequest(prompt="test")
            client.generate(request)
            
            # Verify endpoint URL
            assert mock_post.call_args[0][0] == expected_endpoint
        
        client.close()
    
    def test_gemini_endpoint_with_trailing_slash(self, gemini_config):
        """Test Gemini endpoint construction with trailing slash in base_url."""
        client = LLMClient(gemini_config)
        
        # Gemini base_url ends with /openai/, so endpoint should be:
        # https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
        expected_endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        
        with patch.object(client.client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "test"}}]
            }
            mock_post.return_value = mock_response
            
            request = GenerationRequest(prompt="test")
            client.generate(request)
            
            # Verify no double slashes in URL
            actual_url = mock_post.call_args[0][0]
            assert actual_url == expected_endpoint
            assert "//" not in actual_url.replace("https://", "")
        
        client.close()
    
    def test_authorization_header(self, openai_config):
        """Test that Authorization header is set correctly."""
        client = LLMClient(openai_config)
        
        with patch.object(client.client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "test"}}]
            }
            mock_post.return_value = mock_response
            
            request = GenerationRequest(prompt="test")
            client.generate(request)
            
            # Check headers
            call_kwargs = mock_post.call_args[1]
            headers = call_kwargs['headers']
            assert headers['Authorization'] == "Bearer test-key-12345"
            assert headers['Content-Type'] == "application/json"
        
        client.close()
    
    def test_request_payload_format(self, openai_config):
        """Test that request payload follows OpenAI format."""
        client = LLMClient(openai_config)
        
        with patch.object(client.client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "test"}}]
            }
            mock_post.return_value = mock_response
            
            request = GenerationRequest(
                prompt="Generate a routing heuristic",
                generation_id="test-001"
            )
            client.generate(request)
            
            # Check payload structure
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs['json']
            
            assert payload['model'] == "gpt-4"
            assert payload['temperature'] == 0.7
            assert payload['messages'] == [
                {
                    "role": "user",
                    "content": "Generate a routing heuristic"
                }
            ]
        
        client.close()
    
    def test_http_401_error_handling(self, openai_config):
        """Test handling of 401 Unauthorized errors."""
        client = LLMClient(openai_config)
        
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": {"message": "Invalid API key"}
        }
        
        with patch.object(client.client, 'post') as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=Mock(),
                response=mock_response
            )
            
            request = GenerationRequest(prompt="test")
            
            with pytest.raises(RuntimeError) as exc_info:
                client.generate(request)
            
            error_msg = str(exc_info.value)
            assert "401" in error_msg
            assert "Invalid API key" in error_msg
        
        client.close()
    
    def test_http_404_error_handling(self, openai_config):
        """Test handling of 404 Not Found errors."""
        client = LLMClient(openai_config)
        
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": {"message": "Not found"}}
        
        with patch.object(client.client, 'post') as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=Mock(),
                response=mock_response
            )
            
            request = GenerationRequest(prompt="test")
            
            with pytest.raises(RuntimeError) as exc_info:
                client.generate(request)
            
            error_msg = str(exc_info.value)
            assert "404" in error_msg
        
        client.close()
    
    def test_http_400_bad_request(self, openai_config):
        """Test handling of 400 Bad Request (e.g., invalid model)."""
        client = LLMClient(openai_config)
        
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {"message": "Model not found: private-response-marker"}
        }
        
        with patch.object(client.client, 'post') as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "400 Bad Request",
                request=Mock(),
                response=mock_response
            )
            
            request = GenerationRequest(prompt="test")
            
            with pytest.raises(RuntimeError) as exc_info:
                client.generate(request)
            
            error_msg = str(exc_info.value)
            assert "400" in error_msg
            assert "Provider rejected the request" in error_msg
            assert "private-response-marker" not in error_msg
        
        client.close()
    
    def test_network_error_handling(self, openai_config):
        """Test handling of network connection errors."""
        client = LLMClient(openai_config)
        
        with patch.object(client.client, 'post') as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")
            
            request = GenerationRequest(prompt="test")
            
            with pytest.raises(RuntimeError) as exc_info:
                client.generate(request)
            
            error_msg = str(exc_info.value)
            assert "Connection refused" in error_msg or "ConnectError" in error_msg
        
        client.close()
    
    def test_timeout_error_handling(self, openai_config):
        """Test handling of request timeouts."""
        client = LLMClient(openai_config)
        
        with patch.object(client.client, 'post') as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")
            
            request = GenerationRequest(prompt="test")
            
            with pytest.raises(RuntimeError) as exc_info:
                client.generate(request)
            
            error_msg = str(exc_info.value)
            assert "timeout" in error_msg.lower() or "TimeoutException" in error_msg
        
        client.close()
    
    def test_successful_response_parsing(self, openai_config):
        """Test parsing of successful API response."""
        client = LLMClient(openai_config)
        
        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": "def score_candidates(context): return [1.0, 2.0, 3.0]"
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            },
            "model": "gpt-4",
            "id": "chatcmpl-123"
        }
        
        with patch.object(client.client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_post.return_value = mock_response
            
            request = GenerationRequest(
                prompt="test",
                generation_id="gen-001",
                metadata={"iteration": 1}
            )
            response = client.generate(request)
            
            # Verify response structure
            assert response.raw_content == "def score_candidates(context): return [1.0, 2.0, 3.0]"
            assert response.provider == "openai"
            assert response.model == "gpt-4"
            assert response.generation_id == "gen-001"
            assert "usage" in response.metadata
            assert response.metadata["usage"]["total_tokens"] == 150
            assert "latency_seconds" in response.metadata
            assert "iteration" in response.metadata
        
        client.close()
    
    def test_api_key_not_logged(self, openai_config, caplog):
        """Test that API key is never logged."""
        client = LLMClient(openai_config)
        
        # Force an error to see if key appears in logs
        with patch.object(client.client, 'post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": {"message": "test"}}
            mock_post.side_effect = httpx.HTTPStatusError(
                "401",
                request=Mock(),
                response=mock_response
            )
            
            request = GenerationRequest(prompt="test")
            
            try:
                client.generate(request)
            except RuntimeError:
                pass
        
        # Check that API key doesn't appear in any captured logs
        api_key = openai_config.api_key
        for record in caplog.records:
            assert api_key not in record.message
        
        client.close()


class TestLLMClientCleanup:
    """Test LLM client resource cleanup."""
    
    def test_context_manager_cleanup_on_success(self, openai_config):
        """Test that context manager cleans up httpx client on success."""
        with patch('httpx.Client') as mock_client_class:
            mock_instance = Mock()
            mock_client_class.return_value = mock_instance
            mock_instance.post.return_value = Mock(
                status_code=200,
                json=lambda: {
                    "choices": [{"message": {"content": "test"}}],
                    "usage": {}
                }
            )
            
            # Use context manager
            with LLMClient(openai_config) as client:
                request = GenerationRequest(
                    prompt="test",
                    generation_id="test",
                    metadata={}
                )
                client.generate(request)
            
            # Verify close was called
            mock_instance.close.assert_called_once()
    
    def test_context_manager_cleanup_on_exception(self, openai_config):
        """Test that context manager cleans up even when exception occurs."""
        with patch('httpx.Client') as mock_client_class:
            mock_instance = Mock()
            mock_client_class.return_value = mock_instance
            mock_instance.post.side_effect = httpx.RequestError("Network error")
            
            # Use context manager - expect exception
            with pytest.raises(RuntimeError):
                with LLMClient(openai_config) as client:
                    request = GenerationRequest(
                        prompt="test",
                        generation_id="test",
                        metadata={}
                    )
                    client.generate(request)
            
            # Verify close was called despite exception
            mock_instance.close.assert_called_once()
    
    def test_manual_close(self, openai_config):
        """Test manual close() method."""
        with patch('httpx.Client') as mock_client_class:
            mock_instance = Mock()
            mock_client_class.return_value = mock_instance
            
            client = LLMClient(openai_config)
            client.close()
            
            # Verify close was called
            mock_instance.close.assert_called_once()
    
    def test_gemini_404_error_message(self, gemini_config):
        """Test Gemini-specific 404 error for unsupported model."""
        with patch('httpx.Client') as mock_client_class:
            mock_instance = Mock()
            mock_client_class.return_value = mock_instance
            
            # Mock Gemini 404 response for unsupported model
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.json.return_value = [{
                "error": {
                    "code": 404,
                    "message": "models/gemini-2.0-flash-exp is not found for API version v1main, or is not supported for generateContent.",
                    "status": "NOT_FOUND"
                }
            }]
            
            mock_instance.post.side_effect = httpx.HTTPStatusError(
                "404",
                request=Mock(),
                response=mock_response
            )
            
            client = LLMClient(gemini_config)
            
            with pytest.raises(RuntimeError) as exc_info:
                request = GenerationRequest(
                    prompt="test",
                    generation_id="test",
                    metadata={}
                )
                client.generate(request)
            
            # Verify error message mentions 404
            assert "404" in str(exc_info.value)
            
            # Clean up
            client.close()
