import os
import json
import base64

from functools import lru_cache #package for a tool to call a fucntion only once

#gemini api imports
from google import genai 
from google.genai import types

#google cloud service imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLIENT_SECRET_FILE = 'credentials.json'

# Instructions to be sent to gemini
with open('system_instruction.md') as instructions_file:
    SYSTEM_INSTRUCTIONS = instructions_file.read()

# File having all labels
with open('labels.json', 'r') as label_file: 
    LABELS = json.load(label_file)

# File having address to label map
with open('address.json') as address_file:
    ADDRESS_TO_LABEL = json.load(address_file)

# Reverse map of label id to name
LABEL_ID_TO_NAME = {v: k for k, v in LABELS.items()}

# Loading the gmail service 
def get_gmail_service():
    creds = None

    # Loading credentials of the specific scope for the existing token 
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        # Refreshing token window for an hour when expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Starting new login as base case 
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Writing the token for future use
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

# Such that the gmail service api is called only once 
@lru_cache(maxsize=1)
def service():
    return get_gmail_service()
    
def extract_body(payload):
    body_text = ""

    # Looking for 'parts' key within payload
    if 'parts' in payload:
        for part in payload['parts']:
            body_text += extract_body(part)

    # Only extracting the text/plain from within rejecting any other type
    elif payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        if data:
            body_text += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

    # Redacting previous messages in the thread 
    for marker in ["\nOn ", "\n-Original Message-"]:
        if marker in body_text:
            body_text = body_text.split(marker)[0]

    return body_text.strip()


# Extracting only from, subject and body of the mail
def get_formated_msg(msg_data):
    payload = msg_data['payload']

    # [TESTING] _labels = msg_data['labelIds']
    _from = next((item["value"] for item in payload.get('headers', []) if item.get("name", "").lower() == "from"), None)
    _subject = next((item["value"] for item in payload.get('headers', []) if item.get("name", "").lower() == "subject"), None)
    _body = extract_body(payload)

    # [TESTING] print(f'Labels : {_labels} \nFrom : {_from} \nSubject : {_subject} \nBody : {_body}')
    return {
        # [TESTING] "labels" : _labels,
        "from" : _from,
        "subject" : _subject,
        "body" : _body
    }

# Returning all the threads grabable in single call {In Future : loop to call all the unread inboxes via loop and checking 'next page id'}
def get_threads():
    response = service().users().threads().list(
        userId='me',
        labelIds=['INBOX']
    ).execute()

    threads_list = response.get('threads', [])

    return threads_list

def process_threads(threads_list):
    thread_label_map = {}
    unprocessed_threads = []    
    
    for thread in threads_list:
        # Getting data of a single thread at a time
        thread_data = service().users().threads().get(
            userId='me',
            id=thread['id']
        ).execute()

        messages = thread_data.get('messages', [])

        # Skipping if the mail is not read 
        has_unread = any('UNREAD' in m.get('labelIds', []) for m in messages)
        if has_unread:
            continue

        # Checking if thread is new, or continuing one
        if len(messages) > 1:
            older_label_ids = messages[0].get('labelIds', [])

            # Sorting the mail according to the previously assigned Label tag
            matched_custom_label_id = next(
                (l_id for l_id in older_label_ids if l_id in LABEL_ID_TO_NAME),
                None
            )

            # Creating the thread_id : label_id map
            if matched_custom_label_id:
                custom_label_name = LABEL_ID_TO_NAME[matched_custom_label_id]
                print(f"inheriting label : {custom_label_name} | {matched_custom_label_id}")
                thread_label_map[thread['id']] = matched_custom_label_id
                continue

        # Checking if the sender is within the predetermined map of { address : label } 
        headers = messages[-1].get('payload', {}).get('headers', [])
        sender_header = next(
            (item["value"].lower() for item in headers if item.get("name", "").lower() == "from"), 
            ""
        )

        matched_label_name = next(
            (label_name for addr, label_name in ADDRESS_TO_LABEL.items() if addr.lower() in sender_header),
            None
        )

        # Adding this to thread_id : label_id
        if matched_label_name and matched_label_name in LABELS:
            matched_label_id = LABELS[matched_label_name]
            print(f"address match: {sender_header} -> {matched_label_name} | {matched_label_id}")
            thread_label_map[thread['id']] = matched_label_id
            continue
        
        
        unprocessed_threads.append(thread_data)

    return unprocessed_threads, thread_label_map

# For creating a list of formatted, unsorted mails
def get_processed_msgs(unprocessed_threads):
    processed_messages = []

    for thread in unprocessed_threads:
        messages = thread.get('messages', [])
        if not messages:
            continue

        latest_msg = messages[-1]
        formatted_msg = get_formated_msg(latest_msg)

        if not formatted_msg['body'] and not formatted_msg['subject']:
            print(f"Skipping thread {thread['id']}: No plain-text body or subject found.")
            continue

        processed_messages.append({
            "threadId" : thread['id'],
            "message" : formatted_msg
        })

    return processed_messages

# Calling the api to apply the labels 
def apply_thread_labels(thread_label_map):
    if not thread_label_map:
        print("No threads to update.")
        return

    for thread_id, label_id in thread_label_map.items():
        human_name = LABEL_ID_TO_NAME.get(label_id, label_id) # Just for visual queue / testing
        print(f"Applying label '{human_name}' to thread {thread_id}...")

        try:
            service().users().threads().modify(
                userId='me',
                id=thread_id,
                body={
                    'addLabelIds': [label_id],
                    'removeLabelIds': ['INBOX']
                }
            ).execute()
        except HttpError as error:
            if error.resp.status == 404:
                print(f"[Skipped] Thread {thread_id} not found (invalid thread ID or deleted email).")
            else:
                print(f"[Error] Failed to update thread {thread_id}: {error}")

    print("All thread updates successfully executed!")

def classify_messages_with_gemini(processed_msgs, batch_size=25):
    if not processed_msgs:
        print('No messages to send to Gemini')
        return {}

    client = genai.Client() 
    gemini_thread_map = {}

    for i in range(0, len(processed_msgs), batch_size):
        # Batching mails to send to gemini to keep prompt size smaller and decrease hillacunation
        chunk = processed_msgs[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1} ({len(chunk)} emails)...")

        prompt = json.dumps(chunk, indent=2)

        try:
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTIONS,
                    temperature=0.1 # 0.1 to keep hillacunations at its lowest but still providing a leaway
                )
            )

            raw_output = response.text.strip()

        except Exception as e:
            print(f"Error processing batch {i // batch_size + 1}: {e}")
            continue

        #[TESTING] 
        # subject_lookup = {
        #         item['threadId']: item['message'].get('subject', 'No Subject')
        #         for item in chunk
        #     }
        #[TESTING] 

        """
            Gemini returns the output in format of 
                #thread_id : label_id
            Parsing that to extract the thread id and label id and removing unnecesary spaces
        """

        for line in raw_output.splitlines():
            line = line.strip()
            if not line or not line.startswith('#'):
                continue

            parts = line.lstrip('#').split(':', 1)
            if len(parts) != 2:
                continue

            thread_id = parts[0].strip()
            label_name = parts[1].strip()
            # [TESTING] subject = subject_lookup.get(thread_id, "No Subject") #delete this 

            if label_name in LABELS:
                label_id = LABELS[label_name]
                gemini_thread_map[thread_id] = label_id
                print(f"  [Matched] {thread_id} -> {label_name} ({label_id})")
                # [TESTING] print(f"  [Matched] Subject: '{subject}' -> {label_name}")
            elif label_name == "Uncategorized":
                print(f"  [Uncategorized] {thread_id} left in Inbox.")
                # [TESTING] print(f"  [Uncategorized] Subject: '{subject}'")
            else:
                print(f"  [Skipped] {thread_id} returned unknown label: '{label_name}'")
                # [TESTING] print(f"  [Unknown Label] Subject: '{subject}' returned '{label_name}'")

    return gemini_thread_map


def main():
    threads_list = get_threads() 
    unprocessed_threads, thread_label_map = process_threads(threads_list)
    processed_msgs = get_processed_msgs(unprocessed_threads)

    gemini_thread_map = classify_messages_with_gemini(processed_msgs)

    thread_label_map.update(gemini_thread_map)

    apply_thread_labels(thread_label_map)

if __name__ == '__main__':
    main()






#==========================GARBAGE CODE==============================

   # data = []
    # if payload.get('body', {}).get('size', {}) : 
    #     data.insert(0, payload.get('body', {}).get('data', {}))

    # parts = payload.get('parts')

    # if parts :
    #     for i in range(len(parts)):
    #         part = parts[i]
    #         if part.get('mimeType', '') == 'text/plain' : 
    #             data.insert(0, part.get('body', {}).get('data', {}))

    # for i in range(len(data)):
    #     print(base64.urlsafe_b64decode(data[i]).decode('utf-8', errors='ignore'))

    # for index in range(len(messages_list)):
    #     msg = messages_list[index]
    #     # for msg in messages_list:
    #     print(f"Processing ID : {msg['id']}")
    #     msg_data = service.users().messages().get(
    #         userId='me',
    #         id=msg['id']
    #     ).execute()

    #     formated_msg = get_formated_msg(msg_data)

    #     #FILTERING UNREAD AS WE DONT WANT TO SORT THE MAILS WE HAVNET READ

    #     if "UNREAD" in formated_msg['labels'] : 
    #         continue