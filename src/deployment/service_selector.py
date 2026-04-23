"""Service selector for Bedrock AgentCore.

Routes to the correct service based on AGENTCORE_SERVICE environment variable.
"""

import os
import sys

def main():
    """Select and run the appropriate service."""
    SERVICE = os.getenv("AGENTCORE_SERVICE", "identity").lower()
    
    if SERVICE == "identity":
        from src.deployment.agentcore_entrypoint import main
        main()
    
    elif SERVICE == "runtime":
        import uvicorn
        from src.deployment.runtime_service import BedrockAgentCoreRuntime
        from fastapi import FastAPI

        app = FastAPI(title="Bedrock AgentCore Runtime")
        runtime = BedrockAgentCoreRuntime()

        @app.get("/health")
        async def health():
            return await runtime.health_check()

        @app.post("/agents/{agent_id}/invoke")
        async def invoke(agent_id: str, request: dict):
            return await runtime.invoke_agent(
                agent_id=request.get("agent_id"),
                session_id=request.get("session_id"),
                input_text=request.get("input_text"),
            )

        @app.get("/agents")
        async def list_agents():
            return await runtime.list_agents()

        port = int(os.getenv("PORT", "8001"))
        uvicorn.run(app, host="0.0.0.0", port=port)

    elif SERVICE == "gateway":
        import uvicorn
        from src.deployment.gateway_service import app

        port = int(os.getenv("PORT", "8080"))
        uvicorn.run(app, host="0.0.0.0", port=port)
    
    else:
        print(f"ERROR: Unknown service: {SERVICE}")
        print("Valid options: identity, runtime, gateway")
        sys.exit(1)


if __name__ == "__main__":
    main()
