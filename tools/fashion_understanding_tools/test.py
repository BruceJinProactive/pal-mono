import argparse
import datetime
import random

import requests

#####################
# Usage: python3 -m tools.fashion_understanding_tools.test -e <local|lat|stg> -I
# Set -I if you want to communicate with the agent multiple times in one conversation
# Example: python3 -m tools.fashion_understanding_tools.test -e local -I
#####################


def query(prompt: str, endpoint: str, hash: int = random.getrandbits(128)):

    endpoints = {
        "local": "http://localhost:8000/v1/chat/",
        "lat": "http://pal-mono-lat-api-lb-1443082111.us-west-1.elb.amazonaws.com/v1/chat/",
        "stg": "http://pal-mono-stg-api-lb-1164693723.us-west-1.elb.amazonaws.com/v1/chat/",
    }

    if endpoint not in endpoints:
        print("Invalid endpoint")
        return
    endpoint = endpoints[endpoint]

    payload = {
        "message": {
            "author_type": "user",
            "sender_identifier": f"demo-user-{hash}",
            "recipient_identifier": "windsor-default",
            "channel": "api",
            "broker": None,
            "type": "text",
            "text": {"body": prompt},
            "metadata": {},
            "context": "",
        }
    }
    start = datetime.datetime.now()
    response = requests.post(endpoint, json=payload)
    end = datetime.datetime.now()
    execution_time = end - start

    json_res = response.json()
    print(json_res)
    print(f"Total execution time: {execution_time.total_seconds()} seconds")
    image_urls = []
    for message in json_res["messages"]:
        if message.get("media", None) is not None:
            image_urls.append(message["media"]["url"])

    final_response = json_res["messages"][0]["text"]["body"]

    print(final_response)
    print(f"Image URLs: {image_urls}")
    return final_response


def get_textual_response(prompt, endpoint: str = "local"):
    hash = random.getrandbits(128)  # create new user
    query(prompt, endpoint, hash)


def get_textual_response_interactive(endpoint: str = "local"):
    hash = random.getrandbits(128)  # create new user
    user_query = input("Enter your query. Type q/quit to exit: ")

    while user_query.lower() not in ["q", "quit"]:
        query(user_query, endpoint, hash)
        user_query = input("Enter your query. Type q/quit to exit: ")


if __name__ == "__main__":

    # Parse arguments
    parser = argparse.ArgumentParser(description="Test Fashion Recommendation Logic")
    parser.add_argument(
        "-e",
        "--endpoint",
        type=str,
        default="local",
        help="API endpoint to test. Options: local, lat, stg",
    )
    parser.add_argument(
        "-I",
        "--interactive",
        action="store_true",
        default=False,
        help="Whether to run in interactive mode",
    )
    args = parser.parse_args()

    # Set endpoint
    endpoint = args.endpoint

    # If run in interactive mode, allow user to input multiple queries
    if args.interactive:
        get_textual_response_interactive(endpoint=endpoint)
        exit()

    # Obtain agent response and recommendation
    chat_history = []
    user_query = """Hi! I'm looking for a new maxi dress for a cocktail party. Chic. No specific preference for color. Select a color for me. Any recommendations?"""
    get_textual_response(prompt=user_query, endpoint=endpoint)


############################    OLD TEST CASE    ############################
# chat_history = [
#     {
#         "role": "user",
#         "content": "Hi! I'm looking for a new outfit for a party. Any recommendations?",
#     },
#     {
#         "role": "assistant",
#         "content": "Hello! Sure, I'd love to help. Could you tell me more about the party? Is it formal, semi-formal, or casual?",
#     },
#     {
#         "role": "user",
#         "content": "It's a semi-formal event, and I really want to make a good impression. It's indoors and in the evening.",
#     },
#     {
#         "role": "assistant",
#         "content": "Got it. For a semi-formal indoor event, you could wear a tailored blazer with a crisp button-down shirt and slim-fit pants. Do you have any color preferences or style inspirations you want to incorporate?",
#     },
#     {
#         "role": "user",
#         "content": "I usually prefer neutral colors like black, gray, or navy. I’d like something that’s both comfortable and chic.",
#     },
#     {
#         "role": "assistant",
#         "content": "In that case, a navy blazer paired with black or charcoal pants would look polished. You could add a subtle pop of color with a pocket square or a statement accessory. Would you like some shoe suggestions as well?",
#     },
# ]

# query = "Sounds great! I'd like to see some shoes that would complement the outfit."

##############################################################################
