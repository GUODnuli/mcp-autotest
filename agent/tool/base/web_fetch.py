# -*- coding: utf-8 -*-
"""
Web fetch tool - HTTP GET requests for fetching web content.

Provides web fetching with:
- HTTP GET requests
- Response text extraction
- Status code and headers reporting
- Timeout handling
- Content truncation for large responses
"""

import json
from typing import Optional
from urllib.parse import urlparse

from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


def _success_response(data: dict) -> ToolResponse:
    """Create a success ToolResponse."""
    return ToolResponse(
        content=[TextBlock(type="text", text=json.dumps(data, ensure_ascii=False))]
    )


def _error_response(message: str, error_code: str = "FETCH_ERROR") -> ToolResponse:
    """Create an error ToolResponse."""
    return ToolResponse(
        content=[TextBlock(
            type="text",
            text=json.dumps({
                "status": "error",
                "error_code": error_code,
                "message": message
            }, ensure_ascii=False)
        )]
    )


def web_fetch(
    url: str,
    timeout: int = 30,
    max_length: int = 50000
) -> ToolResponse:
    """
    Fetch content from a URL via HTTP GET request.

    Performs an HTTP GET request and returns the response content.
    Suitable for fetching public web pages, APIs, and documentation.

    Args:
        url: The URL to fetch (must be http:// or https://)
        timeout: Request timeout in seconds (default 30, max 120)
        max_length: Maximum response length in characters (default 50000)

    Returns:
        ToolResponse containing:
        - status: "success" or "error"
        - url: The fetched URL
        - status_code: HTTP status code
        - content: Response text (truncated if needed)
        - content_length: Original content length
        - truncated: True if content was truncated
        - content_type: Response content-type header

    Example:
        web_fetch("https://api.example.com/data")
        web_fetch("https://docs.python.org/3/", timeout=60)

    Notes:
        - Only HTTP and HTTPS URLs are allowed
        - Follows redirects automatically
        - Binary responses are not supported (returns error)
        - Requires httpx library (included with agentscope)
    """
    if not HTTPX_AVAILABLE:
        return _error_response(
            "httpx library not available. Install with: pip install httpx",
            "DEPENDENCY_MISSING"
        )

    # Validate URL
    if not url:
        return _error_response("URL cannot be empty", "INVALID_URL")

    try:
        parsed = urlparse(url)
    except Exception as e:
        return _error_response(f"Invalid URL format: {e}", "INVALID_URL")

    # Validate scheme
    if parsed.scheme not in ("http", "https"):
        return _error_response(
            f"Invalid URL scheme: {parsed.scheme}. Only http:// and https:// are allowed.",
            "INVALID_SCHEME"
        )

    # Validate host
    if not parsed.netloc:
        return _error_response("URL must include a host", "INVALID_URL")

    # Block localhost/internal addresses for security (SSRF protection)
    host_lower = parsed.netloc.lower().split(":")[0]

    # Check blocked hostnames
    blocked_hosts = {
        "localhost", "127.0.0.1", "0.0.0.0", "::1",
        "metadata.google.internal",  # GCP metadata
        "instance-data",             # AWS metadata alias
    }
    if host_lower in blocked_hosts:
        return _error_response(
            "Cannot fetch from localhost or internal network addresses",
            "BLOCKED_HOST"
        )

    # Check private IP ranges (SSRF protection)
    private_prefixes = (
        "10.",           # Class A private
        "172.16.", "172.17.", "172.18.", "172.19.",  # Class B private
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        "192.168.",      # Class C private
        "169.254.",      # Link-local / AWS metadata
        "fe80:",         # IPv6 link-local
    )
    if host_lower.startswith(private_prefixes):
        return _error_response(
            "Cannot fetch from localhost or internal network addresses",
            "BLOCKED_HOST"
        )

    # Clamp timeout
    timeout = max(5, min(timeout, 120))
    max_length = max(1000, min(max_length, 100000))

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers={
                "User-Agent": "TestAgent/1.0 (https://github.com/testagent)"
            })

        content_type = response.headers.get("content-type", "")

        # Check for binary content
        if "image/" in content_type or "audio/" in content_type or "video/" in content_type:
            return _error_response(
                f"Cannot fetch binary content (content-type: {content_type})",
                "BINARY_CONTENT"
            )

        # Get text content
        try:
            content = response.text
        except Exception as e:
            return _error_response(
                f"Cannot decode response as text: {e}",
                "DECODE_ERROR"
            )

        original_length = len(content)
        truncated = False

        if len(content) > max_length:
            content = content[:max_length] + "\n\n... [content truncated]"
            truncated = True

        return _success_response({
            "status": "success",
            "url": str(response.url),  # Final URL after redirects
            "status_code": response.status_code,
            "content": content,
            "content_length": original_length,
            "truncated": truncated,
            "content_type": content_type,
            "headers": {
                "content-type": content_type,
                "content-length": response.headers.get("content-length"),
            }
        })

    except httpx.TimeoutException:
        return _error_response(
            f"Request timed out after {timeout} seconds",
            "TIMEOUT"
        )

    except httpx.ConnectError as e:
        return _error_response(
            f"Connection failed: {e}",
            "CONNECTION_ERROR"
        )

    except httpx.TooManyRedirects:
        return _error_response(
            "Too many redirects",
            "TOO_MANY_REDIRECTS"
        )

    except httpx.HTTPStatusError as e:
        return _error_response(
            f"HTTP error: {e.response.status_code}",
            "HTTP_ERROR"
        )

    except Exception as e:
        return _error_response(
            f"Fetch failed: {type(e).__name__}: {e}",
            "FETCH_ERROR"
        )
