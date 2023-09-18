# --------------------
# Imports & Initial Configuration
# --------------------

import os
import json
import time
import openai
import vonage
import random
import asyncio
import requests
import pinecone
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta  
from fastapi.responses import FileResponse
from langchain.vectorstores import Pinecone
from fastapi import FastAPI, Request, Query
from fastapi import FastAPI, BackgroundTasks
from langchain.embeddings.openai import OpenAIEmbeddings

app = FastAPI()

docker_url = "YOUR_DOCKER_URL" # Can't be localhost, has to be public URL. For testing you can use a tunneling service to expose localhost port to internet and use this URL.
PRIVATE_KEY_PATH = "./env/private.key" # Your Vonage Private Key
TO_NUMBER = "+61470273821"
VONAGE_NUMBER = "+61480046465"
conversations = {}
processed_recordings = set()
utc_plus_ten = (datetime.utcnow() + timedelta(hours=10)).isoformat()
print(utc_plus_ten)
print(datetime.utcnow().isoformat())

with open(PRIVATE_KEY_PATH, 'r') as file:
    PRIVATE_KEY = file.read()

# --------------------
# Configuration Mappings
# --------------------

availability_type_ids_dict = {
    "Dr Eugene Tshibangu (standard appointment)": 299974,
    "Dr Karim Ahmed (standard appointment)": 422093,
    "Dr Eugene Tshibangu (long appointment)": 447400,
    "Dr Karim Ahmed (long appointment)": 449913,
    "physiotherapy": 571381,
    "dietitian": 588132,
}

doctor_ids_dict = {
    "Dr Eugene Tshibangu": 106141,
    "Dr Karim Ahmed": 117697,
    "Emily Robinson": 137026,
    "Dr Diaa Attallah": 137023
}

reason_ids_dict = {
    "Long Appointment": 78501,
    "Standard Appointment": 78264,
    "Dietitian Appointment": 115328,
    "Physiotherapy Appointment": 113450
}


# ----------------------------------------
# Global variables
# ----------------------------------------

from_number = None
call_status = None
uuid_to_phone = {}  # Global dictionary to maintain the relationship of UUID to from number 

# --------------------
# Utility Functions
# --------------------

@app.get("/webhooks/log")
async def log_event(request: Request):
    global call_status  # Tell Python we're referring to the global variable
    
    # Get the query parameters from the request and convert to a regular dictionary
    params = dict(request.query_params)
    
    # Extract the status value
    status = params.get("status", None)
    
    # Update the global call_status
    call_status = (status == "completed")

    # Log the entire request data
    log_entry = str(params) + "\n"
    
    # Append the log entry to a .txt file
    with open("logs/webhook_logs.txt", "a") as f:
        f.write(log_entry)

    print("Logged successfully\n\n")

def construct_encoded_url(iso_date_time, doctor_id, reason_id):
    """
    Constructs the appointment authentication URL for HotDoc based on the provided parameters.
    This version of the function also encodes the URL parameters.
    """
    
    base_url = "https://www.hotdoc.com.au/request/appointment/authenticate"
    params = {
        "clinic": 6848,
        "doctor": doctor_id,
        "for": "you",
        "history": "return-visit",
        "reason": reason_id,
        "timezone": "Australia/Sydney",
        "when": f"{iso_date_time}"
    }
    
    # Convert the params dictionary into a URL-encoded query string
    query_string = urllib.parse.urlencode(params)
    
    # Combine the base URL with the query string
    full_url = f"{base_url}?{query_string}"
    return full_url

def increment_date_range(start_date, end_date, days_increment=1):
    """
    Increments both the start and end dates by a certain number of days.
    """

    start_date_dt = datetime.fromisoformat(start_date)
    end_date_dt = datetime.fromisoformat(end_date)

    # Shift both dates by the specified increment
    start_date_dt += timedelta(days=days_increment)
    end_date_dt += timedelta(days=days_increment)

    return start_date_dt.isoformat(), end_date_dt.isoformat()


# --------------------
# API Endpoints
# --------------------

@app.get("/audio/temp_audio_file.mp3")
async def get_audio():
    file_path = Path("audio/temp_audio_file.mp3")
    return FileResponse(file_path, media_type="audio/mpeg")

# --------------------
# OpenAI Functions
# --------------------

async def transcribe_audio(audio_file_path):
    with open(audio_file_path, 'rb') as audio_file:
        transcription = openai.Audio.transcribe("whisper-1", audio_file, prompt="iron, infusion, Chisholm, Eugene, Tshibangu, Karim, Ahmed, Diaa, iron infusion, slot, standard, standard appointment, next, appointment, implanon, long, long appointment")
    return transcription['text']


def context_lookup(query):

    os.environ['OPENAI_API_KEY'] = "YOUR_OPENAI_API_KEY"

    embeddings = OpenAIEmbeddings()

    index_name = "chmc-example"
    docsearch = Pinecone.from_existing_index(index_name, embeddings)

    docs = docsearch.similarity_search(query, namespace="chmc-information")
    
    results = []  # Store the results here
    
    if docs:
        for doc in docs:
            content = doc.page_content
            source = doc.metadata['source']
            results.append(f"Content: {content}\nSource: {source}\n--------")
    else:
        results.append("No results found for the query.")
    
    return "\n".join(results)

def fetch_time_slots(start_time, end_time, doctor_ids, availability_type_ids, retries=21):
    base_url = "https://www.hotdoc.com.au/api/patient/time_slots"

    doctor_id = doctor_ids_dict.get(doctor_ids)
    availability_type_ids = availability_type_ids_dict.get(availability_type_ids)

    # Construct the parameters
    params = {
        "start_time": start_time,
        "end_time": end_time,
        "timezone": "Australia/Sydney",
        "clinic_id": 6848,
        "availability_type_ids[]": availability_type_ids,
        "doctor_ids[]": doctor_id
    }

    print(params)

    headers = {
    "Accept": "application/au.com.hotdoc.v5",
    "Content-Type": "application/json; charset=utf-8",
    "App-Version": "4.0054.0",
    "App-Platform": "web",
    "App-Timezone": "Australia/Sydney",
    "Cookie": "_hjSessionUser_2015007=eyJpZCI6IjQwZWI0MTVlLWVlMDctNWZjNi1hOWU1LWE5N2YwZmM5MTEwMyIsImNyZWF0ZWQiOjE2NjkwMDM3NzgzMDYsImV4aXN0aW5nIjp0cnVlfQ==; _gcl_au=1.1.2073099095.1692404552; _gid=GA1.3.431411255.1692404552; __hstc=95078531.5d1d5b8722f50d003d84c2a93ffab16a.1692404552236.1692404552236.1692404552236.1; hubspotutk=5d1d5b8722f50d003d84c2a93ffab16a; __hssrc=1; _fbp=fb.2.1692404552674.123582009; _ga=GA1.3.703231684.1692404552; _ga_5QKYWLDYTJ=GS1.3.1692404552.1.0.1692404558.54.0.0; _ga_6ZEES7RX5V=GS1.1.1692404551.1.1.1692404561.50.0.0; rl_page_init_referrer=RudderEncrypt%3AU2FsdGVkX1%2BvCKK5bPaT9xZk2GmTai0H1l7LN7HXvlbpuRF8Xku8NfDCa%2F5gVaZa; rl_page_init_referring_domain=RudderEncrypt%3AU2FsdGVkX18%2FYKCVamgt%2Bi4NnZZyWJRKIJ1RbUBUntRg53rbJJ%2BstaU3RkI90XQR; rl_user_id=RudderEncrypt%3AU2FsdGVkX19RXpUOUrWB%2FBfis%2Bidd86Etcs1X25FLFA%3D; rl_trait=RudderEncrypt%3AU2FsdGVkX181IujdSTE%2FIDV8yXfmO9PgrBlQyqmK3FA%3D; rl_group_id=RudderEncrypt%3AU2FsdGVkX1%2Bk5uPJu%2FwNXTD1yZnxxgf1p7Bqbubb%2BwU%3D; rl_group_trait=RudderEncrypt%3AU2FsdGVkX18%2FECpEmHkVpWijsQLVzRbDGdVh2mKwX1w%3D; rl_anonymous_id=RudderEncrypt%3AU2FsdGVkX1%2BsskugNvQ6BqA96aopMJTjC1vZqBrpwGTX1Zit4PvwKxCvvitZl2JsxxC0Sti9ka%2FIMSgdWFPKAg%3D%3D; rl_session=RudderEncrypt%3AU2FsdGVkX1%2FFL3OmlbK5oDSuZ0RQcVPJtpkxBF%2B6pJ3%2Bn0e3o8dLYfsiDulMSzsYix9hA4xwdZ7fJ4k5z55hp8SA7SRZe2YPhUixluUoXbTIQ0NdW%2F7xgA0thC%2Bv66njAXQCm%2FaZgecsKx98SOdvEQ%3D%3D; AWSALBTG=t6G0IBD/VISs/7e2clVQwxHbjCgONrG2a10yxeeVYLK+nuFzJ2HQTda79Y25ugD8Xp70ltCMsxHoFwwUKZqp2rZkmp5fPcUxxPgtIupiH85oYKd0Oe6v/zRO0uRX+FJTNBr0yPyV+cyXel9KK/D2PjLqsC02861EUR78wSd2F7qAS0+0eO8=; AWSALBTGCORS=t6G0IBD/VISs/7e2clVQwxHbjCgONrG2a10yxeeVYLK+nuFzJ2HQTda79Y25ugD8Xp70ltCMsxHoFwwUKZqp2rZkmp5fPcUxxPgtIupiH85oYKd0Oe6v/zRO0uRX+FJTNBr0yPyV+cyXel9KK/D2PjLqsC02861EUR78wSd2F7qAS0+0eO8=; _HotDoc_session=T0dvT3k4ZllDcHgvcEE5NlpyUGhYZ0NEeUtSWmYxdGI5eDF3WUxUelpBM25GSWMyenpyZERVVDJUeDJuSXJJc2dkWGxyL0dTTDllZlhBdVVxTkhDUU40R1N3cDYxUWlna2I4WTFBNFhDclNZVm5JQ3gyT0QvNk01anpHM2ZiMWJzWTgxMGc4eERzTUJVQStCSElCM2xXRER0V0RJclZwT3Bvamx4ZFcwaExwMzRLRVp0bTZIQ2xyRGtObDVmdVMzeDcwZWJaNEZna2xFUWtLMnRUSTJxdHIwL1hHeXhhbUpOWDFXaE95by9DaTFUVzRtdTF1b2o2N3ZYeTZWS1R6bk9KNlZodWdSMStrY2h3c0dHemR6Mms3MXJZbjFmOFdvZVZBS0IxN3hCbFF3TlkyalVLVldIR2NmcmlFdUI3VUV4VzRFcmJoRDdpVUc1S3V0UnJiZjZBPT0tLWNEazNFOGNoSk53TFJTK1Z3NmNMdEE9PQ%3D%3D--e0ab9d0811f2aa7c466834920078c547aba02cf5"
    }

    for _ in range(retries):
        # Make the request
        response = requests.get(base_url, params=params, headers=headers)

        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()
            if result['time_slots']:
                slots_found = []
                for slot in result['time_slots']:
                    # print(f"{slot['day']} at {slot['label']}")
                    slots_found.append(f"{slot['day']} at {slot['label']}")

                if slots_found:
                    return f"{slots_found}"
                
            # If no slots found, update the date range and retry
            start_time, end_time = increment_date_range(start_time, end_time)
            params["start_time"] = start_time
            params["end_time"] = end_time
        else:
            print(f"error: Request failed with status code {response.status_code}")
            print(f"Response text: {response.text}")
            print(f"Response headers: {json.dumps(dict(response.headers), indent=4)}")
            return "Sorry, do you mind repeating when you said you would like to book your appointment?"

    return "No available slots found after multiple retries."

# --------------------
# Vonage Functions
# --------------------

def transfer_to_reception(uuid):
    
    vonage_client = vonage.Client(application_id="719b615e-8957-41b2-b35f-7ca844a54d77", private_key=private_key)
    
    ncco = [
        {
            "action": "connect",
            "from": VONAGE_NUMBER,
            "endpoint": [{
                "type": 'phone',
                "number": "61251122599"
            }]
        }
    ]
    
    response = vonage_client.voice.update_call(
    uuid, {
        "action": "transfer",
        "destination": {
            "type": "ncco",
            "ncco": ncco
            }
        }
    )
    print(response)
    return response

def book_appointment(doctor_ids, reason_ids, date, time, iso_date_time):
    """
    Send an SMS notification for an appointment.
    """
    # Construct the URL
    doctor_id = doctor_ids_dict.get(doctor_ids)
    reason_id = reason_ids_dict.get(reason_ids)
    url = construct_encoded_url(iso_date_time, doctor_id, reason_id)
    
    # Format the message

    message = (
        f"To complete your appointment booking with {doctor_ids} "
        f"on {date}, at {time}, please click on the following link: "
        f"{url}"
    )
    
    print(f"\n\nFROM NUMBER ------ {from_number}\n\n")
    # Send the SMS
    response = sms.send_message({
        'from': 'CHMC AI',
        'to': from_number,
        'text': message
    })

    return f"""Your appointment booking has been reserved. To complete your appointment booking with {doctor_ids} on {date}, at {time}, please click on the link I sent via sms to your mobile number. 
            Can I help you with anything else?
            """
            
@app.get("/webhooks/answer")
async def answer_call(from_number_: str = Query(None, alias="from"), uuid: str = None):
    
    uuid_to_phone[uuid] = from_number_
    
    global from_number
    from_number = from_number_
    
    ncco = [
        {
            "action": "talk",
            "text": """You've called the Chisholm Medical Centre. Please don't hesitate to ask me if you need information on our services, fees, and operating hours or have other general inquiries. I am also here to help you book appointments and check the availability of our healthcare providers. If, at any point after my responses, you'd rather speak with a human receptionist, just let me know. How can I assist you?""",
            "level": 0.20,
            "premium": True,
            "language": "en-AU",
            "style": 4
        },
        {
            "action": "input",
            "eventUrl": [f"{docker_url}/webhooks/recordings"],
            "type": ["speech"],
            "speech": {
                "endOnSilence": 1.00,
                "saveAudio": True  # Save audio to get recording_url
            }
        }
    ]
    
    return ncco

@app.post("/webhooks/recordings")
async def handle_recordings(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    
    print(f"\n\nCALL STATUS ------ {call_status}\n\n")

    # Schedule the process_data function to run in the background if the status of the call is not complete
    if call_status != True:
        background_tasks.add_task(process_data, data)
    else: print("Background tasks terminated due to CALL_STATUS = True.")
    
    # Read the JSON file containing the sentences
    with open('sentences.json', 'r') as file:
        twenty_distinct_sentences = json.load(file)

    # Randomly select a sentence
    random_sentence = random.choice(twenty_distinct_sentences)

    # Respond immediately with a holding message followed by a silent audio loop
    ncco = [
        {
            "action": "talk",
            "text": random_sentence,
            "level": 0.20,
            "premium": True,
            "language": "en-AU",
            "style": 4
        },
        {
            "action": "stream",
            "streamUrl": [f"{docker_url}/audio/temp_audio_file.mp3"],
            "loop": 0  # Infinite loop
        }
    ]
    return ncco

@app.post("/webhooks/update_call_with_response")
def update_call_with_response(call_uuid, response_text):
    
    vonage_client = vonage.Client(application_id="719b615e-8957-41b2-b35f-7ca844a54d77", private_key=private_key)
    
    try:
        response = vonage_client.voice.update_call(
            call_uuid, {
                "action": "transfer",
                "destination": {
                    "type": "ncco",
                    "ncco": [
                        {
                            "action": "talk",
                            "text": f"{response_text}",
                            "level": 0.20,
                            "premium": True,
                            "language": "en-AU",
                            "style": 4
                        },
                        {
                            "action": "input",
                            "eventUrl": [f"{docker_url}/webhooks/recordings"],
                            "type": ["speech"],
                            "speech": {
                                "endOnSilence": 1.00,
                                "saveAudio": True  # Save audio to get recording_url
                            }
                        }
                    ]
                }
            })
        return response
    
    except Exception as e:
        return f"Error executing update_call_with_response: {e}\nLikely due to user call completion."

# --------------------
# Main Processing Function
# --------------------

def process_data(data):
    
    vonage_client = vonage.Client(application_id="719b615e-8957-41b2-b35f-7ca844a54d77", private_key=private_key)
    
    recording_url = data.get("speech", {}).get("recording_url")
    
    uuid = data.get("uuid")
    
    if not recording_url:
        
        response = vonage_client.voice.update_call(
            uuid, {
                "action": "transfer",
                "destination": {
                    "type": "ncco",
                    "ncco": [
                        {
                            "action": "talk",
                            "text": "Sorry I didn't quite hear you. Could you please repeat that for me?",
                            "level": 0.20,
                            "premium": True,
                            "language": "en-AU",
                            "style": 4
                        },
                        {
                            "action": "input",
                            "eventUrl": [f"{docker_url}/webhooks/recordings"],
                            "type": ["speech"],
                            "speech": {
                                "endOnSilence": 1.00,
                                "saveAudio": True  # Save audio to get recording_url
                            }
                        }
                    ]
                }
            })
        return response

    # Add recording URL to processed set
    processed_recordings.add(recording_url)

    uuid = data.get("uuid")
    
    # Initialize the conversation if not already present
    if uuid not in conversations:
        conversations[uuid] = [
            {
                "role": "user",
                "content": 
                    """
                    Remember that any misspellings in reference to services provided should be ignored and considered 
                    to be it's likely alternative according to the context (e.g. 'artin infusion' or '9 infusion' should 
                    be considered to be 'iron infusion').
                    """
            }
        ]

    # Download the recording for transcription
    response = vonage_client.voice.get_recording(recording_url)

    audio_file_path = "audio/temp_audio_file.mp3"
    
    with open(audio_file_path, 'wb') as f:
        f.write(response)
    
    # Transcribe the recording using the Whisper service
    # Timing the transcription
    start_time = time.time()
    transcribed_text = asyncio.run(transcribe_audio(audio_file_path))
    elapsed_time_transcript = time.time() - start_time
    print(f"\n\nWhisper transcription took {elapsed_time_transcript:.2f} seconds.\n")
    
    # Add user's message to the context
    conversations[uuid].append({"role": "user", "content": transcribed_text})
    current_conversation = {uuid: conversations[uuid]}
    
    message_content = f"Conversation History: {current_conversation}\n\nCurrent User Input: {[{'role': 'user', 'content': transcribed_text}]}"

    # print(message_content)
    
    fc_start_time = time.time()
    fc_messages = [
        {
            "role": "user",
            "content": f"""
            If given an appointment date/day without a desired time, assume the time period for the appointment (e.g. 'appointment with Dr Eugene today' should trigger the book_appointment function).
            If Conversation History shows that the caller is speaking about a particular doctor, check the availability for that doctor.
            Do not give more than 4 appointment times in a single response.
            RESPOND ONLY IN SENTENCES SUITABLE FOR TEXT-TO-SPEECH. DO NOT RESPOND USING ASTERISK & ORDERED/UNORDERED LISTS.
            DO NOT TRANSFER CALLS WHEN ASKED TO SPEAK TO A DOCTOR.
            THE DEFAULT REASON (reason_ids) NEEDED AS AN ARGUMENT TO BOOK AN APPOINTMENT USING THE 'book_appointment' FUNCTION IS 'Standard Appointment'.
            When referring to date and time:
            - Use the ISO 8601 date-time format for function calling, like this: `2023-08-31T00:00:00.000`. Do not include a 'Z' at the end.
            - In your responses, use the format of days of the week and 12hr time, such as: Thursday, 24th August at 12:10 PM.
            - Ensure that dates given to you in queries are accurate based on the current date time (referred to below).

            Regarding appointments:
            - Do not confuse appointment times mentioned in the conversation history with the appointment times most recently given to you (e.g. appointment times for Dr Eugene in the previous query response should not be referenced as appointment times for Dr Karim in the current query response).
            - Do not book appointments that are before the current date-time specified.
            - Roughly estimate the period of time which the user would like to book an appointment from their query and execute 'fetch_time_slots'.
            - If asked to book a specific appointment time slot, book the appointment using the 'book_appointment' function.
            - The default appointment type and reason for Dr Karim and Dr Eugene is a standard appointment unless otherwise specified (i.e. long appointment, 20 minute appointment, etc.).
            - The default appointment reason for Dr Diaa Attallah is 'Physiotherapy Appointment'.
            - The default appointment reason for Emily Robinson is 'Dietitian Appointment'
            - When calling the 'book_appointment' function with ISO 8601 date-time, ensure a range of at least 1 week.
            - Be brief when suggesting appointment times, avoid verbosity and over-elaboration.
            - Only execute a function if the query is about specific appointment times, not general questions about appointments.

            Staff details:
            - Emily Robinson is the Dietitian.
            - Dr Diaa Attallah is the Physiotherapist.
            - Dr Eugene Tshibangu and Dr Karim Ahmed are General Practitioners. 
            - If a specific doctor isn't mentioned, default to Dr Eugene Tshibangu.

            Response guidelines:
            - Execute 'transfer_to_reception' function when asked to speak to a receptionist.
            - Avoid using dashes, slashes, or lists in your responses.
            - Craft responses suitable for text-to-speech.
            
            The current date-time is: {utc_plus_ten}
            """
        },
        {
            "role": "user",
            "content": f"""
            Instruction for Observing and Acting on Appointment Confirmations in Conversations:

            Objective: 
            - One of your tasks is to detect when a user's response is confirming an appointment booking within a conversation.

            Indicators of Confirmation: 
            - The user might confirm an appointment by using phrases such as:

                - 'yes'
                - 'yes please'
                - 'yes book that slot'
                - ...and other similar affirmative responses (potentially in the past tense).
            
            Context: 
            - This confirmation may not always immediately follow the appointment offer. 
            - It could be a response to an appointment booking confirmation or request that was made earlier in the conversation. 
            - Therefore, always consider the immediate conversation history for context.

            Action on Confirmation:

            - If you determine that the user's response is indeed confirming an appointment:
            - Identify the specific date and time details mentioned or implied earlier in the conversation.
            - Execute the 'book_appointment' function using those date and time details.
            
            Key Note: 
            - Always pay attention to the context. If the user seems to be agreeing to a specific date and time, use that information. 
            - If no specific time is mentioned, but it's clear they are confirming an appointment, further clarification may be needed.
            """
        },
        {"role": "user", "content": f"{message_content}"}
    ]
        
    functions = [
        {
            "name": "fetch_time_slots",
            "description": "Fetches doctor's availability from hotdoc",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_time": {
                        "type": "string",
                        "description": "Start time. Do not start on a Sunday."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time"
                    },
                    "doctor_ids": {
                        "type": "string",
                        "description": "Doctor's Name",
                        "enum": ["Dr Eugene Tshibangu", "Dr Karim Ahmed", "Dr Diaa Attallah", "Emily Robinson"]
                    },
                    "availability_type_ids": {
                        "type": "string",
                        "description": "Appointment Type",
                        "enum": ["Dr Eugene Tshibangu (standard appointment)", "Dr Eugene Tshibangu (long appointment)", "Dr Karim Ahmed (standard appointment)", "Dr Karim Ahmed (long appointment)", "physiotherapy", "dietitian"]
                    },
                },
                "required": ["start_time", "end_time", "doctor_ids", "availability_type_ids"],
            }
        },
        {
            "name": "book_appointment",
            "description": "Book appointment times.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Appointment Date (Day, Month, Date Format)"
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment Time (12hr Format)"
                    },
                    "doctor_ids": {
                        "type": "string",
                        "description": "Doctor's Name",
                        "enum": ["Dr Eugene Tshibangu", "Dr Karim Ahmed"]
                    },
                    "reason_ids": {
                        "type": "string",
                        "description": "Reason for Visit. Default is Standard Appointment with Doctor",
                        "enum": ["Long Appointment", "Standard Appointment", "Dietitian Appointment", "Physiotherapy Appointment"]
                    },
                    "iso_date_time": {
                        "type": "string",
                        "description": "Appointment Date in ISO 8601 format (utc + 10)",
                    },
                },
                "required": ["date", "time", "doctor_ids", "iso_date_time", "reason_ids"],
            }
        },
        {
            "name": "transfer_to_reception",
            "description": "Transfer phone call to reception upon request for human/receptionist or both.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uuid": {
                        "type": "string",
                        "description": f"{uuid}" 
                    }
                },
                "required": ["uuid"],
            }
        }
    ]
    
    fc_response = openai.ChatCompletion.create(
    model="gpt-4-0613",
    messages=fc_messages,
    functions=functions,
    function_call="auto"
    )
    
    fc_response_message = fc_response["choices"][0]["message"]

    if fc_response_message.get("function_call"):
        available_functions = {
            "fetch_time_slots": fetch_time_slots,
            "book_appointment": book_appointment,
            "transfer_to_reception": transfer_to_reception
        }
        function_name = fc_response_message["function_call"]["name"]
        function_to_call = available_functions[function_name]
        function_args = json.loads(fc_response_message["function_call"]["arguments"])

        print(f"\n\nFunction to call identified as: {function_name} with arguments: {function_args}\n\n")
        
        try:
            function_response = function_to_call(**function_args)
            if function_response == None:
                return f"Function response: {function_response}"
        except Exception as e:
            print(f"Error executing the function: {e}")

        fc_messages.append(fc_response_message)
        fc_messages.append(
            {
                "role": "function",
                "name": function_name,
                "content": function_response,
            }
        )
        second_response = openai.ChatCompletion.create(
            model="gpt-4-0613",
            messages=fc_messages
        )
        
        gpt4_fc_response = second_response["choices"][0]["message"]["content"]
        
        elapsed_time_fc = time.time() - fc_start_time

        print(f"\n\ngpt-4 function calling completed in {elapsed_time_fc} seconds.\n\n")
    
    # Query construction for transcription for context search
    # Timing the query construction  
    if 'gpt4_fc_response' in locals():
        print("No context query construction.\n\n")
    else:
        start_time = time.time()
        context_query = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": "You are a system that only returns a single keyword or a single 2-3 word keyphrase (excluding Chisholm Medical Centre) for use in a semantic vector search engine. Any queries given relating to the cost of an appointment must include the word 'standard' in the returned keyword phrase, unless otherwise specified."},
            {"role": "user", "content": f"{transcribed_text}"}
            ]
        )
    
    if 'gpt4_fc_response' in locals():
        print("No context query.\n\n")
    else:
        gpt_context_query = context_query['choices'][0]['message']['content']
        elapsed_time_context_query = time.time() - start_time
        print(f"gpt-4 pinecone query construction took {elapsed_time_context_query:.2f} seconds.\n")
    
        # Lookup query for potential context   
        # Timing the context lookup
        start_time = time.time()
        memory = context_lookup(gpt_context_query)
        elapsed_time_context = time.time() - start_time
        print(f"Pinecone semantic search for context took {elapsed_time_context:.2f} seconds.\n")
        total_pinecone_elapsed_time = elapsed_time_context_query + elapsed_time_context
        print(f"Pinecone semantic search + query construct took {total_pinecone_elapsed_time:.2f} seconds.\n")

    # Interact with gpt-4
    # Timing the gpt-4 interaction
    # You can also switch to Llama-2 hosted on Anyscale, you'll need an Anyscale account to obtain api key.
        
    start_time = time.time()
    if 'memory' in locals():
        message_content = f"Potentially Helpful Context: {memory}\n\nConversation History: {current_conversation}\n\nCurrent User Input: {[{'role': 'user', 'content': transcribed_text}]}"
        response = openai.ChatCompletion.create(
            # api_base="https://api.endpoints.anyscale.com/v1",
            # api_key="YOUR_ANYSCALE_API_KEY",
            # model="meta-llama/Llama-2-70b-chat-hf",
            # temperature=0.7,
            model="gpt-4",
            messages=[
                {"role": "user", 
                "content":                     
                    f"""
                    Role Definition: You are the virtual voice assistant for the Chisholm Medical Centre, located at Shop 1/23 Benham Street, Chishom, in Canberra, ACT who is capable of booking appointments.

                    Guidelines for Operation:
                    
                    RESPOND ONLY IN SENTENCES SUITABLE FOR TEXT-TO-SPEECH. DO NOT RESPOND USING ASTERISK & ORDERED/UNORDERED LISTS.
                    
                    Concerning Vaccinations: WE OFFER ALL TYPES OF VACCINATIONS WITH THE NURSE, IN ORDER TO BOOK THESE, IT IS BEST TO SPEAK DIRECTLY TO A RECEPTIONIST. OFFER TO FORWARD THEIR CALL.
                    
                    Concerning Laverty Pathology: They are open from 8:30 - 11:30, Tuesday to Thursday.
                    
                    DO NOT SUGGEST THAT PEOPLE SPEAK TO THE CENTRE DIRECTLY FOR THE MOST UP-TO-DATE INFORMATION.

                        1. Accuracy: Always provide accurate information. Never invent or fabricate answers.

                        2. Date Verification: Ensure that dates provided in queries are accurate in relation to the current date and time. You can book appointments that are on the current day but not before: {utc_plus_ten}.

                        3. Booking Appointments: If a patient asks for an appointment (e.g. appointments today). You can schedule appointments. To do so, you'll need:

                            * The healthcare provider's name:

                                - Dr Eugene Tshibangu (General Practitioner)

                                - Dr Karim Ahmed (General Practitioner)

                                - Dr Diaa Attallah (Physiotherapist)

                                - Emily Robinson (Dietitian)

                            * Desired date and time of the appointment.
                            
                            * YOU WILL NOT NEED TO KNOW THE PURPOSE OF THE APPOINTMENT
                            
                            * YOU CANNOT CANNOT CANCEL APPOINTMENT BOOKINGS. ADVISE THAT YOU WILL NEED TO FORWARD THEIR CALL TO RECEPTION TO DO SO, ASK IF THIS IS OKAY.
                            
                            * If asked to book an iron infusion appointment, ask if they would like to forward their call to reception to book this appointment type.

                        4. Human Assistance: You can direct callers to a human receptionist if necessary.

                        5. Availability Check: You can verify the availability of our healthcare providers.

                        6. Clarity: Offer straightforward answers. If presented with context, integrate it as your internal knowledge without citing it as external information.

                        7  Formatting: Avoid using dashes, slashes, lists or asterisk in your responses.

                        8. Text-to-Speech Compatibility: Craft your responses to be easily read by text-to-speech software.

                        9. Service References: When addressing inquiries, remember that they pertain to the Chisholm Medical Centre and its services. If the Centre doesn't provide a service mentioned, acknowledge this and offer likely alternatives based on the context provided; do not suggest other medical centres. For instance, terms like 'artin infusion', '9 infusion', or 'non-infusion' should be interpreted as 'iron infusion'.

                    Please adhere to these guidelines to provide the best assistance to the patients and visitors of the Chisholm Medical Centre.
                    """
                },
                {"role": "user", "content": message_content}
            ]
        )
        gpt4_response = response['choices'][0]['message']['content']
    else:
        None # Some sort of handling here idk


    elapsed_time_gpt4 = time.time() - start_time
    
    if 'gpt4_fc_response' in locals():
        total_elapsed_time = elapsed_time_gpt4 + elapsed_time_transcript + elapsed_time_fc
        print(f"Total elapsed time of all 4 processes was {total_elapsed_time:.2f} seconds.\n\n")
    else:
        total_elapsed_time = elapsed_time_gpt4 + elapsed_time_context + elapsed_time_transcript + elapsed_time_context_query
        print(f"gpt-4 text interaction took {elapsed_time_gpt4:.2f} seconds.\n")
        print(f"Total elapsed time of all 4 processes was {total_elapsed_time:.2f} seconds.\n\n")
    
    # Add gpt-4's response to the context
    if 'gpt4_fc_response' in locals():
        conversations[uuid].append({"role": "assistant", "content": gpt4_fc_response})
    else:
        conversations[uuid].append({"role": "assistant", "content": gpt4_response})
    
    # print("PAYLOAD ------", data, "\n\n")
    
    if 'gpt4_fc_response' in locals():
        print("")
    else:
        print("gpt-4 Pinecone Query ------", gpt_context_query, "\n\n")
    
    print("CONVERSATION HISTORY ------", current_conversation, "\n\n")
    
    print("USER TRANSCRIPTION ------", transcribed_text, "\n\n")
    
    # Update the current call with the gpt response and log response
    print(f"CALL STATUS ------ {call_status}\n\n")
    if call_status != True:
        if 'gpt4_fc_response' in locals():
            print("GPT-4 FUNCTION RESPONSE ------", gpt4_fc_response, "\n\n--------------------------------------------------------\n\n") 
            update_call_with_response(uuid, gpt4_fc_response)
        else:
            print("GPT-4 RESPONSE ------", gpt4_response, "\n\n--------------------------------------------------------\n\n")   
            update_call_with_response(uuid, gpt4_response) 
    else: print(f"Update call terminated due to call CALL_STATUS = {call_status}.\n\n--------------------------------------------------------\n\n")
         

# --------------------
# Initialisation
# --------------------

private_key = PRIVATE_KEY
openai.api_key = "YOUR_OPENAI_KEY"
vonage_client = vonage.Client(application_id="YOUR_VONAGE_APPLICATION_ID", private_key=private_key)
client = vonage.Client(key="YOUR_VONAGE_KEY", secret="YOUR_VONAGE_SECRET")
sms = vonage.Sms(client)
pinecone.init(
    api_key="YOUR_PINECONE_API_KEY",
    environment="YOUR_PINECONE_ENVIORNMENT"
    )