# spotify-listening-history-app
Streamlit web app to visualize my Spotify listening history. Listening history is obtained through Spotify's Get Recently Played Tracks [endpoint](https://developer.spotify.com/documentation/web-api/reference/get-recently-played). The architecture diagram below demonstrates the end-to-end data flow.

![alt text](https://github.com/amolrairikar/spotify-listening-history-app "Logo Title Text 1")


Running the auth flow manually
`pipenv run python -m src.spotify_auth.auth_flow`