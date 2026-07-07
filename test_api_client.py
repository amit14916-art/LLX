import asyncio
import httpx
import json
# websockets was installed as a dependency of langgraph-sdk
import websockets

async def listen_logs():
    """Listens to real-time logs broadcast over the WebSocket."""
    uri = "ws://127.0.0.1:8000/ws/logs"
    await asyncio.sleep(1) # wait for HTTP request to initiate
    try:
        async with websockets.connect(uri) as websocket:
            print("[Client] Connected to WebSocket log stream.")
            # Send dummy packet to keep connection registry happy
            await websocket.send("ping")
            while True:
                log_msg = await websocket.recv()
                print(f"[WS Log Broadcast] {log_msg}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Client] WebSocket logger error: {e}")

async def trigger_execution():
    """Triggers the agent execution and listens to the Server-Sent Events (SSE) stream."""
    # Brief wait for Uvicorn server startup
    await asyncio.sleep(2)
    
    url = "http://127.0.0.1:8000/execute"
    payload = {
        "goal": "Build an addition function in calc.py and verify it works.",
        "test_command": "python test_calc.py"
    }
    
    print("[Client] Sending POST request to /execute to start agent...")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream("POST", url, json=payload) as response:
                print(f"[Client] SSE HTTP Status: {response.status_code}")
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        event_data = line[len("data: "):]
                        chunk = json.loads(event_data)
                        print(f"[Client] SSE State Event: {chunk}")
                        for node, data in chunk.items():
                            if "git_branch" in data and data["git_branch"]:
                                print(f"[Client VERIFICATION] Git branch set successfully: {data['git_branch']}")
                            if "current_lint_score" in data and data["current_lint_score"] is not None:
                                print(f"[Client VERIFICATION] Linter health score reported: {data['current_lint_score']}/10.00")
    except Exception as e:
        print(f"[Client] HTTP request error: {e}")

async def main():
    # Execute WebSocket subscriber and HTTP SSE executor concurrently
    # This proves that prints inside executor_agent successfully route to WebSocket listeners in parallel
    print("[Client] Initializing E2E API Verification Client...")
    
    # Run client steps
    listener_task = asyncio.create_task(listen_logs())
    await trigger_execution()
    
    # Clean up listener task after HTTP stream completes
    await asyncio.sleep(1)
    listener_task.cancel()
    print("[Client] Verification Client finished.")

if __name__ == "__main__":
    asyncio.run(main())
