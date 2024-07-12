import pandas as pd
import streamlit as st
from phi.assistant.run import AssistantRun
from phi.storage.assistant.postgres import PgAssistantStorage
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config, user_ui
from db.session import get_db
from db.settings import db_settings
from services.admin_service import get_account

set_page_config()
st.title("Messages")


class Row:
    def __init__(self, run: AssistantRun):
        memory_json = run.memory
        self.user_id = memory_json.get("user_id")
        self.created_at = run.created_at
        self.memories = memory_json.get("memories")
        self.chat_history = memory_json.get("chat_history")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "created_at": self.created_at,
            "memories": str(self.memories),
            "chat_history": len(self.chat_history),
        }


def get_all_messages():
    db = next(get_db())
    account = get_account(db, account_name=user.account_name)
    if account is None:
        raise ValueError("Account not found")
    if not account.projects:
        raise ValueError("No projects found for this account")
    project_id = account.projects[0].id
    storage_table_name = f"project_{project_id}_storage"
    storage = PgAssistantStorage(
        table_name=storage_table_name,
        db_url=db_settings.get_db_url(),
    )
    all_runs = storage.get_all_runs()
    rows = []
    for run in all_runs:
        rows.append(Row(run))
    return rows


def main() -> None:
    rows = get_all_messages()
    rows_dicts = [row.to_dict() for row in rows]
    df = pd.DataFrame(rows_dicts)

    # Display the dataframe in a full-width container
    with st.container():
        st.dataframe(df, height=400, use_container_width=True)

    # Input field to accept the row number
    row_number = st.text_input("Enter the row number to view chat history:", "")

    # Validate the input and display chat history if valid
    if row_number:
        try:
            row_number = int(row_number)
            if 0 <= row_number < len(df):
                selected_row = df.iloc[row_number]
                selected_row_obj = rows[row_number]

                st.write("---")  # Add a separator
                st.write(f"Chat History for User ID {selected_row['user_id']}:")

                chat_history_df = pd.DataFrame(selected_row_obj.chat_history)
                st.dataframe(chat_history_df, use_container_width=True)
            else:
                st.error(
                    "Invalid row number. Please enter a number within the range of the table."
                )
        except ValueError:
            st.error("Invalid input. Please enter a valid row number.")


if user.is_logged_in:
    main()
    user_ui()
else:
    switch_page("home")
