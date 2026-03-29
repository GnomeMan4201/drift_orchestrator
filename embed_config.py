import os
import json

DEFAULT_CONFIG = {
    "model_name": "all-MiniLM-L6-v2",
    "cache_enabled": True,
    "cache_backend": "sqlite",
    "cache_max_entries": 10000,
    "fallback_to_stub": True,
    "normalize": True,
    "device": "cpu",
}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "embed_config.json")


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                user = json.load(f)
            cfg = {**DEFAULT_CONFIG, **user}
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(updates):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    cfg = load_config()
    cfg.update(updates)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def show_config():
    cfg = load_config()
    print("\n  [EMBED CONFIG]")
    for k, v in cfg.items():
        print(f"  {k:<24} : {v}")
    print()
    return cfg
