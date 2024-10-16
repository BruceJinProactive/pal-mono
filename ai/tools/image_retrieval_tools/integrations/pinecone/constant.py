"""Prompts for Image Retrieval using Pinecone."""

SYSTEM_PROMPT = """Based on the user's chat history, extract the most relevant information to identify what item the user is looking for. For example, if the chat history might contain phrases like "I need a dress for a wedding" and "I'm looking white dress", the expected output might be something like "A white dress for a wedding". Return ONLY the relevant information about the item. Not other text should be included."""

USER_PROMPT = """Here is the chat history: "{chat_history}". Please extract the most relevant information to identify what fashion item the user is looking for."""
