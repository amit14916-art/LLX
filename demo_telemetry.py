import os
import sys
import json
import asyncio
import httpx
import websockets
import subprocess

async def listen_metrics():
    """Listens to WebSocket metrics and validates JSON structure."""
    uri = "ws://127.0.0.1:8000/metrics"
    await asyncio.sleep(2.0)
    
    websocket = None
    for attempt in range(5):
        try:
            websocket = await websockets.connect(uri)
            print(f"[Client] Connected to WebSocket metrics stream on attempt {attempt+1}.")
            break
        except Exception:
            print(f"[Client] Connection attempt {attempt+1}/5 failed. Retrying...")
            await asyncio.sleep(1.0)
            
    if not websocket:
        print("[Client] ERROR: Failed to connect to /metrics WebSocket server.")
        return
        
    events_received = []
    try:
        # Send dummy packet
        await websocket.send("ping")
        while True:
            msg = await websocket.recv()
            event = json.loads(msg)
            print(f"[Metrics Event] {event}")
            events_received.append(event)
            
            # Check keys
            assert "node_name" in event, "Event must contain 'node_name'"
            assert "timestamp" in event, "Event must contain 'timestamp'"
            assert "tokens_used" in event, "Event must contain 'tokens_used'"
            assert "cost" in event, "Event must contain 'cost'"
            assert "success_status" in event, "Event must contain 'success_status'"
            assert "error_log" in event, "Event must contain 'error_log'"
            
    except asyncio.CancelledError:
        # Check that we received events for planner, executor, and critic
        nodes = [e["node_name"] for e in events_received]
        print(f"\n[Client] Verification: Recorded node events: {nodes}")
        assert "planner" in nodes, "Should record 'planner' node telemetry."
        assert "executor" in nodes, "Should record 'executor' node telemetry."
        assert "critic" in nodes, "Should record 'critic' node telemetry."
        print("[SUCCESS] All telemetry event structures and properties validated!")
    except Exception as e:
        print(f"[Client] WebSocket metrics error: {e}")
    finally:
        if websocket:
            await websocket.close()

async def run_execute():
    """Triggers the agent execution loop, retrying connection until server is active."""
    url = "http://127.0.0.1:8000/execute"
    payload = {
        "goal": "Build an addition function in calc.py and verify it works.",
        "test_command": "python test_calc.py"
    }
    
    await asyncio.sleep(2.0)
    
    client = httpx.AsyncClient(timeout=30)
    connected = False
    
    # Try connecting to server up to 8 times
    for attempt in range(8):
        try:
            # Quick health check or get response
            print(f"[Client] Connecting to FastAPI execute endpoint (attempt {attempt+1}/8)...")
            async with client.stream("POST", url, json=payload) as response:
                print(f"[Client] Connected! HTTP Execute Status: {response.status_code}")
                connected = True
                async for line in response.aiter_lines():
                    pass # Just consume the stream
                break
        except Exception as e:
            print(f"[Client] HTTP Execute attempt {attempt+1} failed: {e}. Retrying in 1.5s...")
            await asyncio.sleep(1.5)
            
    await client.aclose()
    if not connected:
        print("[Client] ERROR: Failed to execute goal after 8 attempts.")

async def main():
    print("[Client] Starting E2E Telemetry pipeline validation...")
    
    # 1. Start Uvicorn FastAPI server in background
    print("[Server] Booting Uvicorn server in background on port 8000...")
    server_process = subprocess.Popen(
        [".\\.venv\\Scripts\\python.exe", "-m", "uvicorn", "app:app", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        # Run WebSocket telemetry logger and execution HTTP call concurrently
        metrics_task = asyncio.create_task(listen_metrics())
        await run_execute()
        
        # Keep connection open briefly to capture all events
        await asyncio.sleep(2.0)
        metrics_task.cancel()
        
    finally:
        # Clean up Uvicorn server process
        print("[Server] Terminating Uvicorn backend process...")
        server_process.terminate()
        server_process.wait()
        print("[Client] E2E Telemetry verification run complete.")

if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
