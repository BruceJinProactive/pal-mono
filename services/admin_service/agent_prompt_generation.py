import concurrent.futures
import re
import subprocess

import requests
from bs4 import BeautifulSoup

from agent.model import ModelOptions, call_llm_default
from utils.log import logger


def parse_agent_prompt_sections(generated_prompt: str) -> dict:
    """
    Split the generated prompt into separate sections.

    Args:
        generated_prompt (str): The complete LLM-generated prompt

    Returns:
        dict: Dictionary with persona and interaction_guidelines
    """
    # Split on interaction guidelines - everything before is persona
    guidelines_match = re.search(
        r"(?:#{1,4}\s*|\*{1,2}|^)\s*Interaction Guidelines\*{0,2}[\s:]*\n(.*?)$",
        generated_prompt,
        re.DOTALL | re.MULTILINE,
    )

    if guidelines_match:
        # Find where interaction guidelines starts
        guidelines_start = guidelines_match.start()
        persona_content = generated_prompt[:guidelines_start].strip()
        # Include the header in the guidelines content
        guidelines_content = generated_prompt[guidelines_start:].strip()
    else:
        # No interaction guidelines found - everything is persona
        persona_content = generated_prompt.strip()
        guidelines_content = ""

    return {
        "persona": persona_content,
        "interaction_guidelines": guidelines_content,
    }


def scrape_website(url: str) -> str | None:
    """Scrape a single website for restaurant context using curl and subprocess."""
    try:
        # Validate URL to prevent command injection
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"] or not parsed.netloc:
            logger.warning(f"Invalid URL format: {url}")
            return None

        # First try using curl with subprocess for better compatibility
        curl_command = [
            "curl",
            "-A",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "--max-time",
            "10",
            "--silent",
            "--show-error",
            "--location",
            "--fail",
            url,
        ]

        result = subprocess.run(
            curl_command, capture_output=True, text=True, timeout=12
        )

        if result.returncode == 0 and result.stdout:
            html_content = result.stdout
        else:
            # Fallback to requests if curl fails
            logger.debug(f"Curl failed for {url}, falling back to requests")
            response = requests.get(
                url,
                timeout=8,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                },
            )
            response.raise_for_status()
            html_content = response.text

        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text content
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        # Limit to reasonable length
        if len(text) > 1500:  # Reduced from 2000 for faster processing
            text = text[:1500] + "..."

        return text

    except subprocess.TimeoutExpired:
        logger.error(f"Curl timeout for {url}")
        return None
    except Exception as e:
        logger.error(f"Could not scrape {url}: {e}")
        return None


def scrape_multiple_urls_parallel(urls: list[str]) -> str:
    """Scrape multiple URLs in parallel for better performance."""
    if not urls:
        return ""

    valid_urls = [url.strip() for url in urls if url.strip()]
    if not valid_urls:
        return ""

    scraped_contents = []

    # Use ThreadPoolExecutor for parallel scraping
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_url = {
            executor.submit(scrape_website, url): url for url in valid_urls
        }

        for future in concurrent.futures.as_completed(future_to_url, timeout=15):
            url = future_to_url[future]
            try:
                content = future.result()
                if content:
                    scraped_contents.append(f"Content from {url}:\n{content}")
                    logger.debug(
                        f"Successfully scraped {len(content)} characters from {url}"
                    )
            except Exception as e:
                logger.error(f"Could not scrape {url}: {e}")

    return "\n---\n".join(scraped_contents) if scraped_contents else ""


async def summarize_menu_with_llm(menu_content: str) -> str:
    """
    Use LLM to intelligently summarize menu content for prompt optimization.
    This handles any menu format and creates a contextual summary.
    """
    if not menu_content or not menu_content.strip():
        return "No menu information available"

    try:
        summarization_prompt = f"""You are a restaurant menu expert. Please create a balanced summary of this menu that will help a customer service AI agent assist customers effectively.

MENU CONTENT:
{menu_content[:8000]}  

INSTRUCTIONS:
- Extract the most important menu items and categories
- Include popular/signature items if mentioned
- Note key ingredients, dietary options, and specialties
- Keep the summary under 600 words
- Focus on items customers would likely ask about
- Include price ranges if provided
- Organize by categories (appetizers, mains, desserts, etc.)
- Be factual - don't add information not in the menu
- Adjust detail level based on menu size (more concise for large menus, more detailed for small ones)

Format as a clean, organized summary that an AI agent can reference when helping customers."""

        chat_params = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a menu analysis expert who creates concise, accurate summaries.",
                },
                {"role": "user", "content": summarization_prompt},
            ],
            "max_tokens": 800,
            "temperature": 0.1,
        }

        response = await call_llm_default(
            model_option=ModelOptions.GPT_4O, params=chat_params
        )

        if not response.choices:
            raise RuntimeError(f"No response from LLM: {response.model_dump_json()}")

        choice = response.choices[0]
        if not choice.message:
            raise RuntimeError("Choice has no message")

        content = choice.message.content or ""
        summary = content.strip() if isinstance(content, str) else ""

        # Log the summarization results
        return summary

    except Exception as e:
        logger.error(f"Menu summarization failed: {e}")
        # Fallback to basic extraction if LLM fails
        return "Menu provided - please reference the original menu content below."


async def build_prompt(
    restaurant_name: str,
    menu_content: str,
    keywords: str,
    agent_name: str,
    agent_type: str,
    specific_instructions: str = "",
    additional_context: str = "",
) -> str:
    """Build the comprehensive prompt for agent generation."""

    # Check if menu content exists and get summary
    has_menu = bool(menu_content and menu_content.strip())
    menu_summary = (
        await summarize_menu_with_llm(menu_content)
        if has_menu
        else "No menu information available"
    )

    # Build menu information section using LLM summary
    menu_info_section = ""
    if has_menu and menu_summary != "No menu information available":
        menu_info_section = f"""
### Menu Information Available:
{menu_summary}

**CRITICAL GUIDELINES**:
- Only reference menu items that actually exist in the above summary
- Do not invent or hallucinate any menu items not mentioned
- Use exact item names when possible
- If unsure about an item, ask the customer for clarification"""
    else:
        menu_info_section = """
### Menu Information:
- No specific menu provided - focus on general hospitality and service excellence
- **CRITICAL**: Do not invent or hallucinate specific menu items
- Recommend that customers ask about current menu options"""

    # Build additional context section
    additional_context_section = ""
    if additional_context.strip():
        additional_context_section = f"""
### Additional Restaurant Context:
Use this factual information from the restaurant's website to inform the agent's knowledge:
{additional_context}

**IMPORTANT**: Only use factual information from the provided context. Do not add details not present in the source material."""

    # Agent type specific content
    agent_capabilities = ""

    if agent_type == "general":
        agent_capabilities = """
**AGENT TYPE: GENERAL (INFORMATION & ASSISTANCE)**
This agent specializes in providing helpful information and guidance. The agent's role is to:
- Answer questions about menu items, ingredients, and preparation
- Provide recommendations and suggestions
- Share information about the restaurant
- Help customers understand options
- Assist with menu navigation and dining decisions"""
    else:  # ordering
        agent_capabilities = """
**AGENT TYPE: ORDERING**
This agent CAN take orders and help with the complete ordering process. The agent's role includes:
- Answer questions about menu items, ingredients, and preparation
- Provide recommendations and suggestions
- Take customer orders with modifications and special requests
- Confirm order details and dietary restrictions
- Process the complete ordering workflow
- Provide helpful service throughout the ordering experience"""

    # Extract complex expressions to avoid f-string syntax issues
    menu_content_text = (
        menu_content
        if menu_content
        else "No menu provided - focus on general restaurant service principles"
    )
    special_instructions_section = (
        f"### Special Instructions:\n{specific_instructions}\n"
        if specific_instructions.strip()
        else ""
    )

    # Extract the conditional text blocks that contain backslashes
    if agent_type == "general":
        section_3_title = "### 3. Information Sharing & Guidance"
        section_3_content = """- How to provide comprehensive information about menu items
- Explaining ingredients, preparation methods, and options
- **Regional expressions and communication patterns if geographical context detected**
- Handling questions about restaurant policies and services
- Professional information-focused closing approach"""
    else:
        section_3_title = "### 3. Order Management"
        section_3_content = """- How to confirm orders clearly (using any regional communication style if detected)
- **Regional courtesy expressions and confirmation styles if cultural context found**
- Handling modifications and special requests
- Confirming dietary restrictions and allergies
- Professional order completion approach"""

    prompt_text = f"""
You are an expert in designing voice AI personalities for restaurants.

**FIRST**: Analyze the personality keywords "{keywords}" to determine if they contain any geographical, regional, or cultural context (locations, ethnicities, regional descriptors, etc.). If found, incorporate authentic regional characteristics naturally throughout the prompt, **including subtle regional speaking styles, expressions, and communication patterns that are genuine to that area. IMPORTANT: Focus on genuine hospitality styles and communication approaches rather than obvious stereotypes or exaggerated regional traits.**

Create a comprehensive prompt that defines a voice AI agent's **Persona** and **Interaction Guidelines** with specific examples and detailed guidance.

Base the prompt on:
- Restaurant name: {restaurant_name}
{("- Agent name: " + agent_name) if agent_name else ""}
- Personality keywords: {keywords}
{"- Specific requirements to integrate throughout (DO NOT show as separate section): " + specific_instructions + " **CRITICAL: Only reference information that is factually provided in these instructions - do not invent, assume, or hallucinate any details not explicitly stated.**" if specific_instructions.strip() else ""}
- Available menu information
- Additional factual context from restaurant websites

{agent_capabilities}

**CRITICAL ACCURACY REQUIREMENTS:**
1. **ONLY use menu items that actually exist** in the provided menu content
2. **ONLY use factual information** from the provided additional context
3. **DO NOT invent, hallucinate, or assume** details not explicitly provided
4. When no menu is provided, focus on general service principles without specific items
5. Make all examples realistic and based on actual provided information
6. **If keywords contain geographical/cultural context**: Incorporate authentic regional characteristics naturally - keep it respectful and genuine, avoid stereotypes. **Include subtle regional speaking styles, common expressions, hospitality customs, and communication patterns specific to that area. CRITICAL: Avoid exaggerated accents, clichéd phrases, or overly obvious regional references. Keep it natural and professional.**
7. **NEVER include timing or logistics information** like preparation times or "ready in X minutes"
8. **USE ONLY FACTUAL EXAMPLES**: All examples must use actual menu items or be generic enough to avoid misleading information (e.g., "our signature dish" instead of inventing specific dishes)
{"9. **STRATEGIC INTEGRATION OF REQUIREMENTS**: Incorporate these requirements selectively where most appropriate and natural - avoid forcing them into every section: " + specific_instructions + " **Only use facts explicitly stated in these requirements - do not expand or assume additional details.**" if specific_instructions.strip() else ""}
{"10. **GENERAL AGENTS**: Focus on information, guidance, and customer assistance" if agent_type == "general" else "10. **ORDERING AGENTS**: Include complete order-taking workflow and confirmation processes"}

**Instructions:**
1. Create two distinct, well-separated sections: Persona and Interaction Guidelines
2. For each point, provide 1-2 specific examples using "Example:" format
3. Include "Do/Don't" examples where helpful
4. Use numbered bullet points for better organization
5. **Make examples specific to the restaurant using ONLY provided factual information - if no specific info available, use generic examples like "our signature dish" or "our popular items"**
6. Keep tone {keywords} throughout
7. If geographical/cultural context detected in keywords, incorporate authentic characteristics naturally
{"8. **MANDATORY SPECIAL INSTRUCTIONS INTEGRATION**: The special instructions '" + specific_instructions + "' MUST be woven into your generated prompt. Include them naturally in relevant sections (voice/tone, interaction guidelines, examples, scenarios) - don't create a separate section, but ensure they appear in the final prompt output where they make sense contextually. **Stick strictly to the facts provided - no embellishment or additional assumptions.**" if specific_instructions.strip() else "8. No special instructions provided"}
{"9. Focus on exceptional information sharing and customer assistance" if agent_type == "general" else "9. Include comprehensive order management and confirmation processes"}

**REGIONAL AUTHENTICITY GUIDELINES (if geographical context detected):**
- Focus on genuine hospitality styles and communication approaches of the region
- Use subtle expressions and speaking patterns, not exaggerated accents or dialect
- Incorporate authentic local customs and values, not stereotypical behaviors
- Maintain professional service standards while reflecting regional warmth and character
- Avoid clichéd phrases or overly obvious regional references
- Emphasize universal hospitality enhanced by regional genuine characteristics

---

## Persona

**IMPORTANT: Start your response directly with the ## Persona header shown above, then immediately include the character description below it.**

Character description:
{"You are " + agent_name + ", [dynamically create a role description using the actual personality traits provided: " + keywords + ". Vary your phrasing - could be 'a [keyword] server', 'the [keyword] hospitality specialist', '[keyword] team member', or other creative combinations that fit the specific keywords given] for " + restaurant_name + ". [Then create a natural character description that reflects the essence of these specific personality traits and any geographical/cultural background found in keywords, based on provided context]" if agent_name else "You are [dynamically create a role description using the actual personality traits provided: " + keywords + ". Vary your phrasing - could be 'a [keyword] server', 'the [keyword] hospitality specialist', '[keyword] team member', or other creative combinations that fit the specific keywords given] for " + restaurant_name + ". [Then create a natural character description that reflects the essence of these specific personality traits and any geographical/cultural background found in keywords, based on provided context]"}

### Voice & Tone

Create 4-5 numbered points that reflect the {keywords} personality and any geographical/cultural characteristics found in the keywords. {"**REQUIRED**: Include and reference these specific requirements in your generated prompt: " + specific_instructions + ". Weave them into relevant voice/tone points where they naturally fit. The final prompt output MUST contain these instructions. **IMPORTANT: Use only the exact information provided - do not add details not explicitly stated.**" if specific_instructions.strip() else ""}

Each point should include:
- A clear principle/guideline
- 1-2 specific dialogue examples using ONLY actual menu items when available, or generic examples if no factual information provided
- **Any authentic geographical/cultural characteristics if relevant, including subtle regional speaking styles, expressions, and hospitality customs (avoid stereotypes or exaggerated traits)**
- Context for when to use this approach

Format each point as:
1. **[Principle Name]**
   - [Guideline description]
   - [When to use this approach]
   Example:
   "[Specific dialogue example using ONLY real menu items OR generic examples like 'our signature dish' - never invent specific information]"

Make sure the voice and tone guidelines directly reflect the {keywords} personality traits and any cultural background detected.

---

## Interaction Guidelines

Create detailed, practical guidelines organized into clear subsections{"**MANDATORY**: Ensure these specific requirements appear in your generated interaction guidelines: " + specific_instructions + " **Remember: Only reference facts explicitly provided in these requirements. The final prompt MUST include these instructions in appropriate guideline sections.**" if specific_instructions.strip() else ""}:

### 1. Opening Interactions
- How {"the agent" if not agent_name else agent_name} should greet customers (incorporating any regional hospitality style if detected in keywords)
- Energy level and approach
- **Regional greeting styles and expressions if geographical context is detected (keep subtle and professional, avoid stereotypical phrases)**
- Initial questions to ask
{"- Focus on providing helpful information and assistance" if agent_type == "general" else "- Determine if customer wants information or is ready to order"}
Examples with specific dialogue reflecting any regional communication style found in keywords (use ONLY factual information or generic examples)

### 2. Menu Navigation & Recommendations
- Process for understanding customer preferences
- How to describe menu items (using ONLY actual provided menu items or generic descriptions)
- **Regional food terminology and expressions if cultural context is detected (use authentic terms, not stereotypical food references)**
- Approach for dietary restrictions and allergies
{"- Upselling and suggestion techniques" if agent_type == "ordering" else ""}
- Any regional food culture and preferences if relevant to keywords
Examples with ONLY real menu items when available OR generic examples like "our most popular dish"

{section_3_title}
{section_3_content}
Examples with specific dialogue incorporating any regional style found in keywords (use ONLY factual information or broad examples)

### 4. Communication Best Practices
- Do/Don't examples for maintaining the {keywords} personality and any regional authenticity
- How to handle difficult situations
- Maintaining conversation flow
- Key phrases to use and avoid
- **Natural incorporation of any geographical/cultural characteristics found in keywords, including subtle regional speaking patterns and expressions (prioritize authentic communication styles over obvious regional clichés)**
{"- Maintain focus on information and assistance excellence" if agent_type == "general" else "- Smooth order flow management"}

---

{menu_info_section}

{additional_context_section}

### Restaurant Context:
- **Name**: {restaurant_name}
{("- **Agent**: " + agent_name) if agent_name else ""}
- **Personality**: {keywords}

{special_instructions_section}### Menu Content for Reference:
{menu_content_text}
"""

    # Build the final instruction
    agent_capability_text = (
        "Focus on providing helpful information, guidance, and exceptional customer assistance."
        if agent_type == "general"
        else "Include complete order-taking capabilities and workflow."
    )

    special_instructions_integration = ""
    if specific_instructions.strip():
        special_instructions_integration = f" **CRITICAL: Ensure the special instructions '{specific_instructions}' are naturally integrated throughout the generated prompt where relevant - include them in appropriate sections like voice/tone, interaction guidelines, or specific scenarios. Don't create a separate section, but weave them into the practical guidance.**"

    final_instruction = f"""

**CRITICAL OUTPUT INSTRUCTIONS:**

Your response must ONLY contain the final agent prompt{"that " + agent_name + " will use" if agent_name else ""}. 

DO NOT include in your response:
- Any analysis of the keywords (like "even though these keywords don't indicate...")  
- Any commentary about your process or methodology
- Any meta-instructions or guidelines about prompt creation
- Any phrases like "based on the analysis", "the following prompt", or "here is the prompt"
- Any sections titled "Analysis" or "Approach"

START your response directly with:
{"You are " + agent_name + ", [create role description] for " + restaurant_name + "..." if agent_name else "You are [create role description] for " + restaurant_name + "..."}

Generate a comprehensive, example-rich prompt {"that " + agent_name + " can use " if agent_name else ""}to provide excellent, {keywords} customer service at {restaurant_name} with any authentic geographical/cultural character found in the keywords. {agent_capability_text} Use ONLY factual information provided above. If regional characteristics are included, ensure they are subtle, authentic, and professional - avoid stereotypes or exaggerated traits.{special_instructions_integration}

OUTPUT THE CLEAN AGENT PROMPT NOW (start with "You are {agent_name}..."):"""

    return prompt_text + final_instruction


async def generate_agent_prompts(
    restaurant_name: str,
    agent_name: str,
    agent_type: str,
    keywords: str,
    specific_instructions: str = "",
    menu_content: str = "",
    additional_urls: list[str] | None = None,
) -> dict:
    """
    Generate agent prompts using LLM service based on restaurant and agent information.

    This function uses LLM service and web scraping - no database access needed.
    """
    if additional_urls is None:
        additional_urls = []

    # Validation
    if not restaurant_name or not keywords:
        raise ValueError("Restaurant name and keywords are required")

    if agent_type not in ["general", "ordering"]:
        raise ValueError('Agent type must be either "general" or "ordering"')

    logger.info(
        f"🚀 Starting generation for: {restaurant_name} with agent '{agent_name if agent_name else 'unnamed'}' ({agent_type}) and keywords: {keywords}"
    )

    # Scrape additional URLs for context (in parallel for better performance)
    additional_context = ""
    if additional_urls and any(url.strip() for url in additional_urls):
        valid_urls = [url.strip() for url in additional_urls if url.strip()]
        additional_context = scrape_multiple_urls_parallel(valid_urls)

    try:

        prompt = await build_prompt(
            restaurant_name=restaurant_name,
            menu_content=menu_content,
            keywords=keywords,
            agent_name=agent_name,
            agent_type=agent_type,
            specific_instructions=specific_instructions,
            additional_context=additional_context,
        )

        chat_params = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2500,
            "temperature": 0.7,
        }

        response = await call_llm_default(
            model_option=ModelOptions.GPT_4O, params=chat_params
        )

        if not response.choices:
            raise RuntimeError(f"No response from LLM: {response.model_dump_json()}")

        choice = response.choices[0]
        if not choice.message:
            raise RuntimeError("Choice has no message")

        content = choice.message.content or ""

        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned empty or invalid response")

        generated_prompt = content.strip()

        logger.info(
            f"✅ Generated {len(generated_prompt)} characters successfully for {agent_name if agent_name else 'unnamed agent'}"
        )

        # Parse the response into separate sections
        parsed_sections = parse_agent_prompt_sections(generated_prompt)

        return parsed_sections

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ LLM API error: {error_msg}")

        if "billing" in error_msg.lower() or "quota" in error_msg.lower():
            raise ValueError(
                "LLM API billing issue detected. Please check your configuration and billing settings."
            )
        else:
            raise ValueError(f"LLM API error: {error_msg}")
