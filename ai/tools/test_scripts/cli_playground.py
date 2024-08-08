from ai.assistants.pizza_assistant import get_pizza_assistant

# The user_id can be any random string.
assistant = get_pizza_assistant(user_id="random_string", debug_mode=True, new_run=True)

print("Enter user message:")
text = input()
while text:
    assistant.print_response(message=text, stream=False)
    print("Enter user message:")
    text = input()

with open("chat_history.txt", "a") as f:
    f.write(assistant.memory.get_formatted_chat_history())
