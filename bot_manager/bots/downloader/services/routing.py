"""
Dynamic Routing Service

Читает конфигурацию провайдеров из Redis.
Позволяет менять порядок провайдеров без перезапуска бота.
"""
import json
import logging
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from .cache import get_redis

logger = logging.getLogger(__name__)

# Дефолтные chains (fallback если Redis недоступен или нет конфига)
DEFAULT_CHAINS = {
    "youtube_full": ["ytdlp", "pytubefix", "savenow"],
    "youtube_shorts": ["ytdlp", "pytubefix", "savenow"],
    "instagram_reel": ["rapidapi"],
    "instagram_post": ["rapidapi"],
    "instagram_story": ["rapidapi"],
    "instagram_carousel": ["rapidapi"],
    "tiktok": ["ytdlp", "rapidapi"],
    "pinterest": ["ytdlp", "rapidapi"],
}


@dataclass
class ProviderConfig:
    """Конфиг одного провайдера в chain"""
    name: str
    enabled: bool = True
    timeout_sec: int = 60     # Download timeout
    connect_sec: int = 5      # Connection/ping timeout (быстрая проверка)


@dataclass
class RoutingChain:
    """Chain провайдеров для источника"""
    source: str
    providers: List[ProviderConfig]
    is_override: bool = False
    override_expires_at: Optional[datetime] = None

    def get_enabled_providers(self) -> List[str]:
        """Получить список включённых провайдеров в порядке приоритета"""
        return [p.name for p in self.providers if p.enabled]

    def get_timeout(self, provider_name: str) -> int:
        """Получить download timeout для провайдера"""
        for p in self.providers:
            if p.name == provider_name:
                return p.timeout_sec
        return 60  # default

    def get_connect_timeout(self, provider_name: str) -> int:
        """Получить connection/ping timeout для провайдера"""
        for p in self.providers:
            if p.name == provider_name:
                return p.connect_sec
        return 5  # default


async def get_routing_chain(source: str) -> RoutingChain:
    """
    Получить chain провайдеров для источника.

    Приоритет:
    1. Override (если активен и не истёк)
    2. Сохранённый config в Redis
    3. Дефолтный chain

    Usage:
        chain = await get_routing_chain("youtube_full")
        providers = chain.get_enabled_providers()  # ["ytdlp", "pytubefix", "savenow"]
    """
    try:
        redis = await get_redis()

        # Сначала проверяем override
        override_json = await redis.get(f"routing_override:{source}")
        if override_json:
            override_data = json.loads(override_json)
            expires_at = datetime.fromisoformat(override_data["expires_at"])
            if expires_at > datetime.utcnow():
                logger.info(f"[ROUTING] Using override for {source}: {override_data['chain']}")
                return RoutingChain(
                    source=source,
                    providers=[ProviderConfig(name=p) for p in override_data["chain"]],
                    is_override=True,
                    override_expires_at=expires_at
                )

        # Читаем сохранённый config
        chain_json = await redis.get(f"routing:{source}")
        if chain_json:
            chain_data = json.loads(chain_json)
            providers = []
            for p in chain_data:
                if isinstance(p, dict):
                    providers.append(ProviderConfig(
                        name=p["name"],
                        enabled=p.get("enabled", True),
                        timeout_sec=p.get("timeout_sec", 60),
                        connect_sec=p.get("connect_sec", 5)
                    ))
                else:
                    providers.append(ProviderConfig(name=p))

            logger.debug(f"[ROUTING] Using saved config for {source}: {[p.name for p in providers]}")
            return RoutingChain(source=source, providers=providers)

    except Exception as e:
        logger.warning(f"[ROUTING] Redis error for {source}: {e}, using default")

    # Fallback на дефолт
    default_chain = DEFAULT_CHAINS.get(source, ["ytdlp"])
    logger.debug(f"[ROUTING] Using default for {source}: {default_chain}")
    return RoutingChain(
        source=source,
        providers=[ProviderConfig(name=p) for p in default_chain]
    )


def get_source_key(platform: str, bucket: Optional[str] = None) -> str:
    """
    Преобразует platform + bucket в routing source key.

    Examples:
        ("youtube", "full") -> "youtube_full"
        ("youtube", "shorts") -> "youtube_shorts"
        ("instagram", "reel") -> "instagram_reel"
        ("tiktok", None) -> "tiktok"
    """
    if platform == "youtube":
        if bucket in ("full", "long", "medium"):
            return "youtube_full"
        return "youtube_shorts"
    elif platform == "instagram":
        if bucket == "reel":
            return "instagram_reel"
        elif bucket == "story":
            return "instagram_story"
        elif bucket == "carousel":
            return "instagram_carousel"
        return "instagram_post"
    elif platform == "tiktok":
        return "tiktok"
    elif platform == "pinterest":
        return "pinterest"

    # Unknown platform - return as is
    return f"{platform}_{bucket}" if bucket else platform
