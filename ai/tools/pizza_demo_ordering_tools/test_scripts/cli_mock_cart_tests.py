from ai.assistants.pizza_assistant import get_pizza_assistant
from ai.tools.pizza_demo_ordering_tools.adapters.mock_cart import reset_mock_cart

# clear output file
output_file_path = "mock_cart_test_chat_history.txt"
with open(output_file_path, "w") as f:
    f.write("")


def run_test(test_case):
    user_id = test_case[0]
    reset_mock_cart(user_id)
    assistant = get_pizza_assistant(user_id=user_id, debug_mode=False, new_run=True)
    for message in test_case[1:]:
        if message != "":
            assistant.print_response(message=message, stream=False)

    with open(output_file_path, "a") as f:
        f.write(
            f"-------------------------------\n{test_case[0]}:"
            + assistant.memory.get_formatted_chat_history()
            + "\n"
        )


def run_tests(test_files):
    for test_file in test_files:
        with open(f"ai/tools/tests/{test_file}", "r") as f:
            content = f.read()
            test_cases = content.split("~")
            for test_case in test_cases:
                if test_case != "":
                    run_test(test_case.split("\n"))


test_files = [
    "checkout.txt",
    "magical_moment.txt",
    "ordering.txt",
    "address.txt",
]

if __name__ == "__main__":
    run_tests(test_files)
