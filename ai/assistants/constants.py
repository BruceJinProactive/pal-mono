"""
The name of the function to be called by OpenAI can have a maximum of 64 characters. 
Limiting to 64 is the industry standard for function names.
For readability and maintainability, it's best practice to keep function names under this limit.
As a guideline, ChatGPT suggests a maximum length of 50 characters for function names.
More from: https://platform.openai.com/docs/api-reference/assistants/createAssistant#assistants-createassistant-tools
"""

FUNCTION_NAME_LENGTH_LIMIT = 63
