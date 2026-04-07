from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from orchestrator.contracts import ModelRole


@dataclass
class ModelEntry:
    name: str
    role: ModelRole
    temperature: float = 0.2
    max_tokens: int = 4096
    endpoint: str = "http://localhost:11434"
    priority: int = 0
    notes: str = ""

    def ollama_options(self) -> dict:
        return {"temperature": self.temperature, "num_predict": self.max_tokens}


_DEFAULT_MODELS: list[ModelEntry] = [
    ModelEntry(name="phi3:latest", role=ModelRole.ROUTER, temperature=0.05, max_tokens=512, priority=0, notes="Primary router."),
    ModelEntry(name="llama3.1:latest", role=ModelRole.ROUTER, temperature=0.05, max_tokens=512, priority=1, notes="Fallback router."),
    ModelEntry(name="mistral:latest", role=ModelRole.PLANNER, temperature=0.2, max_tokens=2048, priority=0, notes="Primary planner."),
    ModelEntry(name="llama3.1:latest", role=ModelRole.PLANNER, temperature=0.2, max_tokens=2048, priority=1, notes="Fallback planner."),
    ModelEntry(name="mistral:latest", role=ModelRole.SHAPER, temperature=0.3, max_tokens=1024, priority=0, notes="Direct-path shaper."),
    ModelEntry(name="mistral:latest", role=ModelRole.CODER, temperature=0.15, max_tokens=4096, priority=0, notes="Primary coder."),
    ModelEntry(name="llama3.1:latest", role=ModelRole.CODER, temperature=0.15, max_tokens=4096, priority=1, notes="Alternate coder 1."),
    ModelEntry(name="phi3:latest", role=ModelRole.CODER, temperature=0.15, max_tokens=4096, priority=2, notes="Alternate coder 2."),
    ModelEntry(name="llama3.1:latest", role=ModelRole.VERIFIER, temperature=0.1, max_tokens=1024, priority=0, notes="Verifier."),
]


class RegistryError(Exception):
    pass


class ModelRegistry:
    def __init__(self) -> None:
        self._registry: dict[ModelRole, list[ModelEntry]] = {}
        self._load_defaults()

    def _load_defaults(self) -> None:
        for entry in _DEFAULT_MODELS:
            self._registry.setdefault(entry.role, [])
            self._registry[entry.role].append(entry)
        for role in self._registry:
            self._registry[role].sort(key=lambda e: e.priority)

    def configure(self, entries: list[ModelEntry]) -> None:
        self._registry = {}
        for entry in entries:
            self._registry.setdefault(entry.role, [])
            self._registry[entry.role].append(entry)
        for role in self._registry:
            self._registry[role].sort(key=lambda e: e.priority)

    def add_model(self, entry: ModelEntry) -> None:
        self._registry.setdefault(entry.role, [])
        existing = {e.name for e in self._registry[entry.role]}
        if entry.name in existing:
            raise RegistryError("Model already registered: " + entry.name)
        self._registry[entry.role].append(entry)
        self._registry[entry.role].sort(key=lambda e: e.priority)

    def get_primary(self, role: ModelRole) -> ModelEntry:
        models = self._registry.get(role)
        if not models:
            raise RegistryError("No models registered for role: " + role.value)
        return models[0]

    def get_all(self, role: ModelRole) -> list[ModelEntry]:
        models = self._registry.get(role)
        if not models:
            raise RegistryError("No models registered for role: " + role.value)
        return list(models)

    def next_model(self, role: ModelRole, current_model_name: str) -> Optional[ModelEntry]:
        models = self._registry.get(role, [])
        names = [e.name for e in models]
        try:
            idx = names.index(current_model_name)
        except ValueError:
            return models[0] if models else None
        next_idx = idx + 1
        return models[next_idx] if next_idx < len(models) else None

    def has_alternate(self, role: ModelRole, current_model_name: str) -> bool:
        return self.next_model(role, current_model_name) is not None

    def model_count(self, role: ModelRole) -> int:
        return len(self._registry.get(role, []))

    def list_roles(self) -> list[ModelRole]:
        return list(self._registry.keys())

    def summary(self) -> dict[str, list[str]]:
        out = {}
        for role, entries in self._registry.items():
            out[role.value] = [
                e.name + " (priority=" + str(e.priority) + ", temp=" + str(e.temperature) + ")"
                for e in entries
            ]
        return out


registry = ModelRegistry()
