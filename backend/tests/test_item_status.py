import pytest

from app.domain.items import ItemStatus, can_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ItemStatus.INBOX, ItemStatus.DRAFT),
        (ItemStatus.INBOX, ItemStatus.ERROR),
        (ItemStatus.REVIEW, ItemStatus.APPROVED),
        (ItemStatus.APPROVED, ItemStatus.PUBLISHED),
        (ItemStatus.ERROR, ItemStatus.DRAFT),
    ],
)
def test_allowed_item_transitions(current: ItemStatus, target: ItemStatus) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ItemStatus.INBOX, ItemStatus.PUBLISHED),
        (ItemStatus.PUBLISHED, ItemStatus.REVIEW),
        (ItemStatus.ARCHIVED, ItemStatus.DRAFT),
    ],
)
def test_invalid_item_transitions_are_rejected(current: ItemStatus, target: ItemStatus) -> None:
    assert not can_transition(current, target)