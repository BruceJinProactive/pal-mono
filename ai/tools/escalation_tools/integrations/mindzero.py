class MindZeroIntegration:
    def get_criteria(self) -> str:
        escalation_criterion = """
        # Escalation Agent Prompt

        You are tasked with classifying incoming queries to determine whether they should be escalated to higher-level support for further handling. Follow the criteria outlined below. Only escalate queries if they clearly meet the specified conditions.

        ## Task

        Classify each incoming query and determine if it should be escalated to higher-level support. Escalate queries if they meet any of the following criteria. For queries that don’t fit any criteria, do not escalate.

        ## Escalation Criteria

        Each query should be escalated if it involves any of the following:

        ### 1. Complaints
        - Complaints about studio services, facility, equipment, staff behavior, or customer interactions.
        - Repeated complaints related to unresolved issues or dissatisfaction with past resolutions.

        ### 2. Equipment or Facility Concerns
        - Reports of broken, malfunctioning, unsafe, or out-of-order equipment.
        - Complaints about facility conditions (e.g., cleanliness, lighting, air conditioning, heating), or specific areas of the facility (e.g., restrooms, changing rooms).
        - Concerns about hazardous conditions within the facility (e.g., blocked exits, slippery floors).

        ### 3. Scheduling and Booking
        - Inquiries or disputes about class schedules, appointment times, cancellations, or booking errors (e.g., double bookings, missed sessions).
        - Requests to change or reschedule future bookings.

        ### 4. Billing and Membership Issues
        - Disputes regarding overcharges, billing errors, refunds, or payment methods.
        - Questions about membership plans, pricing, subscription terms, or refund policies.

        ### 5. Health, Safety, and Security
        - Reports of injuries or medical incidents related to studio activities.
        - Inquiries about safety protocols, emergency procedures, or the availability of first-aid or emergency equipment.
        - Physical security threats (e.g., personal safety threats, security breaches, physical altercations).
        - Concerns about workplace safety, hazardous conditions, or emergency procedures.

        ### 6. Legal and Liability Concerns
        - Inquiries about the studio's liability policies, insurance coverage, or terms of service.
        - Legal disputes or concerns about potential legal actions against the studio.
        - Concerns about the mishandling of personal data or privacy breaches.

        ### 7. Marketing and Promotions
        - Questions about studio marketing campaigns, promotional offers, partnerships, or social media presence.
        - Inquiries regarding collaborations or events hosted by the studio.

        ### 9. High-Priority Complaints or Crisis Management
        - Complaints that could lead to business loss, negative reviews, or potential legal action.
        - Threats to escalate the issue publicly or pursue legal action.
        - Situations that could harm the studio’s reputation or require an official response to mitigate damage (e.g., public complaints, legal threats, PR issues).

        ### 10. Direct Contact Requests
        - Requests to speak with a manager, coach, or senior staff member for resolution.

        ### 11. Criminal Activity
        - Incidents involving violent or non-violent crimes (e.g., unlawful violence, encouragement of crimes).
        - Reports of sex-related crimes, including harassment or trafficking.
        - Reports of child sexual exploitation or any mention of abuse of children.

        ### 12. Ethical and Personnel Concerns
        - Incidents involving unethical behavior or breaches of studio policies.
        - Employee-related issues (e.g., harassment claims, discrimination, disciplinary actions).
        - Reports of financial fraud, theft, or discrepancies.

        ### 13. Hate Speech, Suicide, or Self-Harm
        - Mentions of self-harm, suicide, or encouragement of such actions.
        - Hate speech or demeaning remarks based on personal characteristics (e.g., race, religion, gender).
        """
        return escalation_criterion

    def get_response(self) -> str:
        response = """
        I understand this requires special attention, and I’m sending your concern to our team. They’ll contact you soon, or you can reach them directly at (843) 798-9599 during business hours. For any immediate medical emergencies, please call 911.
        """
        return response
