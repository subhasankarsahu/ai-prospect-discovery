"""Platform sources registration package."""

from app.platforms.base import PlatformSource
from app.platforms.facebook import FacebookPlatform
from app.platforms.instagram import InstagramPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.threads import ThreadsPlatform
from app.platforms.x import XPlatform
from app.platforms.youtube import YouTubePlatform


def get_all_platform_sources() -> list[PlatformSource]:
    """Return initialized instances of all supported platform discovery sources."""
    return [
        LinkedInPlatform(),
        XPlatform(),
        YouTubePlatform(),
        InstagramPlatform(),
        ThreadsPlatform(),
        FacebookPlatform(),
    ]
