

import structlog
from cancer_claw.config import settings
from cancer_claw.services.model_router.provider import ModelProvider, ProviderError
from cancer_claw.services.model_router import providers_store
from cancer_claw.services.model_router.schema import ChatRequest, ChatResponse, ProviderStatus

logger = structlog.get_logger()

from cancer_claw.services.platform.rate_limiter import llm_slot

class ModelRouter:


    def __init__(self):
        self._providers: list[ModelProvider] = []
        self._init_from_config()

    def _init_from_config(self):

        items = providers_store.list_providers_sync()
        source = "providers_yaml"
        if not items:


            items = [
                {
                    "id": pc.id,
                    "name": pc.name,
                    "base_url": pc.base_url,
                    "api_key": pc.api_key,
                    "models": [{"id": m.id, "role": m.role} for m in pc.models],
                    "enabled": pc.enabled,
                    "priority": pc.priority,
                }
                for pc in settings.providers
            ]
            source = "config_yaml_fallback"

        for it in items:
            if not it.get("enabled", True):
                continue
            provider = ModelProvider(
                provider_id=it["id"],
                name=it.get("name", ""),
                base_url=it.get("base_url", ""),
                api_key=it.get("api_key", ""),
                models=list(it.get("models") or []),
                enabled=bool(it.get("enabled", True)),
                priority=int(it.get("priority", 0) or 0),
            )
            self._providers.append(provider)

        self._providers.sort(key=lambda p: p.priority)
        logger.info(
            "model_router_initialized",
            providers=[p.id for p in self._providers],
            source=source,
        )

    def add_provider(self, provider_id: str, name: str, base_url: str, api_key: str,
                     models: list[dict], enabled: bool = True, priority: int = 0):

        provider = ModelProvider(
            provider_id=provider_id,
            name=name,
            base_url=base_url,
            api_key=api_key,
            models=models,
            enabled=enabled,
            priority=priority,
        )
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority)

    def remove_provider(self, provider_id: str):

        self._providers = [p for p in self._providers if p.id != provider_id]

    def _select_providers(
        self, task_type: str, *, requires_vision: bool = False,
    ) -> list[ModelProvider]:

        if requires_vision:
            vision_candidates = [
                p for p in self._providers if p.enabled and p.has_vision_model()
            ]
            if vision_candidates:


                fallback = [
                    p for p in self._providers
                    if p.enabled and p.get_model_for_role(task_type)
                    and p not in vision_candidates
                ]
                return vision_candidates + fallback




        candidates = []
        for p in self._providers:
            if not p.enabled:
                continue
            if p.get_model_for_role(task_type):
                candidates.append(p)


        if not candidates:
            candidates = [p for p in self._providers if p.enabled]
        return candidates

    async def chat(self, request: ChatRequest) -> ChatResponse:

        if not self._providers:
            raise RuntimeError("没有配置任何模型供应商，请在 config.yaml 或管理界面中添加")

        candidates = self._select_providers(
            request.task_type, requires_vision=request.requires_vision,
        )
        if not candidates:
            raise RuntimeError(f"没有可用的模型供应商处理 task_type={request.task_type}")





        provider_key = candidates[0].id if candidates else "default"
        async with llm_slot(provider_key):
            return await self._chat_candidates(request, candidates)

    async def _chat_candidates(
        self, request: ChatRequest, candidates: list[ModelProvider]
    ) -> ChatResponse:

        last_error = None
        for provider in candidates:
            try:
                response = await provider.chat(request)
                logger.info("model_call_success",
                           provider=provider.id,
                           model=response.model,
                           tokens=response.usage.get("total_tokens", 0))
                return response
            except ProviderError as e:
                last_error = e
                logger.warning("provider_failed_trying_next",
                              provider=provider.id,
                              error=str(e))
                continue


        raise RuntimeError(f"所有供应商均调用失败，最后错误: {last_error}")

    async def chat_simple(self, messages: list[dict], task_type: str = "general",
                          tools: list[dict] | None = None) -> ChatResponse:

        request = ChatRequest(messages=messages, tools=tools, task_type=task_type)
        return await self.chat(request)

    def get_all_status(self) -> list[ProviderStatus]:

        return [p.get_status() for p in self._providers]

    def get_provider(self, provider_id: str) -> ModelProvider | None:

        for p in self._providers:
            if p.id == provider_id:
                return p
        return None

_router: ModelRouter | None = None

def get_router() -> ModelRouter:

    global _router
    if _router is None:
        _router = ModelRouter()
    return _router

def reset_router():

    global _router
    _router = None
