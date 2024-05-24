from typing import List

from ai.assistants.gym_assistant import get_gym_assistant


# TODO move this to a Data Access Layer, and look up the user ID from the database based on the phone numbers
def get_user_id_from_sms(to_number: str, from_number: str):
    return "client_phone_number_" + to_number + "_user_phone_number_" + from_number


def assistant_from_sms(to_number: str, from_number: str):
    user_id = get_user_id_from_sms(to_number, from_number)

    print(f"User ID: {user_id}")

    assistant = get_gym_assistant(
        user_id=user_id,
        debug_mode=False,
    )

    # Get the run id
    assistant_run_ids: List[str] = assistant.storage.get_all_run_ids(user_id=user_id)
    assistant_run_id = None
    if not assistant_run_ids or len(assistant_run_ids) == 0:
        assistant_run_id = assistant.create_run()
    else:
        assistant_run_id = assistant_run_ids[0]
    assistant.run_id = assistant_run_id

    print(f"Assistant run ID: {assistant_run_id}")

    return assistant
