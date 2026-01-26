"""Utilities for VAPI provider."""

# ============================================================================
# CALL ANALYSIS PROMPT
# ============================================================================

CALL_ANALYSIS_PROMPT = """1. Call Purpose
Identify all the main reasons for the customer's call.
	- store_info: Questions about store operations such as hours, pricing, location/directions, parking, or store policies.
	- menu_info: General inquiries about the menu (items, ingredients, portion sizes, pricing) without placing an order.
	- ordering: Calls where the customer is placing or modifying a food order directly with the store.
	- reservation: Requests to reserve a table at the store.
	- waitlist: Calls to join, check, or manage the restaurant's waitlist.
	- takeout_issue: Issues specifically related to takeout orders (e.g., delays, missing items, pickup problems).
	- third_party_order: Questions or issues about orders placed via third-party apps (DoorDash, UberEats, etc.).
	- delivery: Calls involving delivery - placing delivery orders, asking about delivery availability, delivery areas/zones, delivery fees, delivery times, or issues with deliveries.
	- customer_service: General customer service inquiries not tied to a specific order (e.g., feedback, inquiries about promotions).
	- complaint_service: Complaints about service quality (e.g., staff interactions, slow service, rude behavior).
	- complaint_food_safety: Serious complaints about food safety (e.g., food poisoning, contamination, allergies mishandled).
	- dietary_specific: Inquiries about dietary restrictions or requirements (e.g., gluten-free, vegan, nut-free).
	- lost_and_found: Calls about lost or forgotten items at the store.
	- reservation_change: Requests to modify or cancel an existing reservation.
	- other: Any call purpose that does not fit the categories above.

2. Language Spoken
Determine the *primary* language the customer spoke during the call. Choose exactly one from the options below:
	- english: Customer primarily spoke English
	- french: Customer primarily spoke French
	- spanish: Customer primarily spoke Spanish
	- chinese: Customer primarily spoke Chinese
	- other: Any language that does not fit the categories above.

3. User Satisfaction (Overall)
Assess the customer's overall satisfaction. Choose exactly one from this list:
["positive","neutral","negative"]
	- positive: Customer's issues or inquiries were mostly resolved, or customer confirms resolution and expresses appreciation after resolution (e.g., "that helps, thanks", "perfect").
	- negative: Customer's main issues and inquiries were not met and call ends without an acceptable alternative, or customer expresses dissatisfaction (e.g., "that's not helpful", "I'm frustrated", "this is ridiculous").
	- neutral: Customer's issues or inquiries were partially resolved or transferred, purely informational with no clear success signal, too little content (greeting only), dropped calls, silence, or customer hangs up mid-flow after unmet goal.

4. Explanation of Satisfaction
Write 1–2 sentences explaining why you chose the satisfaction rating.

Output Rules:
You are an evaluation assistant. You must ONLY output valid JSON.
You are NOT allowed to invent or use values outside of the enums below.
If the call does not match any category, you must choose "other".

Valid CallPurpose values (list, multiple allowed, but "other" can only be used once and never combined with other categories):
["store_info","menu_info","ordering","reservation","waitlist","takeout_issue","third_party_order","delivery","customer_service","complaint_service","complaint_food_safety","dietary_specific","lost_and_found","reservation_change","other"]

Valid Language Spoken values (exactly one):
["english","spanish","chinese","other"]

Valid UserSatisfaction values (exactly one):
["positive","neutral","negative"]

Output MUST be valid JSON in this exact schema:
{
  "call_purpose": ["ordering"],
  "language_spoken": "english",
  "user_satisfaction": "positive",
  "explanation": "One or two plain sentences here."
}"""
