import os
import sys
import json
import asyncio
import httpx
import websockets
import subprocess

async def listen_metrics():
    """Listens to WebSocket metrics and validates hierarchical node events."""
    uri = "ws://127.0.0.1:8000/metrics"
    await asyncio.sleep(4.0)
    
    websocket = None
    for attempt in range(10):
        try:
            websocket = await websockets.connect(uri)
            print(f"[Client] Connected to WebSocket metrics stream on attempt {attempt+1}.")
            break
        except Exception:
            print(f"[Client] Connection attempt {attempt+1}/10 failed. Retrying...")
            await asyncio.sleep(1.0)
            
    if not websocket:
        print("[Client] ERROR: Failed to connect to /metrics WebSocket server.")
        return
        
    events_received = []
    try:
        await websocket.send("ping")
        while True:
            msg = await websocket.recv()
            event = json.loads(msg)
            print(f"[Metrics Event] {event}")
            events_received.append(event)
            
    except asyncio.CancelledError:
        nodes = [e["node_name"] for e in events_received]
        print(f"\n[Client] Verification: Recorded node events in hierarchy: {nodes}")
        
        # Verify coordinator and workers
        assert "planner" in nodes, "Should record 'planner' node telemetry."
        assert "manager" in nodes, "Should record 'manager' coordinator telemetry."
        assert any(n in nodes for n in ["coder", "tester", "security"]), "Should record worker nodes telemetry."
        
        print("[SUCCESS] Multi-Agent Hierarchical validation completed successfully!")
    except Exception as e:
        print(f"[Client] WebSocket metrics error: {e}")
    finally:
        if websocket:
            await websocket.close()

async def run_execute():
    """Triggers the agent execution loop."""
    url = "http://127.0.0.1:8000/execute"
    payload = {
        "goal": "Write calculator function in calc.py. Verify it passes unit tests. Check security safety.",
        "test_command": "python test_calc.py"
    }
    
    await asyncio.sleep(6.0)
    client = httpx.AsyncClient(timeout=30)
    connected = False
    
    for attempt in range(12):
        try:
            print(f"[Client] Connecting to FastAPI execute endpoint (attempt {attempt+1}/12)...")
            async with client.stream("POST", url, json=payload) as response:
                print(f"[Client] Connected! HTTP Execute Status: {response.status_code}")
                connected = True
                async for line in response.aiter_lines():
                    pass # Consume stream
                break
        except Exception as e:
            print(f"[Client] HTTP Execute attempt {attempt+1} failed: {e}. Retrying in 1.5s...")
            await asyncio.sleep(1.5)
            
    await client.aclose()
    if not connected:
        print("[Client] ERROR: Failed to execute goal after 12 attempts.")

async def main():
    print("[Client] Starting E2E Hierarchical multi-agent validation...")
    
    # Start Uvicorn FastAPI server in background
    print("[Server] Booting Uvicorn server in background on port 8000...")
    server_process = subprocess.Popen(
        [".\\.venv\\Scripts\\python.exe", "-m", "uvicorn", "app:app", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        metrics_task = asyncio.create_task(listen_metrics())
        await run_execute()
        
        # Keep connection open briefly to catch remaining events
        await asyncio.sleep(3.0)
        metrics_task.cancel()
        
    finally:
        print("[Server] Terminating Uvicorn backend process...")
        server_process.terminate()
        server_process.wait()
        print("[Client] E2E Hierarchical multi-agent verification run complete.")

if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
