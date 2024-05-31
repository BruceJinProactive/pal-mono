from ai.assistants.pizza_assistant import get_pizza_assistant

assistant = get_pizza_assistant(debug_mode=True)

text = input()
while text:
    assistant.print_response(message=text)
    text = input()
