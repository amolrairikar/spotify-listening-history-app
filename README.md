# spotify-listening-history-app
Streamlit web app to visualize my Spotify listening history. Listening history is obtained through Spotify's Get Recently Played Tracks [endpoint](https://developer.spotify.com/documentation/web-api/reference/get-recently-played). The architecture diagram below demonstrates the end-to-end data flow.

![alt text](Spotify%20API%20Project%20Architecture.png)

To replicate this project in your own AWS environment, you will need to create your own AWS account with a Terraform user and a role the Terraform user can assume for provisioning infrastructure. You will also need to create a Spotify [application](https://developer.spotify.com/documentation/web-api/concepts/apps) to run the manual auth flow once using the command `pipenv run python -m src.spotify_auth.auth_flow`.

Any secrets referenced in `.github/workflows/ci_cd_pipeline.yml` should be created as secrets in your own repository.