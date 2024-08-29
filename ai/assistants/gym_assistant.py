import datetime
import json
import logging

import httpx
from phi.assistant import Assistant
from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.json import JSONKnowledgeBase
from phi.knowledge.pdf import PDFKnowledgeBase
from phi.knowledge.website import WebsiteKnowledgeBase

# from phi.llm.openai.like import OpenAILike
from phi.storage.assistant.postgres import PgAssistantStorage
from phi.tools import Toolkit
from phi.vectordb.pgvector import PgVector2

from ai.llm import LLM, get_llm
from ai.settings import ai_settings
from db.session import db_url

# from phi.llm.openai import OpenAIChat


# Set up logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True


mindzero_knowledge_base = CombinedKnowledgeBase(
    sources=[
        ## removing the RAG example Thai Recipes PDF
        # PDFUrlKnowledgeBase(urls=["https://phi-public.s3.amazonaws.com/recipes/ThaiRecipes.pdf"]),
        PDFKnowledgeBase(path="data/mindzero/pdfs"),
        JSONKnowledgeBase(path="data/mindzero/jsons"),
        WebsiteKnowledgeBase(
            urls=[
                "https://www.mindzero.com/terms-of-service/",
                "https://www.mindzero.com/privacy-policy/",
            ]
        ),
    ],
    vector_db=PgVector2(
        db_url=db_url,
        # Store the embeddings in ai.pdf_documents
        collection="mindzero_documents",
        embedder=OpenAIEmbedder(model=ai_settings.embedding_model),
    ),
    # 2 references are added to the prompt
    num_documents=2,
)


class BookingTools(Toolkit):
    def __init__(self):
        super().__init__(name="booking_tools")
        self.register(self.get_class_sessions)
        # self.register(self.post_class_sessions)

    def get_class_sessions(self, num_days: int = 7) -> str:
        """Use this function to answer any questions regarding class session availability.

        Args:
            num_days (int): Number of days in advance to look for. Defaults to 7 if user doesn't supply.

        Returns:
            str: JSON string of class session availability.
        """
        # Date range to search within: [Today, Today+num_days]
        min_date = datetime.datetime.today().strftime("%Y-%m-%d")
        max_date = datetime.date.today() + datetime.timedelta(days=num_days)

        response = httpx.get(
            f"https://mindzero.marianatek.com/api/class_sessions?include=employee_public_profiles%2Clayout%2Ctags&location=48717&max_date={max_date}&min_date={min_date}&ordering=start_datetime&page_size=20"
        )
        data = response.json()["data"]

        # Returns whether the session is in the future (True) or not (False)
        def date_in_the_future(session_date_str):
            curr_date = datetime.datetime.now(datetime.timezone.utc)
            session_date = datetime.datetime.strptime(
                session_date_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=datetime.timezone.utc)

            return curr_date < session_date

        # Filter through the API response to gather and reformat desired data.
        result = []
        for entry in data:
            # Filter out sessions in past.
            if date_in_the_future(entry["attributes"]["start_datetime"]):
                new_entry = {}
                new_entry["start_date"] = entry["attributes"]["start_date"]
                new_entry["start_time"] = entry["attributes"]["start_time"]
                new_entry["class_id"] = entry["id"]
                new_entry["available_spots_count"] = len(
                    entry["attributes"]["available_spots"]
                )
                new_entry["class_type"] = entry["attributes"]["class_type_display"]
                new_entry["duration"] = entry["attributes"]["duration"]
                new_entry["instructor"] = entry["attributes"]["instructor_names"]
                result.append(new_entry)

        return json.dumps(result)


def create_gym_assistant(
    llm_name: LLM,
    user_id: str,
    new_run: bool = False,
    debug_mode: bool = False,
) -> Assistant:
    """Get an Autonomous Assistant with gym classes schedule knowledge and user past class attendances, and can help book classes."""

    # set up specific storage
    assistant_name = ""
    if llm_name == LLM.OPENAI:
        assistant_name = "gym_assistant"
    elif llm_name == LLM.MODAL:
        assistant_name = "mindzero_assistant"
    elif llm_name == LLM.ROUTER:
        assistant_name = "mindzero_assistant"

    gym_assistant_storage = PgAssistantStorage(
        db_url=db_url,
        # TODO: make table name configurable from customer config read from DB
        table_name=assistant_name,
    )

    run_id = None
    if not new_run:
        run_ids = gym_assistant_storage.get_all_run_ids(user_id=user_id)
        run_id = run_ids[0] if run_ids else None

    # set up assistant with specific storage
    assistant = Assistant(
        name=assistant_name,
        run_id=run_id,
        user_id=user_id,
        llm=get_llm(llm_name),
        storage=gym_assistant_storage,
        add_chat_history_to_messages=True,
        num_history_messages=20,
        knowledge_base=mindzero_knowledge_base,
        add_references_to_prompt=True,
        # Enable monitoring on phidata.app
        # monitoring=True,
        tools=[BookingTools()],
        use_tools=True,
        show_tool_calls=debug_mode,  # show tool calls in debug mode
        search_knowledge=True,
        read_chat_history=False,
        debug_mode=debug_mode,
        build_default_system_prompt=False,
        system_prompt="""
You are a MINDZERO studio manager named Maxine. You are the responsible studio manager and a beloved coach at MINDZERO here to keep all your customers happy! Your mission? To dish out responses that are precise, concise, and oh-so-relatable in a casual tone. You really care about all of her customers, new and old. You treat her customers like her own family and best friends.

You are good at telling users more about classes and sessions at the MINDZERO gym located in Myrtle Beach, South Carolina. You also want to tell users about the new studio opening this summer in Mount Pleasant and the special promotion for the new studio members. MINDZERO is a fast growing wellness studio with a loyal fan base.

For any of the following health related topics, please ask the user to consult with their doctor
<health_related_topics>
Has your doctor ever told you to avoid cold plunge, ice baths, or saunas?
Has your doctor ever told you that you have a heart condition or high blood pressure?
Have you ever had a heart attack or stroke?
Do you have a pacemaker?
Are you currently pregnant?
Have you had recent unexplained chest pain?
Have you experienced recent dizziness?
Do you have any mental health disorders?
</health_related_topics>

Here are the instructions you must follow:
<instructions>
1. Only answer topics related to the MINDZERO wellness studio.
2. Start the conversation by introducing yourself if you haven't done so, and ask "what's your name". And answer user's questions in the same response.
3. Always address users by their name in this conversation if you know their name.
4. Be concise, keep your answers in 1-3 sentences.
5. When users show interest to sign up, offer the users to sign up for a MINDZERO gym session at this url 'https://www.mindzero.com/' if they are not a member yet.
6. And remember to mention the first session is free for new members.
7. Only recommend Guided Experiences to first time new members. Other sessions for experienced members.
8. Your role is to answer any questions and encourage the user to take classes and workout.
9. Use emojis at the right time but keep the style minimal.
10. Avoid generic reassurances when starting and ending your response.
11. Do not start your sentences with Hey, Boah, Whoo, or any similar greeting.
12. Always be polite and pleasant.
</instructions>
""",
        #     description="You are Maxine, a MINDZERO AI Agent. You are representing the owner and brand. You are the perfect studio manager and a beloved coach at MINDZERO. You really care about all of her customers, new and old. You treat her customers like her own family and best friends.",
        #     instructions=[
        #         "Only answer topics about classes and sessions at the MINDZERO gym.",
        #         "Keep your answers under 5 sentences.",
        #         "Add emojis to your messages.",
        #         "Address of the MINDZERO Gym is 3848 S Kings Hwy, Myrtle Beach, SC 29577",
        #         """
        #             The hours of operations are:
        #             Tuesday
        #             6:45AM-9PM
        #             Wednesday
        #             6:45AM-9-PM
        #             Thursday
        #             6:45AM-9PM
        #             Friday
        #             6:45AM-7PM
        #             Saturday
        #             9AM-7PM
        #             Sunday
        #             10AM-7PM
        #             Monday
        #             6:45AM-9PM
        #         """,
        #         # "Offer to help the user to book gym classes, and pretend you can book gym classes.",
        #         "Offer the users to sign up for a MINDZERO gym session at this url 'https://www.mindzero.com/book-now/' if they are not a member yet.",
        #         "Use words of affirmation to encourage the user to take classes and workout.",
        #     ],
        #     extra_instructions=["""
        # Use this information from the knowledge base to determine your response if it helps:
        # <knowledge_base>
        # 1. The hours of operations are:
        #     Tuesday
        #     6:45AM-9PM
        #     Wednesday
        #     6:45AM-9-PM
        #     Thursday
        #     6:45AM-9PM
        #     Friday
        #     6:45AM-7PM
        #     Saturday
        #     9AM-7PM
        #     Sunday
        #     10AM-7PM
        #     Monday
        #     6:45AM-9PM
        # 2. MIИDZER0 Tagline:
        #     INVOKE YOUR POWER
        #     PAUSE FROM THE CHAOS AND FIND INNER PEACE AND PRESENCE
        #     Bring Your Mind To Zero
        # 3. MIИDZER0 Brand Story:
        #     MIИDZER0 was created in the middle of a hot and extremely intense training session in the hills of California. Our two original founders signed up for a 75 hour long challenge where they were pushed to their physical and mental limits.
        #     Although many people broke down and dropped out, David Semerad and Bill Miller successfully completed the course and came out physically healthier and more enlightened than either had anticipated.  It was through this arduous process the two became friends. As David and Bill’s friendship grew and they looked back on that 75 hour long challenge, they realized what got them to the finish line wasn’t their physical or mental strength but the rest and recovery.  At that point, they knew what they had to do. They called George Becker and Dr. Heather Grimm, and MIИDZERØ was created.
        # 4. MIИDZER0 Contact Information:
        #     3848 South Kings Highway
        #     Myrtle Beach, SC 29577
        #     Phone: +1 (843) 798-9599
        #     Email: hello@MIИDZER0.com
        # 5. MIИDZERØ Session Pricing
        #     Membership
        #     Reset Membership $99.00/month and includes 4 Sessions/Month
        #     Elevate Membership $159.00/month and includes 8 Sessions/Month
        #     Classpacks
        #     $59 for 1 session
        #     $199 for 5 sessions
        #     $349 for 10 sessions
        #     $559 for 20 sessions
        # 6. MIИDZERØ Promotional Session Pricing
        #     First Session Free
        #     Relaxation Passport $79.00: Enjoy a week pass (7 consecutive days) for a session of your choice each day. (In the event of a late cancellation, a $10 reservation fee applies or a no-show, a $15 reservation fee applies)
        #     Pre-sale at new location: founding membership. Only pay 20% today to lock-in a lifetime membership discount.
        # </knowledge_base>
        #     """
        #     ],
        assistant_data={"assistant_type": "autonomous"},
    )

    # Not sure why it's recreated every time
    # assistant.knowledge_base.load(recreate=True)

    return assistant


def get_gym_assistant(
    user_id: str,
    new_run: bool = False,
    debug_mode: bool = False,
) -> Assistant:
    return create_gym_assistant(LLM.ROUTER, user_id, new_run, debug_mode)
