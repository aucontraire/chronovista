"""
Factory definitions for takeout subscription models.

Provides factory-boy factories for creating test instances of takeout subscription models
with realistic and consistent test data.
"""

from __future__ import annotations

from typing import Any, List, cast

import factory

from chronovista.models.takeout.takeout_data import TakeoutSubscription


class TakeoutSubscriptionFactory(factory.Factory):
    """Factory for TakeoutSubscription models."""

    class Meta:
        model = TakeoutSubscription

    # Required fields
    channel_title = factory.LazyFunction(lambda: "Rick Astley")
    channel_url = factory.LazyFunction(
        lambda: "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
    )

    # Optional fields with realistic defaults
    channel_id = factory.LazyFunction(lambda: "UCuAXFkgsw1L7xaCfnd5JJOw")


class TakeoutSubscriptionMinimalFactory(factory.Factory):
    """Factory for TakeoutSubscription models with only required fields."""

    class Meta:
        model = TakeoutSubscription

    # Only required fields
    channel_title = factory.LazyFunction(lambda: "Python Tutorials")
    channel_url = factory.LazyFunction(
        lambda: "https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw"
    )

    # Set optional fields explicitly to None
    channel_id = None


class TakeoutSubscriptionTechFactory(factory.Factory):
    """Factory for TakeoutSubscription models with tech channels."""

    class Meta:
        model = TakeoutSubscription

    channel_title = factory.LazyFunction(lambda: "Google Developers")
    channel_url = factory.LazyFunction(
        lambda: "https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw"
    )
    channel_id = factory.LazyFunction(lambda: "UC_x5XG1OV2P6uZZ5FSM9Ttw")


class TakeoutSubscriptionMusicFactory(factory.Factory):
    """Factory for TakeoutSubscription models with music channels."""

    class Meta:
        model = TakeoutSubscription

    channel_title = factory.LazyFunction(lambda: "Rick Astley")
    channel_url = factory.LazyFunction(
        lambda: "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
    )
    channel_id = factory.LazyFunction(lambda: "UCuAXFkgsw1L7xaCfnd5JJOw")


class TakeoutSubscriptionCustomUrlFactory(factory.Factory):
    """Factory for TakeoutSubscription models with custom URL (no channel ID extractable)."""

    class Meta:
        model = TakeoutSubscription

    channel_title = factory.LazyFunction(lambda: "Custom Channel")
    channel_url = factory.LazyFunction(
        lambda: "https://www.youtube.com/c/CustomChannelName"
    )
    channel_id = None  # Cannot extract from custom URL


class TakeoutSubscriptionHandleFactory(factory.Factory):
    """Factory for TakeoutSubscription models with handle URL (no channel ID extractable)."""

    class Meta:
        model = TakeoutSubscription

    channel_title = factory.LazyFunction(lambda: "Handle Channel")
    channel_url = factory.LazyFunction(lambda: "https://www.youtube.com/@handlechannel")
    channel_id = None  # Cannot extract from handle URL


# Test data constants for validation testing
class TakeoutSubscriptionTestData:
    """Test data constants for takeout subscription models."""

    # Valid test data
    VALID_CHANNEL_TITLES = [
        "Rick Astley",
        "Google Developers",
        "Python Tutorials",
        "The Late Show with Stephen Colbert",
        "Marques Brownlee",
        "A",  # Min length
        "A" * 200,  # Long channel name
    ]

    VALID_CHANNEL_URLS = [
        "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "https://youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "http://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "https://www.youtube.com/c/CustomChannelName",  # Custom URL
        "https://www.youtube.com/@handlechannel",  # Handle URL
    ]

    VALID_CHANNEL_IDS = [
        "UCuAXFkgsw1L7xaCfnd5JJOw",  # Rick Astley (24 chars)
        "UC_x5XG1OV2P6uZZ5FSM9Ttw",  # Google Developers (24 chars)
        "UCMtFAi84ehTSYSE9XoHefig",  # Stephen Colbert (24 chars)
        "UCBJycsmduvYEL83R_U4JriQ",  # MKBHD (24 chars)
        None,  # Valid for custom URLs
    ]

    # Invalid test data
    INVALID_CHANNEL_TITLES = ["", "   ", "\t\n"]  # Empty, whitespace

    INVALID_CHANNEL_URLS = [
        "",
        "   ",
        "not-a-url",
        "https://example.com",
        "youtube.com/channel/test",  # Missing protocol
        "https://www.youtube.com/watch?v=test",  # Watch URL not channel URL
    ]

    INVALID_CHANNEL_IDS = [
        "",
        "   ",
        "\t\n",
        "a" * 25,  # Too long
        "UCshort",  # Too short
        "PLnotachannel123456789012",  # Wrong prefix
        "notachannel",  # No UC prefix
    ]


# Convenience factory functions
def create_takeout_subscription(**kwargs: Any) -> TakeoutSubscription:
    """Create a TakeoutSubscription with optional overrides."""
    return cast(TakeoutSubscription, TakeoutSubscriptionFactory.build(**kwargs))


def create_minimal_takeout_subscription(**kwargs: Any) -> TakeoutSubscription:
    """Create a minimal TakeoutSubscription with only required fields."""
    return cast(TakeoutSubscription, TakeoutSubscriptionMinimalFactory.build(**kwargs))


def create_tech_takeout_subscription(**kwargs: Any) -> TakeoutSubscription:
    """Create a TakeoutSubscription with tech channel."""
    return cast(TakeoutSubscription, TakeoutSubscriptionTechFactory.build(**kwargs))


def create_music_takeout_subscription(**kwargs: Any) -> TakeoutSubscription:
    """Create a TakeoutSubscription with music channel."""
    return cast(TakeoutSubscription, TakeoutSubscriptionMusicFactory.build(**kwargs))


def create_custom_url_takeout_subscription(**kwargs: Any) -> TakeoutSubscription:
    """Create a TakeoutSubscription with custom URL."""
    return cast(
        TakeoutSubscription, TakeoutSubscriptionCustomUrlFactory.build(**kwargs)
    )


def create_handle_takeout_subscription(**kwargs: Any) -> TakeoutSubscription:
    """Create a TakeoutSubscription with handle URL."""
    return cast(TakeoutSubscription, TakeoutSubscriptionHandleFactory.build(**kwargs))


def create_batch_takeout_subscriptions(count: int = 5) -> List[TakeoutSubscription]:
    """Create a batch of TakeoutSubscription instances for testing."""
    subscriptions = []
    base_channels = [
        ("Rick Astley", "UCuAXFkgsw1L7xaCfnd5JJOw"),
        ("Google Developers", "UC_x5XG1OV2P6uZZ5FSM9Ttw"),
        ("The Late Show", "UCMtFAi84ehTSYSE9XoHefig"),
        ("Marques Brownlee", "UCBJycsmduvYEL83R_U4JriQ"),
        ("Tech Channel", "UCTestChannel12345678901"),
    ]

    for i in range(count):
        channel_title, channel_id_base = base_channels[i % len(base_channels)]
        channel_id: str | None = channel_id_base

        # Mix different URL types
        if i % 3 == 0:
            # Regular channel URL
            channel_url = f"https://www.youtube.com/channel/{channel_id}"
        elif i % 3 == 1:
            # Custom URL (no extractable channel ID)
            channel_url = f"https://www.youtube.com/c/{channel_title.replace(' ', '')}"
            channel_id = None
        else:
            # Handle URL (no extractable channel ID)
            channel_url = (
                f"https://www.youtube.com/@{channel_title.lower().replace(' ', '')}"
            )
            channel_id = None

        subscription = TakeoutSubscriptionFactory.build(
            channel_title=channel_title,
            channel_url=channel_url,
            channel_id=channel_id,
        )
        subscriptions.append(subscription)

    return subscriptions
