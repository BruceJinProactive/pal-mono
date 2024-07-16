from ai.assistants.pizza_assistant import get_pizza_assistant

# The user_id can be any random string.
assistant = get_pizza_assistant(user_id="random_string", debug_mode=True)

text = input()
while text:
    assistant.print_response(message=text)
    text = input()
