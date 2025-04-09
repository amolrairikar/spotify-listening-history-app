# spotify-listening-history-app
Streamlit web app to visualize a user's Spotify listening history

Running the auth flow manually
`pipenv run python -m src.spotify_auth.auth_flow`

Running unit tests
`pipenv run coverage run -m unittest discover -s tests && pipenv run coverage report --omit="tests/*"`

Running unit tests with HTML report
`pipenv run coverage run -m unittest discover -s tests && pipenv run coverage html --omit="tests/*"`