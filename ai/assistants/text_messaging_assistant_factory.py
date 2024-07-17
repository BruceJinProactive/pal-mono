from typing import List

from ai.assistants.gym_assistant import get_gym_assistant
from data_access_layer.dal_user_id import get_user_id_from_sms


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
