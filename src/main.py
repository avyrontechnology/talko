from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from src.components.health.state import health_state
from src.components.security.robots import RobotsController
from src.config.swagger import SwaggerConfig
from src.core.container import Container
from src.core.environment import ENV
from src.middlewares import allowed_middlewares
from src.routes import Router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    await container.init_resources()

    # Singletons reset karo taaki naya instance bane with initialized redis_pool
    container.cache_helper.reset()
    container.call_redis_helper.reset()
    container.inbound_call_event_broker.reset()

    # redis_pool is an async Resource — providers.Singleton downstream of it
    # resolve to a coroutine, so the provider call itself must be awaited.
    # Must go through the container INSTANCE (not a bare
    # Container.inbound_call_event_broker() class-level call) so this is the
    # same singleton the websocket route resolves via Depends(Provide[...]) —
    # see InboundCallEventBroker's docstring for what a mismatch there broke.
    inbound_call_event_broker = await container.inbound_call_event_broker()
    await inbound_call_event_broker.start()

    # # Warm up singletons AFTER redis is ready
    # cache = await container.cache_helper()
    # print("CACHE HELPER REDIS:", cache.redis)  # ← yeh print karo
    # print("CACHE HELPER REDIS ID:", id(cache.redis))
    # await container.call_redis_helper()

    try:
        doc_db_manager = container.db()
        doc_db_manager._initialize_client()
        result = await doc_db_manager._client.admin.command(
            "ping", serverSelectionTimeoutMS=3000
        )
        if result.get("ok") == 1.0:
            health_state["mongodb"] = {"status": "ok"}
        else:
            health_state["mongodb"] = {"status": "error", "error": "Unexpected ping response"}
    except Exception as e:
        health_state["mongodb"] = {"status": "unreachable", "error": str(e)}

    health_state["app"] = {"status": "ok"}

    yield

    # SHUTDOWN
    await inbound_call_event_broker.stop()

    try:
        redis_pool = container.redis_pool()
        await redis_pool.aclose()
    except Exception:
        pass

    try:
        await container.shutdown_resources()
        doc_db_manager = container.db()
        await doc_db_manager.close()
        health_state["mongodb"] = {"status": "closed"}
    except Exception:
        pass

    health_state["app"] = {"status": "stopped"}


# 1. Initialize Container
container = Container()
container.check_dependencies()

container.wire(modules=["src.components.health.controllers"])

# 2. Initialize FastAPI
app = FastAPI(
    title=ENV.SERVICE_NAME,
    container=container,
    middleware=allowed_middlewares,
    lifespan=lifespan,
)

# 3. Setup Routes
holler_service = APIRouter(prefix="/holler-service/v1")
Router.register_all_routes(holler_service)
app.include_router(holler_service)

# 4. Apply Swagger configuration
SwaggerConfig.get_swagger_config(app)

# 5. Add robots.txt router
app.include_router(RobotsController.robot_router)
