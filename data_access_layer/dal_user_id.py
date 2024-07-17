def get_user_id_from_sms(to_number: str, from_number: str):
    """
    returns consistent user id based on account and user phone numbers
    """
    # TODO: add phone numbers to DB and look up the account ID from the database based on the phone numbers and return {Account_UserPhone} format.
    return "client_phone_number_" + to_number + "_user_phone_number_" + from_number


def get_user_id_for_account_name_user_email(account_name: str, user_email: str):
    """
    returns consistent user id based on account name and user email address
    """
    # TODO: look up account ID from account name after we have scripts to add accounts to our demos and use Account ID instead of Account Name
    return "account_name_" + account_name + "_user_email_" + user_email
