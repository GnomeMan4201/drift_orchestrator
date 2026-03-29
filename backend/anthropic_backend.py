import json
import os
import urllib.request


class AnthropicBackend:
    def __init__(
        self,
        api_key=None,
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system_prompt=None,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt

    def complete(self, messages):
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [m for m in messages if m["role"] != "system"]
        }
        if self.system_prompt:
            payload["system"] = self.system_prompt

        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data["content"][0]["text"]

    def name(self):
        return f"anthropic:{self.model}"
