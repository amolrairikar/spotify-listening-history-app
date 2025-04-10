"""Module for a one-time manual Spotify authentication flow."""
import os
import secrets
import urllib
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
from dotenv import load_dotenv

from src.lambdas.get_recently_played import ParameterStoreClient
from src.lambdas.get_recently_played import request_access_token

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
        raise HTTPException(status_code=400, detail='Missing state or authorization_code')

    if state != stored_state:
        raise HTTPException(status_code=400, detail='State mismatch, possible CSRF attack.')

    stored_state = None
    tokens = request_access_token(
        authorization_type='initial_auth',
        auth_token=code
    )
    refresh_token = tokens.json()['refresh_token']

    # Save refresh token, and last fetched timestamp to AWS SSM Parameter Store
    parameter_store_client = ParameterStoreClient(region='us-east-2')
    if refresh_token is not None or refresh_token != '':
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
