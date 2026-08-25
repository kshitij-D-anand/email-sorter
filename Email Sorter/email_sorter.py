import os
import json
import base64

from functools import lru_cache

from google import genai

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLIENT_SECRET_FILE = 'credentials.json'

with open('labels.json', 'r') as label_file: 
    LABELS = json.load(label_file)

with open('address.json') as address_file:
    ADDRESS_TO_LABEL = json.load(address_file)

LABEL_ID_TO_NAME = {v: k for k, v in LABELS.items()}

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

@lru_cache(maxsize=1)
def service():
    return get_gmail_service()
    
def extract_body(payload):
    body_text = ""
    
    # 1. Multi-part email: search sub-parts recursively
    if 'parts' in payload:
        for part in payload['parts']:
            body_text += extract_body(part)
            
    # 2. Leaf node in multi-part email
    elif payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        if data:
            body_text += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

    # Optional: Slice off quoted reply history to save tokens
    for marker in ["\nOn ", "\n-Original Message-"]:
        if marker in body_text:
            body_text = body_text.split(marker)[0]

    return body_text.strip()


def get_formated_msg(msg_data):
    payload = msg_data['payload']

    # _labels = msg_data['labelIds']
    _from = next((item["value"] for item in payload.get('headers', []) if item.get("name", "").lower() == "from"), None)
    _subject = next((item["value"] for item in payload.get('headers', []) if item.get("name", "").lower() == "subject"), None)
    _body = extract_body(payload)

    # print(f'Labels : {_labels} \nFrom : {_from} \nSubject : {_subject} \nBody : {_body}')
    return {
        # "labels" : _labels,
        "from" : _from,
        "subject" : _subject,
        "body" : _body
    }

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
        thread_data = service().users().threads().get(
            userId='me',
            id=thread['id']
        ).execute()

        messages = thread_data.get('messages', [])

        has_unread = any('UNREAD' in m.get('labelIds', []) for m in messages)
        if has_unread:
            continue

        if len(messages) > 1:
            older_label_ids = messages[0].get('labelIds', [])

            matched_custom_label_id = next(
                (l_id for l_id in older_label_ids if l_id in LABEL_ID_TO_NAME),
                None
            )

            if matched_custom_label_id:
                custom_label_name = LABEL_ID_TO_NAME[matched_custom_label_id]
                print(f"inheriting label : {custom_label_name} | {matched_custom_label_id}")
                thread_label_map[thread['id']] = matched_custom_label_id
                continue

        headers = messages[-1].get('payload', {}).get('headers', [])
        sender_header = next(
            (item["value"].lower() for item in headers if item.get("name", "").lower() == "from"), 
            ""
        )

        matched_label_name = next(
            (label_name for addr, label_name in ADDRESS_TO_LABEL.items() if addr.lower() in sender_header),
            None
        )

        if matched_label_name and matched_label_name in LABELS:
            matched_label_id = LABELS[matched_label_name]
            print(f"address match: {sender_header} -> {matched_label_name} | {matched_label_id}")
            thread_label_map[thread['id']] = matched_label_id
            continue
        
        
        unprocessed_threads.append(thread_data)

    return unprocessed_threads, thread_label_map



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

def apply_thread_labels(thread_label_map):
    if not thread_label_map:
        print("No threads to update.")
        return

    for thread_id, label_id in thread_label_map.items():
        human_name = LABEL_ID_TO_NAME.get(label_id, label_id)
        print(f"Applying label '{human_name}' to thread {thread_id}...")

        service().users().threads().modify(
            userId='me',
            id=thread_id,
            body={
                'addLabelIds': [label_id],
                'removeLabelIds': ['INBOX']
            }
        ).execute()

    print("All thread updates successfully executed!")

def main():
    threads_list = get_threads()
    unprocessed_threads, thread_label_map = process_threads(threads_list)
    processed_msgs = get_processed_msgs(unprocessed_threads)

    apply_thread_labels(thread_label_map)

if __name__ == '__main__':
    main()


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