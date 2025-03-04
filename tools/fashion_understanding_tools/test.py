import argparse
import datetime
import random

import requests


def get_textual_response(prompt, endpoint: str = "local"):
    hash = random.getrandbits(128)  # create new user

    def query(prompt: str, endpoint: str):
        # endpoint = "http://localhost:8000/v1/chat/"

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
                "context": "",
            }
        }
        start = datetime.datetime.now()
        response = requests.post(endpoint, json=payload)
        end = datetime.datetime.now()
        execution_time = end - start
        print("Response:")
        print(response.json())
        json_res = response.json()

        print(f"Total execution time: {execution_time.total_seconds()} seconds")
        image_urls = []
        for message in json_res["messages"]:
            if message.get("media", None) is not None:
                image_urls.append(message["media"]["url"])

        final_response = json_res["messages"][0]["text"]["body"]

        print(final_response)
        print(f"Image URLs: {image_urls}")
        return final_response

    query(prompt, endpoint)


if __name__ == "__main__":
    # Usage: python3 -m tools.fashion_understanding_tools.test -e <local|lat|stg>
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
        "-S",
        "--structured_output",
        action="store_true",
        default=False,
        help="Whether to return structured output",
    )
    args = parser.parse_args()

    endpoint = args.endpoint

    # Obtain agent response and recommendation
    chat_history = []
    query = """Hi! I'm looking for a new maxi dress for a cocktail party. Chic. No specific preference for color. Select a color for me. Any recommendations?"""

    # Instruction prompt for evaluation
    prompt = f"""
Call `_recommendation_logic` with the exact parameters as below:
```
query = {query}
return_json = True
```

Returned output should contain no new line characters.
"""
    if not args.structured_output:
        prompt = query
    get_textual_response(prompt=prompt, endpoint=endpoint)


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
