"""Free text from the inputs (names, descriptions, memos) is data, never an instruction."""
import json

from app.domain.refs import Model


class Quarantined(Model):
    """Text that business logic must not interpret. Scanners may read `.text`; everything else shows `quoted()`."""

    text: str

    def quoted(self) -> str:
        return json.dumps(self.text, ensure_ascii=False)

    def __str__(self) -> str:
        return f"<quarantined text, {len(self.text)} characters>"
