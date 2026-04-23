"""
Gateway Service Lambda Handler - OAuth2 Layer 2

Validates OAuth tokens and routes to Runtime service.
Implements zero-trust authorization model.
"""

import json
import boto3
import os
import base64
from datetime import datetime
import jwt

# AWS Clients
dynamodb = boto3.resource('dynamodb')
kms = boto3.client('kms')

# Environment variables
CREDENTIALS_TABLE = os.environ.get('CREDENTIALS_TABLE')
OAUTH_FLOWS_TABLE = os.environ.get('OAUTH_FLOWS_TABLE')
KMS_KEY_ID = os.environ.get('KMS_KEY_ID')

# Initialize tables
credentials_table = dynamodb.Table(CREDENTIALS_TABLE)
flows_table = dynamodb.Table(OAUTH_FLOWS_TABLE)


class AuthorizationError(Exception):
    """Authorization specific errors."""
    pass


def handler(event, context):
    """Gateway service handler."""
    try:
        path = event.get('rawPath', '/')
        method = event.get('requestContext', {}).get('http', {}).get('method', 'POST')
        headers = event.get('headers', {})
        body = event.get('body', '{}')

        # Extract and validate authorization token
        auth_header = headers.get('authorization', '')
        if not auth_header.startswith('Bearer '):
            return error_response(401, 'Unauthorized', 'Missing Bearer token')

        token = auth_header[7:]  # Remove 'Bearer ' prefix
        user_id, credential_id, scopes = validate_token(token)

        # Parse request body
        request_data = json.loads(body) if body else {}
        required_scopes = request_data.get('required_scopes', [])

        # Check scopes
        if not all(scope in scopes for scope in required_scopes):
            return error_response(403, 'Forbidden', f'Missing required scopes: {required_scopes}')

        # Route to appropriate service
        if path == '/gateway/validate':
            return handle_validate(user_id, credential_id, scopes)
        elif path == '/gateway/invoke':
            return handle_invoke(user_id, credential_id, request_data)
        else:
            return error_response(404, 'Not Found', 'Endpoint does not exist')

    except AuthorizationError as e:
        return error_response(401, 'Authorization Error', str(e))
    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, 'Server Error', str(e))


def validate_token(token):
    """
    Validate OAuth token.
    Returns: (user_id, credential_id, scopes)
    """
    try:
        # Query credentials table to find token
        response = credentials_table.scan(
            FilterExpression='access_token = :token',
            ExpressionAttributeValues={':token': token}
        )

        if not response['Items']:
            raise AuthorizationError('Invalid token')

        credential = response['Items'][0]
        
        # Check expiration
        if credential.get('expires_at', 0) < int(datetime.now().timestamp()):
            raise AuthorizationError('Token expired')

        return credential['user_id'], credential['credential_id'], credential.get('scopes', [])

    except AuthorizationError:
        raise
    except Exception as e:
        raise AuthorizationError(f'Token validation failed: {str(e)}')


def handle_validate(user_id, credential_id, scopes):
    """Validate token and return authorization info."""
    return success_response({
        'authenticated': True,
        'user_id': user_id,
        'credential_id': credential_id,
        'scopes': scopes,
        'timestamp': int(datetime.now().timestamp())
    })


def handle_invoke(user_id, credential_id, request_data):
    """Route to Runtime service."""
    action = request_data.get('action')
    payload = request_data.get('payload', {})

    if not action:
        return error_response(400, 'Missing Action', 'action field required')

    # Forward to Runtime service
    return success_response({
        'status': 'routed',
        'action': action,
        'user_id': user_id,
        'credential_id': credential_id,
        'payload': payload
    })


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
