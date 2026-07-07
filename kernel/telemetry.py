import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

def log_telemetry(
    node_name: str,
    tokens_used: int,
    success: bool,
    error_msg: Optional[str],
    workspace_path: str,
    config: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Records a telemetry event containing node performance metrics,
    appends it to a persistent local log file, and triggers any active
    WebSocket telemetry callback registered in the Graph config.
    """
    configurable = config.get("configurable", {}) if config else {}
    telemetry_callback = configurable.get("telemetry_callback")

    # Estimated model cost: $0.002 per 1,000 tokens on average
    cost = (tokens_used / 1000.0) * 0.002

    event = {
        "node_name": node_name,
        "timestamp": datetime.utcnow().isoformat(),
        "tokens_used": tokens_used,
        "cost": cost,
        "success_status": "success" if success else "failed",
        "error_log": error_msg or "",
        **kwargs
    }

    # Append to local jsonl file for persistence in the workspace
    log_file = os.path.join(workspace_path, "telemetry_logs.jsonl")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print(f"[Telemetry] Warning: Could not write to {log_file}: {e}")

    # Invoke WebSocket telemetry push if callback is present
    if telemetry_callback:
        try:
            telemetry_callback(event)
        except Exception as e:
            print(f"[Telemetry] Callback propagation failed: {e}")

    return event
