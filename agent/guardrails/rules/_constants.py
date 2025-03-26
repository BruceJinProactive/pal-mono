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
    "Caesar cipher",
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
    r"\b(def\s+\w+\s*\(|class\s+\w+\s*\:)",  # Python function or class definitions
    r"\b(function\s+\w+\s*\(|var\s+\w+\s*=|let\s+\w+\s*=|const\s+\w+\s*=)",  # JavaScript functions/variables
    r"\b(public|private|protected|static|void)\s+\w+\s*\(",  # Java/C# method declaration
    r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>",  # Malicious script tags
    r"<\s*img[^>]+\bon\w+\s*=",  # Malicious image tags with event handlers
    r"\b(eval\s*\(|exec\s*\(|document\.write\s*\(|innerHTML\s*=|onerror\s*=|onload\s*=)",  # JavaScript risky functions
    r"SELECT\s+\*?\s+FROM\s+\w+",  # SQL Injection
    r"INSERT\s+INTO\s+\w+\s+VALUES\s*\(",  # SQL Injection
    r"UPDATE\s+\w+\s+SET\s+",  # SQL Injection
    r"DELETE\s+FROM\s+\w+",  # SQL Injection
]
