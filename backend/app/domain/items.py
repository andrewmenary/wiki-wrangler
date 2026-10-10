from enum import StrEnum


class ItemStatus(StrEnum):
    INBOX = "inbox"
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    ERROR = "error"


ALLOWED_TRANSITIONS: dict[ItemStatus, frozenset[ItemStatus]] = {
    ItemStatus.INBOX: frozenset({ItemStatus.DRAFT, ItemStatus.ERROR, ItemStatus.ARCHIVED}),
    ItemStatus.DRAFT: frozenset({ItemStatus.REVIEW, ItemStatus.ARCHIVED}),
    ItemStatus.REVIEW: frozenset({ItemStatus.DRAFT, ItemStatus.APPROVED, ItemStatus.ARCHIVED}),
    ItemStatus.APPROVED: frozenset({ItemStatus.PUBLISHED, ItemStatus.REVIEW}),
    ItemStatus.PUBLISHED: frozenset({ItemStatus.ARCHIVED}),
    ItemStatus.ARCHIVED: frozenset(),
    ItemStatus.ERROR: frozenset({ItemStatus.DRAFT, ItemStatus.ARCHIVED}),
}


def can_transition(current: ItemStatus, target: ItemStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]