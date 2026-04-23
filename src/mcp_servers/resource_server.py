"""MCP resource management server."""

import logging
from typing import Any, Dict

from .base_server import MCPServer, Tool

logger = logging.getLogger(__name__)


class ResourceServer(MCPServer):
    """MCP server for managing and accessing resources.

    Exposes tools for:
    - Listing available resources
    - Accessing resource details
    - Managing resource permissions
    """

    def __init__(self, session_handler: Any):
        """Initialize resource server.

        Args:
            session_handler: SessionHandler instance
        """
        super().__init__("resource_server", session_handler)

        # Register tools
        self.register_tool(
            Tool(
                name="list_resources",
                description="List available resources for the current user",
                params_schema={
                    "type": "object",
                    "properties": {
                        "resource_type": {
                            "type": "string",
                            "description": "Filter by resource type (optional)",
                        }
                    },
                    "required": [],
                },
                required_scopes=["mcp:resources:read"],
                handler=self._list_resources,
            )
        )

        self.register_tool(
            Tool(
                name="get_resource",
                description="Get details about a specific resource",
                params_schema={
                    "type": "object",
                    "properties": {
                        "resource_id": {
                            "type": "string",
                            "description": "Resource ID",
                        }
                    },
                    "required": ["resource_id"],
                },
                required_scopes=["mcp:resources:read"],
                handler=self._get_resource,
            )
        )

        self.register_tool(
            Tool(
                name="create_resource",
                description="Create a new resource",
                params_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Resource name",
                        },
                        "resource_type": {
                            "type": "string",
                            "description": "Type of resource (e.g., 'document', 'dataset')",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Additional metadata",
                        },
                    },
                    "required": ["name", "resource_type"],
                },
                required_scopes=["mcp:resources:create"],
                handler=self._create_resource,
            )
        )

    async def _list_resources(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """List available resources.

        Args:
            params: Parameters with optional resource_type filter
            context: Execution context with session

        Returns:
            List of resources
        """
        session = context.get("session", {})
        resource_type = params.get("resource_type")

        logger.info(
            f"📚 Listing resources for user: {session.get('user_id')}, type: {resource_type}"
        )

        # Simulate resource listing
        all_resources = [
            {
                "id": "resource-1",
                "name": "Agent Configuration",
                "type": "config",
                "owner": session.get("user_id"),
                "created_at": 1708708800,
            },
            {
                "id": "resource-2",
                "name": "Session Data",
                "type": "data",
                "owner": session.get("user_id"),
                "created_at": 1708795200,
            },
            {
                "id": "resource-3",
                "name": "Identity Profile",
                "type": "profile",
                "owner": session.get("user_id"),
                "created_at": 1708881600,
            },
        ]

        # Filter by type if specified
        if resource_type:
            resources = [r for r in all_resources if r["type"] == resource_type]
        else:
            resources = all_resources

        return {
            "total": len(resources),
            "resources": resources,
        }

    async def _get_resource(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get resource details.

        Args:
            params: Parameters with resource_id
            context: Execution context with session

        Returns:
            Resource details
        """
        resource_id = params.get("resource_id")
        session = context.get("session", {})

        logger.info(f"📄 Getting resource: {resource_id}")

        # Simulate resource retrieval
        resources = {
            "resource-1": {
                "id": "resource-1",
                "name": "Agent Configuration",
                "type": "config",
                "owner": session.get("user_id"),
                "created_at": 1708708800,
                "content": {"agents": ["default", "auth", "identity"]},
            },
            "resource-2": {
                "id": "resource-2",
                "name": "Session Data",
                "type": "data",
                "owner": session.get("user_id"),
                "created_at": 1708795200,
                "content": {"sessions": []},
            },
            "resource-3": {
                "id": "resource-3",
                "name": "Identity Profile",
                "type": "profile",
                "owner": session.get("user_id"),
                "created_at": 1708881600,
                "content": {"email": session.get("email")},
            },
        }

        if resource_id not in resources:
            raise ValueError(f"Resource {resource_id} not found")

        resource = resources[resource_id]

        # Check ownership
        if resource["owner"] != session.get("user_id"):
            raise ValueError(f"Access denied to resource {resource_id}")

        return resource

    async def _create_resource(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new resource.

        Args:
            params: Parameters with name, type, and metadata
            context: Execution context with session

        Returns:
            Created resource details
        """
        name = params.get("name")
        resource_type = params.get("resource_type")
        metadata = params.get("metadata", {})
        session = context.get("session", {})

        logger.info(f"✨ Creating resource: {name} (type: {resource_type})")

        import time
        import uuid

        resource_id = str(uuid.uuid4())

        return {
            "id": resource_id,
            "name": name,
            "type": resource_type,
            "owner": session.get("user_id"),
            "created_at": int(time.time()),
            "metadata": metadata,
            "status": "created",
        }
