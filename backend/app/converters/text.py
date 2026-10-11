import csv
import io
from io import BytesIO
from pathlib import Path

from markitdown import MarkItDown

SUPPORTED_EXTENSIONS = {".csv", ".md", ".txt"}
MARKITDOWN_EXTENSIONS = {".docx", ".pdf", ".pptx", ".xlsx"}


def _csv_to_markdown(content: bytes) -> str:
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="strict"))))
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    normalized = [row + [""] * (column_count - len(row)) for row in rows]

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()

    header = "| " + " | ".join(cell(value) for value in normalized[0]) + " |"
    separator = "| " + " | ".join("---" for _ in range(column_count)) + " |"
    body = ["| " + " | ".join(cell(value) for value in row) + " |" for row in normalized[1:]]
    return "\n".join([header, separator, *body])


def convert_to_markdown(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        if extension not in MARKITDOWN_EXTENSIONS:
            raise ValueError(f"No converter for {extension or 'unknown file type'}")
        result = MarkItDown().convert_stream(BytesIO(content), file_extension=extension)
        return result.text_content
    if extension == ".csv":
        return _csv_to_markdown(content)
    return content.decode("utf-8-sig")