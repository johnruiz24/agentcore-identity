"""
Runtime Service Lambda Handler - OAuth2 Layer 3

Executes Google Calendar operations using decrypted credentials.
"""

import json
import boto3
import os
import base64
from datetime import datetime, timedelta
import http.client as http_client

# AWS Clients
dynamodb = boto3.resource('dynamodb')
kms = boto3.client('kms')

# Environment variables
CREDENTIALS_TABLE = os.environ.get('CREDENTIALS_TABLE')
KMS_KEY_ID = os.environ.get('KMS_KEY_ID')

# Initialize tables
credentials_table = dynamodb.Table(CREDENTIALS_TABLE)


class RuntimeError(Exception):
    """Runtime execution errors."""
    pass


def handler(event, context):
    """Runtime service handler."""
    try:
        path = event.get('rawPath', '/')
        method = event.get('requestContext', {}).get('http', {}).get('method', 'POST')
        headers = event.get('headers', {})
        body = event.get('body', '{}')

        # Extract user context from headers
        user_id = headers.get('x-user-id')
        credential_id = headers.get('x-credential-id')

        if not user_id or not credential_id:
            return error_response(400, 'Missing Context', 'x-user-id and x-credential-id headers required')

        # Parse request
        request_data = json.loads(body) if body else {}

        # Route to appropriate handler
        if '/calendar/events' in path and method == 'GET':
            return handle_calendar_list_events(user_id, credential_id)
        elif '/calendar/create' in path and method == 'POST':
            return handle_calendar_create_event(user_id, credential_id, request_data)
        else:
            return error_response(404, 'Not Found', 'Endpoint does not exist')

    except RuntimeError as e:
        return error_response(400, 'Runtime Error', str(e))
    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, 'Server Error', str(e))


def get_decrypted_token(user_id, credential_id):
    """Retrieve and decrypt OAuth token from DynamoDB."""
    try:
        response = credentials_table.get_item(
            Key={'credential_id': credential_id, 'user_id': user_id}
        )

        if 'Item' not in response:
            raise RuntimeError('Credential not found')

        credential = response['Item']

        # Check expiration
        if credential.get('expires_at', 0) < int(datetime.now().timestamp()):
            raise RuntimeError('Token expired')

        # Decrypt token
        encrypted_token = credential['access_token']
        ciphertext = base64.b64decode(encrypted_token)

        decrypt_response = kms.decrypt(CiphertextBlob=ciphertext)
        access_token = decrypt_response['Plaintext'].decode()

        return access_token

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f'Token decryption failed: {str(e)}')


def handle_calendar_list_events(user_id, credential_id):
    """List Google Calendar events."""
    try:
        access_token = get_decrypted_token(user_id, credential_id)

        # Call Google Calendar API
        conn = http_client.HTTPSConnection('www.googleapis.com')
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        conn.request('GET', '/calendar/v3/calendars/primary/events', headers=headers)
        response = conn.getresponse()
        events_data = json.loads(response.read().decode())

        if response.status != 200:
            raise RuntimeError(f'Google API error: {events_data.get("error", {}).get("message")}')

        return success_response({
            'status': 'success',
            'action': 'list_events',
            'events': events_data.get('items', [])
        })

    except RuntimeError as e:
        raise
    except Exception as e:
        raise RuntimeError(f'Calendar list failed: {str(e)}')


def handle_calendar_create_event(user_id, credential_id, request_data):
    """Create a Google Calendar event."""
    try:
        access_token = get_decrypted_token(user_id, credential_id)

        event = {
            'summary': request_data.get('summary', 'New Event'),
            'description': request_data.get('description', ''),
            'start': {
                'dateTime': request_data.get('start_time', datetime.now().isoformat()),
                'timeZone': request_data.get('timezone', 'UTC')
            },
            'end': {
                'dateTime': request_data.get('end_time', (datetime.now() + timedelta(hours=1)).isoformat()),
                'timeZone': request_data.get('timezone', 'UTC')
            }
        }

        # Call Google Calendar API
        conn = http_client.HTTPSConnection('www.googleapis.com')
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        conn.request(
            'POST',
            '/calendar/v3/calendars/primary/events',
            json.dumps(event),
            headers=headers
        )
        response = conn.getresponse()
        event_data = json.loads(response.read().decode())

        if response.status != 200:
            raise RuntimeError(f'Google API error: {event_data.get("error", {}).get("message")}')

        return success_response({
            'status': 'success',
            'action': 'create_event',
            'event_id': event_data.get('id'),
            'event': event_data
        })

    except RuntimeError as e:
        raise
    except Exception as e:
        raise RuntimeError(f'Calendar create failed: {str(e)}')


def success_response(data):
    """Format successful response."""
    return {
        'statusCode': 200,
        'body': json.dumps(data),
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}
    }


def error_response(status_code, error_type, message):
    """Format error response."""
    return {
        'statusCode': status_code,
        'body': json.dumps({'error': error_type, 'message': message}),
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}
    }
