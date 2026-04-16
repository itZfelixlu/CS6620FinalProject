"""Ensure Lambda assets are ready before CDK tests."""

from stacks.keyword_tags_sync import sync_keyword_tags


def pytest_configure() -> None:
    sync_keyword_tags()
