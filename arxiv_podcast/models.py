"""Shared data structures passed between pipeline stages."""

from dataclasses import dataclass, field


@dataclass
class Paper:
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    link: str
    published: str  # ISO 8601 string, as returned by arXiv

    def authors_str(self, max_authors: int = 4) -> str:
        if len(self.authors) <= max_authors:
            return ", ".join(self.authors)
        return ", ".join(self.authors[:max_authors]) + " et al."


@dataclass
class DialogueLine:
    speaker: str  # "HOST_A" or "HOST_B"
    text: str


@dataclass
class Episode:
    date: str  # YYYY-MM-DD
    deep_dive: list[Paper]
    roundup: list[Paper]
    lines: list[DialogueLine] = field(default_factory=list)
    audio_path: "str | None" = None
    duration_seconds: "float | None" = None

    @property
    def all_papers(self) -> list[Paper]:
        return self.deep_dive + self.roundup
