import string

BLACKLIST = [
    # Jailbreak & Bypass Terms
    "jailbreak",
    "bypass",
    "ignore previous",
    "unrestricted",
    "override restrictions",
    "disable safety",
    "remove filter",
    "system override",
    "no restrictions",
    "admin mode",
    # Known AI Jailbreak Attempts
    "do anything now",
    "do anythin' now",
    "dan",
    "chatgpt jailbreak",
    "ignore safety protocols",
    "act as unrestricted ai",
    "completely ignore",
    "you are no longer chatgpt",
    "simulate unfiltered ai",
    "enable dev mode",
    "override system policy",
    "without ethical constraints",
    "ignore ethical restrictions",
    "act without limitations",
    "ignore previous instructions",
    "ignore all the instructions",
    "forget all rules",
    "disregard prior commands",
    "override all system filters",
    # Hacking & Exploits
    "hack",
    "exploit",
    "bruteforce",
    "backdoor",
    "reverse shell",
    "privilege escalation",
    "crack password",
    "credential stuffing",
    "zero-day",
    "keylogger",
    "malware",
    # Illegal Activities
    "launder",
    "fraud",
    "phishing",
    "scam",
    "counterfeit",
    "dark web",
    "black market",
    "carding",
    "money laundering",
    "drug trafficking",
    "illegal weapons",
    # Violence & Harm
    "kill",
    "murder",
    "assassinate",
    "bomb",
    "terrorism",
    "violence",
    "self-harm",
    "suicide",
    "how to make a bomb",
    "weaponize",
    "mass attack",
    # Encoding & Obfuscation (often used to bypass filters)
    "base64",
    "base 64",
    "hexadecimal",
    "hexa",
    "octal",
    "binary",
    "ROT13",
    "caesar cipher",
    # Social Engineering & Deception
    "impersonate",
    "social engineering",
    "fake identity",
    "fraudulent",
    "spoofing",
    "bypass CAPTCHA",
    "disable logs",
    "evade detection",
    "steal credentials",
]
MAX_PROMPT_LENGTH = 100
REPEATED_WORD_PATTERN = r"\b(\w+)(?:\s+\1){19,}\b"
BANNED_CATEGORIES = ["Cf", "Cc", "Co", "Cn"]
ALLOWED_WHITE_SPACE = ["\n", " ", "\t", "\r"]  # Allow standard spaces
ALLOWED_PUNCTUATION = [
    "’",
    "‘",
    "“",
    "”",
    "–",
    "—",
    "−",
]
# Refined programming patterns to avoid false positives
CODE_PATTERNS = [
    # --- Python ---
    r"\b(def\s+\w+\s*\(|class\s+\w+\s*\:)",  # Python function or class definitions
    # --- JavaScript ---
    r"\b(function\s+\w+\s*\(|var\s+\w+\s*=|let\s+\w+\s*=|const\s+\w+\s*=)",  # JavaScript functions/variables
    r"\b(eval\s*\(|exec\s*\(|document\.write\s*\(|innerHTML\s*=|onerror\s*=|onload\s*=)",
    # --- Java / C# ---
    r"\b(public|private|protected|static|void)\s+\w+\s*\(",  # Java/C# method declarations
    # --- C / C++ ---
    r"\b(int|void|char|float|double)\s+\w+\s*\([^)]*\)\s*\{",  # C/C++ function definitions (rough heuristic)
    r"\bprintf\s*\(",  # C/C++ printing function
    r"\bscanf\s*\(",  # C/C++ scanning function
    r"^\s*#\s*(include|define|if|endif)",  # Preprocessor directives
    # --- Ruby ---
    r"\b(def\s+\w+\b)",  # Ruby method definitions (simple heuristic)
    # --- PHP ---
    r"<\?php",  # PHP opening tag
    # --- SQL Injection ---
    r"SELECT\s+\*?\s+FROM\s+\w+",  # Basic SELECT
    r"INSERT\s+INTO\s+\w+\s+VALUES\s*\(",  # INSERT
    r"UPDATE\s+\w+\s+SET\s+",  # UPDATE
    r"DELETE\s+FROM\s+\w+",  # DELETE
    # --- HTML / JavaScript Injection ---
    r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>",  # <script> tags
    r"<\s*img[^>]+\bon\w+\s*=",  # <img> tags with event handlers
    # --- Generic code patterns ---
    r"\b(main\s*\()",  # Main function (common in C/C++/Java)
    r";\s*$",  # Line ending with a semicolon (could be code; use with caution)
]
ALLOWED_CHARACTERS = set(
    string.ascii_letters + string.digits + string.punctuation + " "
)
PHONE_PATTERN = (
    r"(?<!\S)(?:\+?1[-.\s]*)?(?:\(\s*\d{3}\s*\)|\d{3})[-.\s]*\d{3}[-.\s]*\d{4}(?!\S)"
)
UNIT_LIST = (
    "inches|inch|in|meters|meter|m|cm|kilograms|kg|lbs|pounds|"
    "liters|litre|l|ounces|oz|gallons|gal|gallon|pints|pt|"
    "quarts|qt|milliliters|millilitre|ml|grams|gram|g|"
    "kilometers|kilometre|km|miles|mile|mi|yards|yard|yd|centimeters|cm|"
    "millimeters|millimetre|mm|millimetres|millimeter|"
    "feet|foot|ft|acres|acre|hectares|hectare|ha|"
)
# Remove anchors so that they match within a longer string:
UNITS_PATTERN = rf"\d+(?:\.\d+)?[-\s]*({UNIT_LIST})"

# Combine USA and Canadian postal codes without anchors:
POSTAL_CODE_PATTERN = r"(?:\d{5}(?:-\d{4})?|[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][-\s]?\d[ABCEGHJ-NPRSTV-Z]\d)"
DAN_PATTERN = r"\bd(?:[\W_]+)?a(?:[\W_]+)?n\b"
DELIM = r"[\s,;:\-\.]+"
BASE64 = (
    r"^(?=.{1,})(?:[A-Za-z0-9+/]{4})*"  # groups of 4 valid Base64 characters
    r"(?:[A-Za-z0-9+/]{2}==|"  # or 2 characters followed by '=='
    r"[A-Za-z0-9+/]{3}=)?$"
)
BINARY = rf"^(?:[01]+(?:{DELIM}[01]+)*)$"
DECIMAL = rf"(?:[+-]?\d+(?:{DELIM}\d+)*)"
HEX = rf"^(?:0x(?:{DELIM})*)?(?:[0-9A-Fa-f]{{20,}}|[0-9A-Fa-f]{{2}}(?:{DELIM}[0-9A-Fa-f]{{2}}){{9,}})$|(?:0[xX](?:{DELIM})*[0-9A-Fa-f]+(?:{DELIM}[0-9A-Fa-f]+)*)"
OCTAL = rf"^(?:[0-7]{{10,}}|[0-7](?:{DELIM}[0-7]){{9,}})$|(?:0[oO](?:{DELIM})*[0-7]+(?:{DELIM}[0-7]+)*)"
ASCII = (
    r"^(?:"  # start non-capturing group for the entire sequence
    r"(?:12[0-7]|1[01]\d|\d{1,2})"  # matches a number between 0 and 127:
    r"(?:[\s,;:\-\.]+|$)"  # each number is followed by a delimiter (or end-of-string)
    r")+$"
)
