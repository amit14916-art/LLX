from typing import Optional
from langchain_core.runnables import RunnableConfig

def log_agent(message: str, config: Optional[RunnableConfig] = None):
    """
    Utility to log message to console and forward it to a configured WebSocket/SSE
    callback if one is provided in the RunnableConfig.
    """
    print(message)
    if config:
        configurable = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {})
        if configurable:
            callback = configurable.get("log_callback")
            if callback and callable(callback):
                try:
                    callback(message)
                except Exception:
                    pass
