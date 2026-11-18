"""Plain text checks on one data line, shared by grounding and the contradiction checks."""
import re

DATE = re.compile(r"(?<![\d.])(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})(?![\d.])")
WORD = re.compile(r"[A-Za-z]{2,}")


def invalid_date(line: str, last_year: int) -> bool:
    """A date-shaped token that cannot be a date in this period: month or day out of range, or a year after it."""
    for a, b, c in DATE.findall(line):
        if len(a) != 4 and len(c) != 4:
            continue  # a two-digit year could be any century: code cannot prove that date wrong
        year, month, day = (int(a), int(b), int(c)) if len(a) == 4 else (int(c), int(b), int(a))
        if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= last_year):
            return True
    return False
