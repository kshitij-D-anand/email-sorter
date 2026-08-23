import os
import json
import base64

from google import genai

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLIENT_SECRET_FILE = 'credentials.json'

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

    _id = msg_data['id']
    _labels = msg_data['labelIds']
    _from = next((item["value"] for item in payload.get('headers', []) if item.get("name") == "From"), None)
    _subject = next((item["value"] for item in payload.get('headers', []) if item.get("name") == "Subject"), None)
    _body = extract_body(payload)

    # print(f'Labels : {_labels} \nFrom : {_from} \nSubject : {_subject} \nBody : {_body}')
    return {
        "id" : _id,
        "labels" : _labels,
        "from" : _from,
        "subject" : _subject,
        "body" : _body
    }

def get_unsorted_mails():
    service = get_gmail_service()

    response = service.users().messages().list(
        userId='me',
        labelIds=['INBOX']
    ).execute()

    messages_list = response.get('messages', [])

    for index in range(len(messages_list)):
        msg = messages_list[index]
        # for msg in messages_list:
        print(f"Processing ID : {msg['id']}")
        msg_data = service.users().messages().get(
            userId='me',
            id=msg['id']
        ).execute()

        formated_msg = get_formated_msg(msg_data)

        #FILTERING UNREAD AS WE DONT WANT TO SORT THE MAILS WE HAVNET READ

        if "UNREAD" in formated_msg['labels'] : 
            continue

        

def main():
    get_unsorted_mails()

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
