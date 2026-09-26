"""Smoke-test the YLD agent's outbound proxy from its internal network."""

from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def status(url):
    try:
        with urlopen(url, timeout=10) as response:
            return response.status
    except HTTPError as error:
        return error.code
    except URLError as error:
        if "Tunnel connection failed: 403" in str(error.reason):
            return 403
        raise


allowed = status("https://api.openai.com/v1/models")
denied = status("https://example.com/")
print(f"OpenAI endpoint: {allowed}; other domain: {denied}")
if allowed != 401 or denied != 403:
    raise SystemExit(1)
