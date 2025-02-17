import os
import re
import time
import traceback
import uuid
from typing import List, Optional, TypeVar

from agno.agent.agent import Agent
from agno.models.groq.groq import Groq
from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import llm, retrieval, task, tool
from llama_index.core import Settings, VectorStoreIndex
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.llms.groq import Groq as GroqLLM
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone
from pydantic import BaseModel

from agent.legacy.storage import get_storage
from tools.adora_tool.classes import AdoraAccessToken, CustomerInfo, Order
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

from . import _apis

ADORA_PAYMENT_URL = "https://pizzamyheart.adorapos.net/OnlineOrdering/OrderHubPayment/?storeKey={store_id}&orderId={order_id}"

T = TypeVar("T", bound=BaseModel)


@llm(name="extractor")
def llm_call(
    system_prompt: str, prompt: str, response_format: type[T] | None = None, name="tool"
) -> Optional[T]:
    # client = get_model(model_name=ModelName.MEDIUM)
    client = Groq(id="deepseek-r1-distill-qwen-32b")

    if response_format:
        system_prompt += """
        \n
        Structure your response as a dictionary, do not include "json" in the beginning
        of the response.
        """
    agent = Agent(
        model=client,
        agent_id=f"ordering-tools/{name}",
        session_id="test-session",
        add_history_to_messages=True,
        knowledge=None,
        debug_mode=True,
        response_model=response_format,
        system_message=system_prompt,
        num_history_responses=0,
        search_knowledge=False,
    )

    response = agent.run(prompt).content

    LLMObs.annotate(
        input_data=prompt,
        output_data=response,
        metadata={"system_prompt": system_prompt},
    )

    return response


class AdoraTool(Toolkit):
    def __init__(
        self,
        agent_id: uuid.UUID,
        account_id: uuid.UUID,
        account_name: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ):
        super().__init__(name="adora_tool")

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.validate_address)
        self.register(self.checkout_order)

        self.store_id = "9WHCV"

        self.agent_id = agent_id
        self.account_id = account_id
        self.account_name = account_name
        self.user_id = user_id
        self.session_id = session_id

        # TODO: This code is bad >:( Refactor once it works. (ToT)
        pc = Pinecone(os.getenv("PINECONE_API_KEY"))
        pinecone_index = pc.Index("agents")

        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index,
            namespace="pizzamyheart-menu-9WHCV-docs-2025-02-13",
        )

        Settings.embed_model = CohereEmbedding(
            api_key=os.getenv("COHERE_API_KEY"),
            model_name="embed-english-v3.0",  # current v3 models support multimodal embeddings
        )

        # set groq llm
        llm = GroqLLM(model="llama-3.3-70b-versatile")
        Settings.llm = llm

        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=Settings.embed_model,
        )

        self.query_engine = index.as_query_engine(
            similarity_top_k=10, similarity_cutoff=0.3
        )

    @tool
    def check_online_ordering_status(self) -> str:
        """
        Check the online ordering status of the store.

        Returns:
            str: The online ordering status of the store.
        """
        # For test store, we always return "active" status
        if self.store_id == "9WHCV":
            return "The store is open for online ordering."

        try:
            api_key = get_client_secret_with_fallback("PIZZAMYHEART_ADORA_API_KEY")
            api_secret = get_client_secret_with_fallback(
                "PIZZAMYHEART_ADORA_API_SECRET"
            )
            bearer_token = _apis.get_adora_pos_auth_token(api_key, api_secret)
            if not bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            status = _apis.get_online_ordering_status(bearer_token, self.store_id)

            if not status:
                logger.error(
                    "[AdoraTool.check_online_ordering_status] Failed to get online ordering status."
                )
                return "Failed to check the online ordering status, please try again."

            return status

        except Exception as e:
            logger.error(f"Error in checking online ordering status: {e}")
            return "Error in checking online ordering status."

    @tool
    def get_store_info(self, store_id: str, date: str) -> str:
        """
        Get the store information by given store id and target business date.

        Args:
            store_id (str): The store id
            date (str): The target business date

        Returns:
            str: The store information of if store is open
        """
        try:
            store_id = self.store_id
            return f"STORE ID {store_id} IS OPEN on {date}"
        except Exception as e:
            logger.error(f"Error getting store info: {e}")
            return "Error getting store info."

    @tool
    def validate_address(self, args: List[str]) -> str:
        try:
            raise NotImplementedError
        except Exception as e:
            logger.error(f"Error in validating address: {e}")
            return "Error in validating address."

    @task
    def _get_content(self, text: str) -> str:
        match = re.search(r"<content>\s*(.*?)\s*</content>", text)
        return match.group(1) if match else ""

    @retrieval
    def _get_chat_history(self) -> str:
        try:
            # db_session = db.get_db()

            # logger.info(db_session)
            # if not db_session:
            #     logger.error(
            #         "Failed to get database session for\n"
            #         f"Account Name: {self.account_name}\n"
            #         f"Account ID: {self.account_id}\n"
            #         f"Agent ID: {self.agent_id}\n"
            #         f"User ID: {self.user_id}\n"
            #         f"Session ID: {self.session_id}"
            #     )
            #     return "Failed to get database session."

            try:
                # # TODO: Defer import to avoid circular import
                # from services.admin_service import (
                #     get_messages_by_conversation_id,
                # )

                # messages = get_messages_by_conversation_id(
                #     db_session, self.user_id, self.session_id
                # )
                storage = get_storage(self.account_name)
                agent_session = storage.read(str(self.session_id), str(self.user_id))

                if not agent_session:
                    logger.error(
                        "Agent session not found for\n"
                        f"Account Name: {self.account_name}\n"
                        f"Account ID: {self.account_id}\n"
                        f"Agent ID: {self.agent_id}\n"
                        f"User ID: {self.user_id}\n"
                        f"Session ID: {self.session_id}"
                    )
                    return "Agent session not found"

                messages = agent_session.memory["runs"]  # type: ignore

                chat_history = ""

                for message in messages:
                    role = message["message"]["role"]
                    if role == "user":
                        user_content = self._get_content(message["message"]["content"])  # type: ignore
                        chat_history += f"**[User]**\n{user_content}\n\n"
                        chat_history += (
                            f"**[Assistant]**\n{message['response']['content']}\n\n"
                        )
                    else:
                        logger.info(
                            f"Skipping appending message to chat history:\n{message}"
                        )

                LLMObs.annotate(output_data=chat_history)

                return chat_history

            except ValueError:
                logger.error(
                    "Conversation history not found for\n"
                    f"Account ID: {self.account_id}\n"
                    f"Agent ID: {self.agent_id}\n"
                    f"User ID: {self.user_id}\n"
                    f"Session ID: {self.session_id}"
                )
                return "Conversation history not found."

        except Exception as e:
            error_msg = "Error in getting chat history"
            logger.error(f"{error_msg}: {e}")
            return error_msg

    @retrieval
    def _get_relevant_docs(self, chat_history: str) -> str:
        response = self.query_engine.query(chat_history)

        context = ""
        output_data = []
        for node in response.source_nodes:
            context += f"{node.text}\n\n"
            output_data.append({"id": node.id_, "text": node.text})

        LLMObs.annotate(input_data=chat_history, output_data=output_data)

        return context

    @task(name="_fulfill_order [via Adora API]")
    def _fulfill_order(self, order: Order, bearer_token: AdoraAccessToken) -> str:
        LLMObs.annotate(input_data=order)

        json_payload = order.model_dump_json(by_alias=True)
        validated_order = _apis.validate_order(
            bearer_token=bearer_token, json_payload=json_payload
        )

        logger.info(f"[AdoraTool.checkout_order] Validated order: {validated_order}")

        if not validated_order or not validated_order.key:
            return "Failed to validate order. Please try again."

        # save validated order in Adora system, get order ID
        logger.info("[AdoraTool.checkout_order] Saving validated order...")

        saved_order = _apis.save_validated_order(bearer_token, validated_order.key)

        if not saved_order or not saved_order.orderID:
            return "Failed to place order. Please try again."

        # delay 1 second to allow Adora to synchronize the order
        time.sleep(1)

        if saved_order:
            text_payment_url = ADORA_PAYMENT_URL.format(
                store_id=self.store_id,
                order_id=saved_order.orderID,
            )
        else:
            logger.debug(
                f"[AdoraTool.checkout_order] Failed to place order. Saved order ID: {saved_order.orderID if saved_order else 'NO SAVED ORDER'}"
            )
            return "The service is busy. Please try again."

        return f"""Your order is pending!
        Please head to the payment url to finalize your order!
        {text_payment_url}
        
        Order Summary:
        {order.items}

        Subtotal: {validated_order.subTotal}
        Sales Tax: {validated_order.taxAmount}
        Order Total: {validated_order.total}
        """

    @tool
    def checkout_order(self) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat history. This function should be invoked when the user asks to checkout, pay, place the order, etc.

        Returns:
            str: The checkout order details including the payment URL.
        """
        chat_history = self._get_chat_history()
        logger.info(f">>> Chat history:\n{chat_history}")

        context = self._get_relevant_docs(chat_history)  # type: ignore
        logger.info(f">>> Context:\n{context}")

        # Extract structured data from natural language
        try:
            system_prompt = """You are an expert at structured data extraction. 
            You will be given the chat history and relevant context.
            You goal is to convert it into the given structure.

            **Instructions on how to perform the task:**
            First, identify the list of items that the user wants to order from the chat history.
            Then, make sure that the quantities for each order are correct.
            Then, make sure that the modifiers for every order are identified, if they were mentioned in the chat history.
            Finally, map the items, names, modifiers, etc., that you just identified from the english language to the structured data format that is required by the Adora API using the provided context.
            Importantly, some of the provided context might be irrelevant to the order, in which case you should ignore it.
            

            **IMPORTANT RULES:**
            - Do NOT make assumptions or fabricate data
            - Leave fields as None/null if the information is not explicitly mentioned
            - Do not infer values or make educated guesses
            - Only extract information that is directly stated
            - Maintain exact values as mentioned (don't modify numbers or text)
            - For phone numbers, only extract if a complete number is provided
            - For addresses, only extract if all required components are present

            If unsure about any field, leave it empty rather than guessing."
            """
            user_prompt = f"""
            Please construct the structured order from the following information:

            **Menu items with the corresponding modifiers**
            {context}

            **Chat History**
            {chat_history}
            """

            # current version of the datadog llmobs does not support pyright
            order = llm_call(
                system_prompt=system_prompt,  # type: ignore
                prompt=user_prompt,  # type: ignore
                response_format=Order,  # type: ignore
            )

            if not isinstance(order, Order):
                logger.error(
                    "[AdoraTool.checkout_order] Failed to extract structured data. Most likely validation schema was not fulfilled."
                )
                return "Failed to extract structured data. Please try again."

            logger.info(f"Extracted structured data: {order}")
            logger.info(f"Extraced structured data type: {type(order)}")

            api_key = get_client_secret_with_fallback("PIZZAMYHEART_ADORA_API_KEY")
            api_secret = get_client_secret_with_fallback(
                "PIZZAMYHEART_ADORA_API_SECRET"
            )
            bearer_token = _apis.get_adora_pos_auth_token(api_key, api_secret)
            if not bearer_token:
                return "Failed to authenticate ordering tool. Please reach out to our support team at help@proactiveailab.com for assistance."

            # Override store id
            order.store_id = self.store_id

            # Manually set customer info for now
            order.customer = CustomerInfo(
                first_name="Jimmy",
                last_name="ProactiveAILab (via Jimmy)",
                phone_number="(555)555-5555",
                email="jimmythesurfer@proactiveailab.com",
            )

            # If order comment is None, set it to an empty string
            order.order_comment = "" if not order.order_comment else order.order_comment

            # Move order_items to the items field which fulfills the Adora API requirements
            items = []
            for order_item in order.order_items:
                items.append({"group": [order_item]})
            order.items = items

            return self._fulfill_order(order, bearer_token)  # type: ignore

        except Exception as e:
            logger.error(f"Error in extracting structured data: {e}")
            logger.error(traceback.format_exc())
            return "Error in extracting structured data."
