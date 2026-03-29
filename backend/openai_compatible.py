import json
import urllib.request
import os


class OpenAICompatibleBackend:
    def __init__(
        self,
        base_url="https://api.openai.com/v1",
        api_key=None,
        model="gpt-3.5-turbo",
        max_tokens=1024,
        stream=False,
        extra_headers=None
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.max_tokens = max_tokens
        self.stream = stream
        self.extra_headers = extra_headers or {}

    def complete(self, messages):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            **self.extra_headers
        }
        body = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "stream": False
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Backend call failed: {e}")

    def name(self):
        return f"openai_compatible:{self.model}@{self.base_url}"


class OllamaBackend(OpenAICompatibleBackend):
    def __init__(self, model="llama3", host="http://localhost:11434", **kwargs):
        super().__init__(
            base_url=f"{host}/v1",
            api_key="ollama",
            model=model,
            **kwargs
        )

    def name(self):
        return f"ollama:{self.model}"
