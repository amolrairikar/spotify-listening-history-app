"""Module for a one-time manual Spotify authentication flow."""
import os
import secrets
import urllib
import base64
import time
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import requests
from dotenv import load_dotenv

from src.lambdas.get_recently_played import ParameterStoreClient

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Store a global state variable
stored_state = None


def generate_state() -> str:
    """Generates a random state string for CSRF protection."""
    return secrets.token_urlsafe(16)


def generate_current_unix_timestamp() -> str:
    """Generates the current Unix timestamp in milliseconds."""
    return str(int(time.time()) * 1000)


def generate_authorization_url(state: str) -> str:
    """Creates the authorization URL for Spotify OAuth2.0 authentication."""
    auth_base_url = 'https://accounts.spotify.com/authorize'
    params = {
        'client_id': os.environ['CLIENT_ID'],
        'response_type': 'code',
        'redirect_uri': os.environ['REDIRECT_URI'],
        'state': state,
        'scope': 'user-read-recently-played',
        'show_dialog': 'false'
    }
    return f'{auth_base_url}?{urllib.parse.urlencode(params)}'


def encode_string(input_string: str) -> str:
    """Encodes a string using base64 encoding."""
    string_bytes = input_string.encode('utf-8')
    base64_bytes = base64.b64encode(string_bytes)
    return base64_bytes.decode('utf-8')


def request_access_token(auth_code: str) -> Dict[str, Any]:
    """Sends a request to exchange the authorization code for access/refresh tokens."""
    token_url = 'https://accounts.spotify.com/api/token'
    encoded_key = encode_string(
        input_string=f'{os.environ["CLIENT_ID"]}:{os.environ["CLIENT_SECRET"]}'
    )
    headers = {
        'Authorization': 'Basic ' + encoded_key,
        'content-type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': os.environ['REDIRECT_URI']
    }
    response = requests.post(token_url, data=data, headers=headers)
    response.raise_for_status()
    return response


@app.get('/', response_class=HTMLResponse)
async def home():
    """Home page with login button."""
    return """
    <html>
        <body>
            <h2>Spotify OAuth2 Authentication</h2>
            <a href="/login">Login with Spotify</a>
        </body>
    </html>
    """


@app.get('/login')
async def login() -> RedirectResponse:
    """Redirects user to the Spotify OAuth2 authorization URL."""
    state = generate_state()
    auth_url = generate_authorization_url(state=state)

    global stored_state
    stored_state = state
    
    # Redirect user to the Spotify authorization URL
    return RedirectResponse(auth_url)


@app.get('/callback')
async def callback(code: Optional[str] = None, state: Optional[str] = None):
    """Handles the callback from Spotify's authorization server."""
    global stored_state
    
    if not state or not code:
        raise HTTPException(status_code=400, detail='Missing state or code')

    if state != stored_state:
        raise HTTPException(status_code=400, detail='State mismatch, possible CSRF attack.')
    
    stored_state = None

    tokens = request_access_token(auth_code=code)
    access_token = tokens.json()['access_token']
    refresh_token = tokens.json()['refresh_token']

    # Save access token, refresh token, and last fetched timestamp to AWS SSM Parameter Store
    parameter_store_client = parameterStoreClient(region='us-east-2')
    parameter_store_client.create_or_update_parameter(
        parameter_name='spotify_access_token',
        parameter_value=access_token,
        parameter_type='SecureString',
        overwrite=False,
        parameter_description='Access token for Spotify API'
    )
    parameter_store_client.create_or_update_parameter(
        parameter_name='spotify_refresh_token',
        parameter_value=refresh_token,
        parameter_type='SecureString',
        overwrite=False,
        parameter_description='Refresh token for Spotify API'
    )
    parameter_store_client.create_or_update_parameter(
        parameter_name='spotify_last_fetched_time',
        parameter_value=generate_current_unix_timestamp(),
        parameter_type='String',
        overwrite=False,
        parameter_description='Last fetched UNIX timestamp for Spotify API'
    )
    return {
        'message': 'Authentication successful and tokens saved!'
    }


if __name__ == "__main__":
    uvicorn.run(app, host='127.0.0.1', port=8000)
