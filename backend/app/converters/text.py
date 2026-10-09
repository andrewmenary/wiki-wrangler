from pathlib import Path


SUPPORTED_EXTENSIONS = {".md", ".txt"}


def convert_to_markdown(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"No built-in converter for {extension or 'unknown file type'}")
    return content.decode("utf-8-sig")