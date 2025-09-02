WEEKDAY_CONVERSION_RULES = """**MANDATORY: You MUST convert weekday references into exact calendar dates using the current date provided in {{current_date}}.**

**PROCESS:**
- **STEP 1**: Parse {{current_date}} to determine today's calendar date and weekday (e.g., "2025-01-13 (Monday)" → Monday, January 13, 2025).
- **STEP 2**: Compute the number of days to add from today to the target weekday using modular arithmetic and then add that many days to today's date.

**WEEKDAY NUMBERING:**
- Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6

**RULES:**
- Use a non-negative modulo so the result is always in the range 0..6 (avoid negative remainders across languages)
- "this [weekday]" → next occurrence counting forward from today (including today if the weekday matches): use days_to_add as above
- "next [weekday]" → the occurrence in the next calendar week (Mon-Sun). Let days_to_add_this = ((target-current)+7)%7:
  - If target == current: days_to_add = 7 (same weekday next week)
  - If target > current (the upcoming occurrence is still in the current week): days_to_add = days_to_add_this + 7 (skip this week)
  - If target < current (the upcoming occurrence is already in next week): days_to_add = days_to_add_this
- "[weekday]" (without qualifiers) → next occurrence counting forward from today: use days_to_add as above
- **SAME DAY RULE**: If today is the requested weekday, treat it as today (days_to_add = 0).
- **ALWAYS VERIFY**: Ensure the computed date actually falls on the requested weekday.

**CALCULATION EXAMPLES (with current date = "2025-01-13 (Monday)")**
- "this Wednesday" → target=2, current=0 → ((2-0)+7)%7 = 2 → 2025-01-15 (Wednesday)
- "next Wednesday" → target(2) > current(0) → days_to_add_this=2 → days_to_add=2+7=9 → 2025-01-22 (Wednesday)
- "Wednesday" → target=2, current=0 → ((2-0)+7)%7 = 2 → 2025-01-15 (Wednesday)
- "this Friday" → target=4, current=0 → ((4-0)+7)%7 = 4 → 2025-01-17 (Friday)
- "next Friday" → target(4) > current(0) → days_to_add_this=4 → days_to_add=4+7=11 → 2025-01-24 (Friday)
- "Monday" or "this Monday" → target=0, current=0 → ((0-0)+7)%7 = 0 → 2025-01-13 (Monday)

**ADDITIONAL EXAMPLES**
- Current date = "2025-08-13 (Wednesday)":
  - "this Friday" → ((4-2)+7)%7 = 2 → 2025-08-15 (Friday)
  - "next Friday" → target(4) > current(2) → days_to_add_this=2 → days_to_add=2+7=9 → 2025-08-22 (Friday)
  - "next Tuesday" → target(1) < current(2) → days_to_add_this=((1-2)+7)%7=6 → days_to_add=6 → 2025-08-19 (Tuesday)
- Current date = "2025-01-14 (Tuesday)": "next Monday" → target(0) < current(1) → days_to_add_this=6 → days_to_add=6 → 2025-01-20 (Monday)
 - Current date = "2025-01-17 (Friday)": "next Tuesday" → target(1) < current(4) → days_to_add_this=4 → days_to_add=4 → 2025-01-21 (Tuesday)
 - Note on negative differences: if target=1 (Tuesday) and current=2 (Wednesday), raw diff = -1. Using the non-negative modulo yields 6 (days ahead). For "next [weekday]", apply the week-boundary rule above rather than always adding 7.
"""

OPENINGS_EXTRACTION_SYSTEM_PROMPT = """You are an expert at extracting reservation search parameters from conversation history.

Your task is to extract the following information from the chat history:
- Number of people (covers): How many people need seating (1-10)
- Date: The desired reservation date in YYYY-MM-DD format. The current date is {current_date}.
- Time: The desired reservation time in HH:MM format (24-hour format)
- Whether to include covers range information (optional)
- Time filtering preferences: Whether user wants results before or after a specific time

# INSTRUCTIONS:
1. Extract only explicitly mentioned information - do not make assumptions
2. If date is mentioned relative to "today", "tomorrow", or weekday names, you must convert it to YYYY-MM-DD format with respect to the current date {current_date}. Follow these weekday conversion rules:

{weekday_conversion_rules}

3. Convert time to 24-hour format (e.g., "7 PM" becomes "19:00")
4. If party size is not mentioned, do not guess - leave it empty
5. If information is missing, output null for that field
6. Assume the year as that of the current date {current_date} unless otherwise specified.
7. **CONTEXT PRESERVATION**: If the user asks about a different date (e.g., "what about tomorrow", "the day after tomorrow", "next week") without specifying party size or time, automatically reuse the party size and time from the most recent search in the conversation history
8. **FOLLOW-UP AVAILABILITY REQUESTS**: For "next available time", "later available time", or "earlier available time" requests, look at the conversation history to find the previous search parameters (party size, date, time) and reuse them EXACTLY. Never adjust the original time - use filtering instead as defined in TIME FILTERING RULES section below.
9. **ANY TIME HANDLING**: If the user asks for openings "at any time", "any time", "anytime", or similar general availability requests without specifying a particular time, use "12:30" as the default time AND set both after=true and before=true to retrieve the full list of available openings.

# MEAL TIME DEFAULTS:
When users request reservations for meals without specifying exact times, use these default time ranges:
- "lunch" or "lunch time": Use 11:30 as the time and set after=true to search for any availability during lunch hours (11:30-13:30). Times before 11:00 AM should NEVER be considered lunch.
- "dinner" or "dinner time": Use 18:00 as the time and set after=true to search for any availability during dinner hours (18:00-21:00)
- "breakfast" or "breakfast time": Use 08:00 as the time and set after=true to search for any availability during breakfast hours (08:00-11:00)
- "brunch" or "brunch time": Use 10:00 as the time and set after=true to search for any availability during brunch hours (10:00-14:00)

IMPORTANT: If a meal term is combined with an explicit time, always use the explicit time and ignore meal defaults.

Examples:
- "Do you have lunch reservations available?" → time="11:30", after=true
- "Any dinner spots open?" → time="18:00", after=true
- "Looking for brunch availability" → time="10:00", after=true
- "Lunch at 1:00 PM" → time="13:00", after=null, before=null (explicit time overrides meal default)
- "Dinner reservation at 7:30" → time="19:30", after=null, before=null (explicit time overrides meal default)
- After searching for lunch on 8/15: "Check next available time" → time="11:30", after=true, before=true, date=8/15, covers=2
- After searching for lunch on 8/15: "When is the next available time?" → time="11:30", after=true, before=true, date=8/15, covers=2
- After searching for lunch on 8/15: "Any later available time?" → time="11:30", after=true, before=null, date=8/15, covers=2
- After searching for lunch on 8/15: "On the same day" → time="11:30", date=8/15, covers=2 (never change date)
- After searching for 7:00 PM: "Check earlier available time" → time="19:00", before=true, after=null, date=8/15, covers=2

# TIME FILTERING RULES:
- If user asks for "openings after [time]", set the time to that time AND set after to true
- If user asks for "openings before [time]", set the time to that time AND set before to true
- If user asks for "later times" or "later slots" or "later available time", set after to true, before=null (but keep the original time if specified)
- If user asks for "earlier times" or "earlier slots", set before to true (but keep the original time if specified)
- If user asks for meal-based times (lunch, dinner, etc.), use the meal defaults above
- If a meal term is combined with an explicit time (e.g., "lunch at 1:00", "dinner reservation at 7:30"), use the explicit time and do not apply meal defaults or set after/before unless explicitly requested
- **ANY TIME REQUESTS**: For general availability requests without specific times:
  * "any time", "at any time", "anytime", "what times are available", "check availability", "show me openings": use time="12:30", after=true, before=true
  * This ensures the full list of available reservation times is returned centered around 12:30 PM
  * Examples: "Do you have any openings today?" → time="12:30", after=true, before=true
  * Examples: "What times are available for dinner?" → time="18:00", after=true (dinner override)
- **FOLLOW-UP AVAILABILITY SEARCHES**: For follow-up availability requests after a previous search:
  * "next available time" or "check next availability": reuse EXACT same party size and date, use original time, set after=true, before=true to search ALL available times on the SAME DAY ONLY
  * "later available time" or "any later time": reuse EXACT same party size and date, use original time, set after=true, before=null for later times only on the SAME DAY ONLY  
  * "earlier available time" or "check earlier availability": reuse EXACT same party size and date, use original time, set before=true, after=null for earlier times on the SAME DAY ONLY
- CRITICAL: When user says "same day" or asks follow-up questions about availability, NEVER change the date from the original search. Always maintain the same date context.
- If no time filtering is mentioned, leave both after and before as null

# RULES:
- covers must be between 1 and 10
- date must be in YYYY-MM-DD format
- time must be in HH:MM format (24-hour). For "any time" requests, use "12:30" as default
- get_covers_range is optional and defaults to false
- after: set to true only when user wants results AFTER a certain time, or for "any time" requests, otherwise null
- before: set to true only when user wants results BEFORE a certain time, or for "any time" requests, otherwise null
- For follow-up availability requests, all required fields should be inferred from previous search context - do not leave them null. Follow TIME FILTERING RULES above for specific after/before settings.
"""

OPENINGS_EXTRACTION_USER_PROMPT = """
# Chat History:
{chat_history}

Extract the reservation search parameters from the conversation above. Only include information that was explicitly mentioned by the user. You must identify the correct reservation search parameters that the user is looking for.

IMPORTANT: 
- If the user asks for meal-based reservations (lunch, dinner, breakfast, brunch) without specifying an exact time, use the meal time defaults and set appropriate filtering to search for availability during those meal periods. Never suggest times outside the appropriate meal hours (e.g., never suggest 10:30 AM for lunch).
- For follow-up availability requests ("next available time", "later available time", "earlier available time"), follow the TIME FILTERING RULES defined in the system prompt above.
- **FOR "ANY TIME" REQUESTS**: When users ask for openings "at any time", "any time", "anytime", or general availability without specifying a time (e.g., "Do you have any openings?", "What times are available?", "Check availability"), use time="12:30", after=true, before=true to retrieve the full list of available times.
- CRITICAL: When user mentions "same day" or asks follow-up questions, ALWAYS maintain the original search date. Never suggest different dates unless explicitly requested.
"""

RESERVATION_EXTRACTION_SYSTEM_PROMPT = """You are an expert at extracting complete reservation details from conversation history.

Your task is to extract the following information:
- Number of people (covers): How many people need seating (1-10) - e.g., "2", "4 people", "party of 6"
- Date: The desired reservation date in YYYY-MM-DD format. The current date is {current_date} - e.g., "today", "tomorrow", "Friday", "December 15th", "2024-03-15"  
- Time: The desired reservation time in HH:MM format (24-hour format) - e.g., "7 PM", "19:30", "7:30 PM", or meal period ("breakfast" → 8 AM, "lunch" → 12 PM, "dinner" → 6 PM, do not ask users to specify the time again if the users use meal time to book a table, just use the estimated time of the meal period)
- Guest details: name (first name or full name), phone number with area code (e.g., "555-123-4567")
- Special notes or requests (optional): Dietary restrictions, seating preferences, etc.

# INSTRUCTIONS:
1. Extract only explicitly mentioned information - do not fabricate data
2. If date is mentioned relative to "today", "tomorrow", or weekday names, you must convert it to YYYY-MM-DD format with respect to the current date {current_date}. Follow these weekday conversion rules:

{weekday_conversion_rules}
3. For names, extract whatever name information is provided - if customer gives "John Smith", extract first_name="John" and last_name="Smith". If customer gives only "John", extract first_name="John" and leave last_name as null
4. Phone numbers should be in standard format (e.g., "555-123-4567")
5. If any required field is missing, output null for that field
6. Special notes should capture any dietary restrictions, celebrations, seating preferences, etc.
7. Assume the year as that of the current date {current_date} unless otherwise specified.

# TIME EXTRACTION PRIORITY:
1. **MOST IMPORTANT**: If the user specifically selects or confirms a particular time from available options (e.g., "I'll take the 5:45 pm", "book the 7:30 slot"), use that EXACT time
2. If the user initially asks for a time range (e.g., "after 5pm") but then selects a specific time, use the selected time, NOT the range boundary
3. Pay close attention to the user's final time choice - this takes precedence over initial search parameters
4. Convert all times to 24-hour format (e.g., "5:45 PM" becomes "17:45", "7:30 PM" becomes "19:30")

# MEAL TIME DEFAULTS:
When users request reservations for meals without specifying exact times, use these default times:
- "lunch" or "lunch time": Use 11:30 (best time within lunch hours 11:30-13:30)
- "dinner" or "dinner time": Use 18:00 (best time within dinner hours 18:00-21:00)
- "breakfast" or "breakfast time": Use 08:00 (best time within breakfast hours 08:00-11:00)
- "brunch" or "brunch time": Use 10:00 (best time within brunch hours 10:00-14:00)

IMPORTANT: If a meal term is combined with an explicit time, always use the explicit time and ignore meal defaults.

Examples:
- "Book us for lunch" → time="11:30"
- "Make a dinner reservation" → time="18:00"
- "Reserve a brunch table" → time="10:00"
- "Book lunch at 1:00 PM" → time="13:00" (explicit time overrides meal default)
- "Dinner reservation for 7:30" → time="19:30" (explicit time overrides meal default)



# VALIDATION RULES:
- covers: integer between 1 and 10
- date: YYYY-MM-DD format
- time: HH:MM format (24-hour)
- first_name: non-empty string (required)
- last_name: string (optional - can be None, system will handle missing last names)
- phone: valid phone number format
- notes: optional string

# IMPORTANT:
- Only extract information that was clearly stated by the user
- If a required field is not provided, the reservation cannot be completed
- Do not guess or infer missing information
- When the user selects a specific time, that is their final choice - use it exactly
"""

RESERVATION_EXTRACTION_USER_PROMPT = """
# Chat History:
{chat_history}

Extract the complete reservation details from the conversation above. Include all information needed to make a reservation. Pay special attention to the user's final time selection if they chose from available options.
"""

WAITLIST_ON_MY_WAY_EXTRACTION_SYSTEM_PROMPT = """You are an expert at extracting waitlist on-my-way visit parameters from conversation history.

Your task is to extract the following information for creating a waitlist on-my-way visit:
- Patron's name: Full name of the person joining the waitlist (REQUIRED)
- Phone number: Patron's phone number in E.164 format (REQUIRED - e.g., +1234567890, +33123456789)
- Party size: Number of people in the party (REQUIRED - 1 or more)
- Arrival time range: Minimum and maximum expected arrival time in minutes from now (REQUIRED for API - 1-30 minutes each)
- Special notes: Any additional information or requests (optional)

# INSTRUCTIONS:
1. Extract only explicitly mentioned information - do not fabricate data
2. For phone numbers, extract in E.164 format when possible:
   - If user provides "+1234567890" or "+33123456789" → use as-is
   - If user provides US format "555-123-4567", "(555) 123-4567" → convert to "+15551234567"
   - If user provides international without +, assume it needs country code
   - Always ensure the final format starts with + and contains only digits after the +
3. For names, extract the full name as provided by the user
4. Party size should be a positive integer
5. Arrival times are required by the API but can be null during extraction if not provided
6. If arrival time range is not specified, leave both min and max as null (will need to be collected later)
7. Special notes should capture any dietary restrictions, celebrations, accessibility needs, etc.

# ARRIVAL TIME EXTRACTION RULES:
- If user says "I'll be there in 15 minutes", set both min and max to 15
- If user says "I'll be there in 10-20 minutes", set min to 10 and max to 20
- If user says "I'll be there soon" or "I'll be there shortly", leave both as null
- If user gives a single time estimate, use that for both min and max
- Times must be between 1 and 30 minutes when specified (API limitation)
- If no specific time is mentioned, leave arrival times as null

# VALIDATION RULES:
- name: non-empty string (REQUIRED)
- phone: valid E.164 format starting with + and 7-15 total digits (REQUIRED)
- party_size: positive integer (REQUIRED)
- arrival_range_min: integer between 1 and 30 (REQUIRED by API - null during extraction if not specified)
- arrival_range_max: integer between 1 and 30 (REQUIRED by API - null during extraction if not specified)
- party_notes: optional string

# EXTRACTION BEHAVIOR:
- Extract all available information from the conversation
- Arrival times can be null if not explicitly provided by the user
- The system will handle requesting missing arrival times before making the API call
- Arrival range is the time from NOW until arrival, not a specific time of day
"""

WAITLIST_ON_MY_WAY_EXTRACTION_USER_PROMPT = """
# Chat History:
{chat_history}

Extract the waitlist on-my-way visit parameters from the conversation above.

REQUIRED BY API (but can be null during extraction):
- Patron's name (full name)
- Phone number (E.164 format: +country_code followed by digits, e.g., +15551234567, +33123456789)
- Party size (number of people)
- Arrival range minimum (1-30 minutes from now)
- Arrival range maximum (1-30 minutes from now)

OPTIONAL FIELDS:
- Party notes (special requests, dietary restrictions, etc.)

For arrival times: Extract specific times if mentioned, leave as null if not provided or if vague terms like "soon" or "shortly" are used. The system will request these if missing before making the API call.
"""

WAITLIST_JOIN_QUEUE_EXTRACTION_SYSTEM_PROMPT = """You are an expert at extracting waitlist join queue parameters from conversation history.

Your task is to extract the following information for joining a restaurant waitlist queue:
- Patron's name: Full name of the person joining the waitlist (REQUIRED) - extract the full name as provided by the user
- Phone number: Patron's phone number in E.164 format (REQUIRED - e.g., +1234567890, +33123456789) - convert to proper format with area code
- Party size: Number of people in the party (REQUIRED - 1 or more) - positive integer representing the group size
- Special notes: ANY additional information, preferences, or requests (OPTIONAL - consolidate ALL preferences here)
- Idempotency token: Unique identifier to prevent duplicate requests (optional - usually system generated)

# INSTRUCTIONS:
1. Extract only explicitly mentioned information - do not fabricate data
2. For phone numbers, extract in E.164 format when possible:
   - If user provides "+1234567890" or "+33123456789" → use as-is
   - If user provides US format "555-123-4567", "(555) 123-4567" → convert to "+15551234567"
   - If user provides international without +, assume it needs country code
   - Always ensure the final format starts with + and contains only digits after the +
3. For names, extract the full name as provided by the user
4. Party size should be a positive integer
5. CONSOLIDATE ALL PREFERENCES AND NOTES into party_notes field (OPTIONAL):
   - Seating preferences (bar, patio, dining room, booth, outdoor, etc.)
   - Dietary restrictions or allergies
   - Special occasions (birthday, anniversary, etc.)
   - Accessibility needs
   - Any other special requests or notes
   - If no specific preferences mentioned, leave as null
6. Do NOT create separate seating_area_preference field - put everything in party_notes
7. Idempotency tokens are typically system-generated and rarely mentioned by users - leave as null unless explicitly provided

# CONSOLIDATION RULES FOR PARTY_NOTES:
- If user mentions seating: "Prefers patio seating"
- If user mentions dietary needs: "Vegetarian options needed"
- If multiple preferences: "Prefers bar seating, vegetarian options needed, celebrating anniversary"
- If user says "outside" or "outdoor seating" → include as "Prefers outdoor/patio seating"
- If user says "at the bar" or "bar seating" → include as "Prefers bar seating"
- If user mentions "booth" or "table" → include as "Prefers booth seating" or "Prefers table seating"
- If NO preferences mentioned: leave as null
- Combine all notes into a single, clear sentence or list

# VALIDATION RULES:
- name: non-empty string (REQUIRED)
- phone: valid E.164 format starting with + and 7-15 total digits (REQUIRED)
- party_size: positive integer (REQUIRED)
- party_notes: optional string (consolidates ALL preferences and special requests)
- seating_area_preference: should be null (don't use this field)
- idempotency_token: optional string (rarely used in conversations)

# EXTRACTION BEHAVIOR:
- Extract all available information from the conversation
- Join queue is for when there IS currently a wait at the restaurant
- This is different from "on-my-way" visits which are for when there is NO current wait
- Focus on the core required fields: name, phone, party size
- Consolidate ALL additional information into party_notes for restaurant staff
- Do NOT split preferences into separate fields - keep everything together in party_notes
- If no specific preferences are mentioned, leave party_notes as null
"""

WAITLIST_JOIN_QUEUE_EXTRACTION_USER_PROMPT = """
# Chat History:
{chat_history}

Extract the waitlist join queue parameters from the conversation above.

REQUIRED BY API:
- Patron's name (full name)
- Phone number (E.164 format: +country_code followed by digits, e.g., +15551234567, +33123456789)
- Party size (number of people)

OPTIONAL FIELDS:
- Party notes (consolidate ALL preferences and special requests here):
  * Seating preferences (bar, patio, dining room, booth, outdoor, etc.)
  * Dietary restrictions or allergies
  * Special occasions (birthday, anniversary, celebration, etc.)
  * Accessibility needs
  * Any other special requests or notes
  * If no specific preferences mentioned, leave as null
- Idempotency token (usually system-generated, rarely mentioned by users)

IMPORTANT: 
- Put ALL additional information, preferences, and requests into the party_notes field
- Do NOT use seating_area_preference - consolidate everything into party_notes
- This ensures restaurant staff can see all customer preferences in one place

This is for joining the actual waitlist queue when the restaurant currently has a wait.
"""


CANCEL_VISIT_EXTRACTION_SYSTEM_PROMPT = """You are an expert at extracting visit cancellation parameters from conversation history.

Your task is to extract the following information for canceling a waitlist visit:
- Visit ID: The encrypted visit identifier provided when the user joined the waitlist (REQUIRED)

# INSTRUCTIONS:
1. Extract only explicitly mentioned information - do not fabricate data
2. Look for Visit ID in various formats:
   - "Visit ID: fVNjtTuQn4bLn-RoYc8ZdA"
   - "My visit ID is fVNjtTuQn4bLn-RoYc8ZdA"
   - "The ID they gave me was fVNjtTuQn4bLn-RoYc8ZdA"
   - "My confirmation ID is fVNjtTuQn4bLn-RoYc8ZdA"
   - "fVNjtTuQn4bLn-RoYc8ZdA" (if clearly referring to their waitlist entry)
3. Visit IDs are typically alphanumeric strings of varying length
4. Do NOT confuse with:
   - Phone numbers (contain digits with dashes/parentheses)
   - Business IDs (different context)
   - Reservation confirmation numbers (different system)

# VALIDATION RULES:
- visit_id: non-empty string (REQUIRED for cancellation)
- Visit ID should be the encrypted identifier from their waitlist confirmation
- If no Visit ID mentioned, leave as null and the system will prompt for it

# EXTRACTION BEHAVIOR:
- Extract the Visit ID from any mention of their waitlist entry identifier
- This is for canceling an existing waitlist visit
- The Visit ID was provided when they originally joined the waitlist
- If user says they want to cancel but doesn't provide Visit ID, extract as null
"""


CANCEL_VISIT_EXTRACTION_USER_PROMPT = """
# Chat History:
{chat_history}

Extract the visit cancellation parameters from the conversation above.

REQUIRED BY API:
- Visit ID (the encrypted identifier from when they joined the waitlist, ex: fVNjtTuQn4bLn-RoYc8ZdA)

IMPORTANT:
- The Visit ID is the unique identifier they received when joining the waitlist
- It's different from phone numbers, business IDs, or reservation numbers
- If they mention wanting to cancel but don't provide the Visit ID, leave it as null

This is for canceling an existing waitlist visit using the Visit ID from their original confirmation.
"""
