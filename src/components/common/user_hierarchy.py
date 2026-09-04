from typing import Any

from src.grpc_client.client_services.auth_service_client import AuthServiceClient
from src.loggers.holler_service_logger import HollerServiceLogger


class UserHierarchy:
    """
    A service class responsible for fetching and validating user/agent hierarchy data
    from the authentication gRPC service.

    This class interacts with the AuthService gRPC client to:
    - Retrieve direct child users under a given user.
    - Retrieve complete hierarchical data (children and grandchildren).
    - Apply optional filtering on agent IDs provided in the request.
    """

    def __init__(self, grpc_client: AuthServiceClient, logger: HollerServiceLogger):
        """
        Initialize UserHierarchy with required dependencies.

        Args:
            grpc_client (AuthServiceClient): The gRPC client used to communicate with
                the authentication service and fetch hierarchy details.
            logger (HollerServiceLogger): Logger instance for logging hierarchy operations.
        """
        self.grpc_client = grpc_client
        self.logger = logger

    async def get_user_hierarchy_data(
        self, request_data: Any, current_user_id: int
    ) -> list[int]:
        """
        Fetch and validate the full agent hierarchy under the given user.

        The method performs the following:
        1. Retrieves all direct children of the given user.
        2. Fetches complete hierarchical details for those children (nested children).
        3. Aggregates a unique set of agent IDs including:
           - The current user
           - Direct children
           - Nested descendants
        4. Optionally filters the result if `request_data` includes a list of agent IDs.
           Only agents present in the hierarchy will be retained.

        Args:
            request_data (Any): Input data object that may contain a field `agents`
                (list of agent IDs to filter).
            current_user_id (int): The ID of the current user whose hierarchy is being fetched.

        Returns:
            list[int]: A list of unique agent IDs belonging to the user hierarchy.
                       Returns an empty list if no valid agents match the filter.
        """
        filter_agent_ids = (
            request_data.agents
            if request_data and hasattr(request_data, "agents")
            else []
        )

        self.logger.info(
            "Fetching user hierarchy for user_id={}, filter_agents={}".format(
                current_user_id, filter_agent_ids
            )
        )

        # Get direct children and their hierarchies
        user_list = await self.grpc_client.get_user_child_details(current_user_id)
        child_hierarchies = await self.grpc_client.get_user_child_hierarchy(user_list)

        self.logger.debug("Child hierarchies: {}".format(child_hierarchies))
        self.logger.debug("Direct children: {}".format(user_list))

        # Collect all unique agent IDs (self + children + grandchildren)
        agent_ids = {
            uid
            for agent_id in user_list
            for uid in [
                agent_id,
                *child_hierarchies.get(agent_id, {}).get("child_ids", []),
            ]
            if uid
        }
        agent_ids.add(current_user_id)  # include current user

        self.logger.info("User hierarchy (before filter): {}".format(agent_ids))

        # Apply filtering if specific agent_ids are requested
        if filter_agent_ids:
            valid_agent_ids = [aid for aid in filter_agent_ids if aid in agent_ids]
            if not valid_agent_ids:
                return []
            agent_ids = valid_agent_ids
        else:
            agent_ids = list(agent_ids)

        self.logger.info("User hierarchy (final): {}".format(agent_ids))
        return agent_ids
