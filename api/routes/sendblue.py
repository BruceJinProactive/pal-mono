import http.client
import json
from os import getenv

from fastapi import APIRouter
from pydantic import BaseModel

from api.routes.endpoints import endpoints
from ai.assistants.text_messaging_assistant_factory import assistant_from_sms


######################################################
## Router for SMS
######################################################

sendblue_router = APIRouter(tags=["Sendblue"])

class SendBlueReceivedMessageModel(BaseModel):
    to_number: str
    from_number: str
    content: str
    media_url: str | None = None

@sendblue_router.post(endpoints.SENDBLUE)
async def sms_response(data: SendBlueReceivedMessageModel):
    """
    SENDBLUE Webhook to handle incoming SMS messages.
    """
    # Get the sent from number
    sent_from = data.from_number

    # Get the sent to number
    sent_to = data.to_number

    # Get the message body
    body = data.content

    # TODO: move these two lines to a controller module/service so this class only handles protocols with SendBlue, and other services for like Twilio only handles protocols with Twilio
    assistant = assistant_from_sms(to_number=sent_to, from_number=sent_from)
    reply = assistant.run(body, stream=False)

    # reply = f"Hello! {sent_from} sent to {sent_to}: {body}"
    send_blue_sms(sent_from, reply)

    return "Acknowledgement"

def send_blue_sms(to_number : str, content : str):
    body_dictionary = {
        'number': to_number,
        'content': content
    }
    post_data = json.dumps(body_dictionary)
    print('send_blue_sms: ' + post_data)

    conn = http.client.HTTPSConnection("api.sendblue.co")
    conn.request("POST", "/api/send-message", post_data,
    {
        'Content-Type': 'application/json',
        'sb-api-key-id': getenv("SENDBLUE_API_KEY"),
        'sb-api-secret-key': getenv("SENDBLUE_API_SECRET_KEY")
    })
    response = conn.getresponse()
    data = response.read()
    conn.close()
    print('send_blue_sms: response:'+ data.decode("utf-8"))

    return data
