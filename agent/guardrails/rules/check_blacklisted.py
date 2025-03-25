import re

from utils.log import logger

# Expanded restricted words/phrases list
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


def check_blacklisted(prompt: str) -> bool:
    """
    Rule 2: Checks for presence of blacklisted words/phrases.
    - Converts prompt to lowercase for case-insensitive comparison.
    """
    prompt_lower = prompt.lower()
    styled_dan_pattern = r"\bd(?:[^\w\s]+)a(?:[^\w\s]+)n\b"
    if re.search(styled_dan_pattern, prompt_lower):
        """Uses a generalized regex to detect styled variants of dan. This regex matches the letter d, followed by one or more non-alphanumeric/non-whitespace (special/unicode) characters, then a, then again one or more special characters, then n.
        it should catch styled variants like "DAN", "d-a-n", "d🔥A🔥n","""
        logger.info("Blacklisted styled DAN pattern found in prompt")
        return False
    words = set(prompt_lower.split())
    blacklist_set = set(BLACKLIST)

    if words.intersection(blacklist_set):
        logger.info("Blacklisted word found in prompt")
        return False
    return True
