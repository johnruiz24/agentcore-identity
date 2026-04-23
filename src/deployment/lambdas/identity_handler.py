"""
Identity Service Lambda Handler - OAuth2 Layer 1

Handles Google OAuth login flow:
1. /authorize - Generate authorization URL
2. /callback - Exchange code for token
3. /status - Check user authentication status
"""

import json
import boto3
import os
import base64
import hashlib
import secrets
from datetime import datetime
from urllib.parse import urlencode
import http.client as http_client

# AWS Clients
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
kms = boto3.client('kms')

# Environment variables
CREDENTIALS_TABLE = os.environ.get('CREDENTIALS_TABLE')
OAUTH_FLOWS_TABLE = os.environ.get('OAUTH_FLOWS_TABLE')
KMS_KEY_ID = os.environ.get('KMS_KEY_ID')
GOOGLE_SECRET_ARN = os.environ.get('GOOGLE_SECRET_ARN')

# Initialize tables
credentials_table = dynamodb.Table(CREDENTIALS_TABLE)
flows_table = dynamodb.Table(OAUTH_FLOWS_TABLE)


class OAuth2Error(Exception):
    """OAuth2 specific errors."""
    pass


def get_google_oauth_config():
    """Retrieve Google OAuth configuration from Secrets Manager."""
    try:
        secret_response = secrets_manager.get_secret_value(SecretId=GOOGLE_SECRET_ARN)
        config = json.loads(secret_response['SecretString'])
        return config
    except Exception as e:
        raise OAuth2Error(f"Failed to retrieve Google OAuth config: {str(e)}")


def generate_state():
    """Generate a secure random state parameter for CSRF protection."""
    return secrets.token_urlsafe(32)


def generate_code_challenge():
    """Generate PKCE code challenge."""
    code_verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip('=')
    return code_verifier, challenge


def handler(event, context):
    """Lambda handler for OAuth2 Identity Service."""
    try:
        path = event.get('rawPath', '/')
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        query_params = event.get('queryStringParameters', {}) or {}
        body = event.get('body', '{}')

        if path == '/oauth/authorize' and method == 'GET':
            return handle_authorize(query_params)
        elif path == '/oauth/callback' and method == 'POST':
            return handle_callback(json.loads(body) if body else {})
        elif path == '/oauth/status' and method == 'GET':
            return handle_status(query_params)
        else:
            return error_response(404, 'Not Found', 'Endpoint does not exist')

    except OAuth2Error as e:
        return error_response(400, 'OAuth2 Error', str(e))
    except Exception as e:
        print(f"Error: {str(e)}")
        return error_response(500, 'Server Error', str(e))


def handle_authorize(params):
    """Handle OAuth2 authorization request."""
    user_id = params.get('user_id')
    if not user_id:
        return error_response(400, 'Missing', 'user_id required')

    google_config = get_google_oauth_config()
    state = generate_state()
    code_verifier, code_challenge = generate_code_challenge()
    flow_id = secrets.token_urlsafe(16)
    timestamp = int(datetime.now().timestamp())

    try:
        flows_table.put_item(Item={
            'flow_id': flow_id,
            'user_id': user_id,
            'state': state,
            'code_verifier': code_verifier,
            'timestamp': timestamp,
            'ttl': timestamp + 3600,
            'status': 'initiated'
        })
    except Exception as e:
        raise OAuth2Error(f"Failed to create flow: {str(e)}")

    auth_params = {
        'client_id': google_config['client_id'],
        'redirect_uri': google_config['redirect_uri'],
        'response_type': 'code',
        'scope': 'openid email profile https://www.googleapis.com/auth/calendar',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'access_type': 'offline'
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(auth_params)}"

    return success_response({
        'status': 'authorized',
        'flow_id': flow_id,
        'authorization_url': auth_url,
        'user_id': user_id
    })


def handle_callback(body):
    """Handle OAuth2 callback from Google."""
    code = body.get('code')
    state = body.get('state')
    error = body.get('error')

    if error:
        return error_response(400, 'Auth Failed', f"Google: {error}")

    if not code or not state:
        return error_response(400, 'Invalid', 'code and state required')

    try:
        flows_response = flows_table.scan(
            FilterExpression='#state = :state',
            ExpressionAttributeNames={'#state': 'state'},
            ExpressionAttributeValues={':state': state}
        )

        if not flows_response['Items']:
            raise OAuth2Error('Invalid state')

        flow = flows_response['Items'][0]
        flow_id = flow['flow_id']
        user_id = flow['user_id']
        code_verifier = flow['code_verifier']

    except Exception as e:
        raise OAuth2Error(f"Flow lookup failed: {str(e)}")

    google_config = get_google_oauth_config()

    try:
        conn = http_client.HTTPSConnection('oauth2.googleapis.com')
        token_params = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': google_config['client_id'],
            'client_secret': google_config['client_secret'],
            'redirect_uri': google_config['redirect_uri'],
            'code_verifier': code_verifier
        }
        conn.request('POST', '/token', urlencode(token_params))
        response = conn.getresponse()
        token_data = json.loads(response.read().decode())

        if 'error' in token_data:
            raise OAuth2Error(f"Token exchange: {token_data.get('error_description')}")

        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)

    except Exception as e:
        raise OAuth2Error(f"Token exchange failed: {str(e)}")

    try:
        encrypted_response = kms.encrypt(KeyId=KMS_KEY_ID, Plaintext=access_token.encode())
        encrypted_token = base64.b64encode(encrypted_response['CiphertextBlob']).decode()

        encrypted_refresh_token = None
        if refresh_token:
            encrypted_refresh = kms.encrypt(KeyId=KMS_KEY_ID, Plaintext=refresh_token.encode())
            encrypted_refresh_token = base64.b64encode(encrypted_refresh['CiphertextBlob']).decode()

    except Exception as e:
        raise OAuth2Error(f"Encryption failed: {str(e)}")

    credential_id = secrets.token_urlsafe(16)
    timestamp = int(datetime.now().timestamp())

    try:
        credentials_table.put_item(Item={
            'credential_id': credential_id,
            'user_id': user_id,
            'provider': 'google',
            'access_token': encrypted_token,
            'refresh_token': encrypted_refresh_token,
            'expires_at': timestamp + expires_in,
            'scopes': ['email', 'profile', 'https://www.googleapis.com/auth/calendar'],
            'created_at': timestamp,
            'ttl': timestamp + (30 * 24 * 3600),
            'flow_id': flow_id
        })

        flows_table.update_item(
            Key={'flow_id': flow_id},
            UpdateExpression='SET #status = :status, credential_id = :cred_id',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'completed', ':cred_id': credential_id}
        )

    except Exception as e:
        raise OAuth2Error(f"Storage failed: {str(e)}")

    return success_response({
        'status': 'authenticated',
        'credential_id': credential_id,
        'user_id': user_id,
        'provider': 'google'
    })


def handle_status(params):
    """Check OAuth2 authentication status."""
    user_id = params.get('user_id')
    if not user_id:
        return error_response(400, 'Missing', 'user_id required')

    try:
        response = credentials_table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': user_id}
        )

        credentials = [{
            'credential_id': c['credential_id'],
            'provider': c['provider'],
            'scopes': c.get('scopes', []),
            'created_at': c['created_at']
        } for c in response.get('Items', [])]

        return success_response({
            'authenticated': len(credentials) > 0,
            'user_id': user_id,
            'credentials': credentials
        })

    except Exception as e:
        raise OAuth2Error(f"Status check failed: {str(e)}")


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
