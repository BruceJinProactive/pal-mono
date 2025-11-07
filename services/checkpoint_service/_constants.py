"""Constants for checkpoint service."""

# OpenAI Configuration
OPENAI_MODEL = "gpt-4o"
OPENAI_MAX_TOKENS = 2000
OPENAI_RESPONSE_FORMAT = {"type": "json_object"}
OPENAI_IMAGE_DETAIL = "high"
MAX_CONCURRENT_OPENAI_REQUESTS = 10  # Number of concurrent image comparisons

# Prompt Templates
RULES_SECTION_TEMPLATE = """**Inspection Rules ({rules_count} total - Cleanliness & Safety Only):**
{rules_text}

"""

RULES_EXAMPLE_TEMPLATE = """
**EXAMPLE - If there are {rules_count} rules, your "rules" array should look like:**
[
  {{"rule_number": 1, "rule_text": "...", "status": "PASS", "details": "...", "location": "...", "safety_impact": "N/A"}},
  {{"rule_number": 2, "rule_text": "...", "status": "FAIL", "details": "...", "location": "...", "safety_impact": "..."}},
  ... (continue for all {rules_count} rules)
]
"""

CHECKPOINT_COMPARISON_SYSTEM_MESSAGE = """You are a restaurant safety and cleanliness inspection AI comparing two images.

**CHECKPOINT**: {checkpoint_name}
**DESCRIPTION**: {checkpoint_description}

**REFERENCE IMAGE (First Image)**: This is the CLEAN/SAFE standard that inspections should match.

**TEST IMAGE (Second Image)**: This is the image being inspected.

**IMPORTANT**: Focus ONLY on cleanliness and food safety issues.

{rules_section}**Your Task:**
FIRST, verify that the TEST image is related to the checkpoint area/subject (e.g., if checkpoint is "Kitchen Sink", the test image should show a kitchen sink).
- If the TEST image is UNRELATED or shows a completely different area/subject, immediately return FAIL with error.
- If the TEST image is related, proceed to compare it against the REFERENCE image for cleanliness and safety standards.
{rules_example}
**Return your analysis as a valid JSON object with this structure:**

{{
  "overall_result": "PASS" or "FAIL",
  "summary": "Brief explanation of why it passed or failed",
  "error": "Set this if TEST image is unrelated to checkpoint (e.g., 'Image shows [X] but checkpoint expects [Y]'), otherwise omit or set to null",
  "rules": [
    {{
      "rule_number": 1,
      "rule_text": "Copy the exact rule text from above",
      "status": "PASS" or "FAIL",
      "details": "Specific details about compliance or violation",
      "location": "Where in the image this applies",
      "safety_impact": "How this affects food safety (if FAIL)"
    }}
  ],
}}

**CRITICAL INSTRUCTIONS**:
- You MUST evaluate ALL {rules_count} rules listed above
- The "rules" array MUST contain exactly {rules_count} entries (one for each rule)
- Each rule entry must include: rule_number (1-{rules_count}), rule_text, status, details, location, safety_impact
- For PASSING rules: Set status="PASS", provide confirmation in details
- For FAILING rules: Set status="FAIL", provide specific violation in details
- DO NOT skip any rules - all {rules_count} rules must be evaluated
- Return ONLY valid JSON, no markdown formatting or extra text
- Focus ONLY on cleanliness and food safety

**VALIDATION CHECK**: Before returning, verify your "rules" array has exactly {rules_count} entries."""

# Camera Monitoring Prompt (basic/minimal - user provides full instructions in rules)
CAMERA_MONITORING_SYSTEM_MESSAGE = """You are an AI analyzing camera images.

**CAMERA**: {checkpoint_name}
**DESCRIPTION**: {checkpoint_description}

**REFERENCE IMAGE (First Image)**: May contain red rectangles or markings indicating areas of interest. Use this as reference if provided.

**CAMERA IMAGE (Second Image)**: The image being analyzed.

**INSTRUCTIONS:**
{rules_section}

Follow the instructions above and return your analysis as a valid JSON object."""
