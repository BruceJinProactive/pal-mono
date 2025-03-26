# Matches if the same word is repeated 20 or more times consecutively.
import re

REPEATED_WORD_PATTERN = re.compile(r"\b(\w+)(?:\s+\1){19,}\b", re.IGNORECASE)
