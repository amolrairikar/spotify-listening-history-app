from typing import Optional
from decimal import Decimal

import pandas as pd
import streamlit as st
import duckdb
import altair as alt


st.set_page_config(layout='wide')

# Set up connection to S3
duckdb.sql(
    f"""
    INSTALL httpfs;
    LOAD httpfs;

    SET s3_region='us-east-2';
    SET s3_access_key_id='{st.secrets['AWS_ACCESS_KEY_ID']}';
    SET s3_secret_access_key='{st.secrets['AWS_SECRET_ACCESS_KEY']}';
    """
)


# Define any functions needed for the Streamlit app here
def generate_sql_query(year: Optional[str] = None, month: Optional[str] = None) -> str:
    """Generate SQL query to fetch Spotify listening history data from S3 using DuckDB SQL."""
    base_query = f"""
        SELECT
            track_id,
            album,
            release_date,
            artists,
            track_length,
            track_name,
            track_url,
            track_popularity,
            played_at
        FROM read_json(
            's3://{st.secrets['SPOTIFY_DATA_S3_BUCKET']}/processed/',
            hive_partitioning=1
        )
    """
    if year:
        base_query = base_query.replace('processed/', f'processed/year={year}/')
        if month:
            base_query = base_query.replace(f'processed/year={year}/', f'processed/year={year}/month={month}/*.json')
        else:
            base_query = base_query.replace(f'processed/year={year}/', f'processed/year={year}/**/*.json')
    else:
        base_query = base_query.replace('processed/', 'processed/**/*')
    return base_query


@st.cache_data(ttl=3600, show_spinner=True, persist=False)
def fetch_s3_data(sql_query: str) -> pd.DataFrame:
    """Fetch data from S3 using a DuckDB SQL query."""
    return duckdb.sql(sql_query).df()


def convert_mmss_to_minutes(mmss_string: str) -> float:
    """Converts a string in mm:ss format to total minutes."""
    minutes = mmss_string.split(':')[0]
    seconds = mmss_string.split(':')[1]
    return Decimal(minutes) + Decimal(Decimal(seconds) / 60)


# Read data from S3 + data processing
year = st.sidebar.selectbox("Select Year", options=[None, '2025'])
month = st.sidebar.selectbox("Select Month", options=[None, '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'])
sql_query = generate_sql_query(year, month)
df = fetch_s3_data(sql_query)
df['artists_clean'] = df['artists'].apply(lambda x: ', '.join(map(str, x)))
df['track_length_minutes'] = round(df['track_length'].astype(str).apply(lambda x: convert_mmss_to_minutes(x) if isinstance(x, str) else x).astype(float), 2)
df['played_at_timestamp'] = pd.to_datetime(df['played_at'])
df['played_at_day_of_week'] = df['played_at_timestamp'].dt.day_name()
day_order = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
df['played_at_day_of_week'] = pd.Categorical(df['played_at_day_of_week'], categories=day_order, ordered=True)
df['played_at_hour'] = df['played_at_timestamp'].dt.hour
hour_order = list(range(0, 24))
df['played_at_hour'] = pd.Categorical(df['played_at_hour'], categories=hour_order, ordered=True)
df['played_at_week_number'] = df['played_at_timestamp'].dt.isocalendar().week
week_order = list(range(1, 53))
df['played_at_week_number'] = pd.Categorical(df['played_at_week_number'], categories=week_order, ordered=True)
most_played_tracks = df.groupby(['track_name', 'artists_clean']).size().reset_index(name='count').sort_values(by='count', ascending=False).head(10)
max_track_play_count = most_played_tracks['count'].max()
most_played_artists = df.explode('artists').reset_index(drop=True)[['artists', 'track_length_minutes']].groupby('artists').sum().reset_index().sort_values(by='track_length_minutes', ascending=False).head(10)
most_played_artists['track_length_minutes'] = round(most_played_artists['track_length_minutes'].astype(float))
most_played_artist_minutes = most_played_artists['track_length_minutes'].max()
day_of_week_track_distribution = df[['played_at_day_of_week', 'track_length_minutes']].groupby('played_at_day_of_week').sum().reset_index()
time_of_day_track_distribution = df[['played_at_hour', 'track_length_minutes']].groupby('played_at_hour').sum().reset_index()
listening_heatmap = df.groupby(['played_at_week_number', 'played_at_day_of_week'], as_index=False)['track_length_minutes'].sum()


# App UI code
st.title('My Spotify Listening History')
spotify_green = '#1DB954'
col1, col2, col3, col4 = st.columns(4)
col1.metric('Total Tracks', df.shape[0])
col2.metric('Total Artists', len(set(df['artists_clean'].str.split(',').sum())))
col3.metric('Total Minutes', round(df['track_length_minutes'].sum()))
col4.metric('Average Track Popularity (1-100)', round(df['track_popularity'].astype(float).mean()))
st.divider()
st.subheader('Most Played Tracks')
st.altair_chart(
    alt.Chart(most_played_tracks).mark_bar(color=spotify_green).encode(
        x=alt.X('count', title='Count', axis=alt.Axis(
            values=list(range(0, max_track_play_count + 1)),
            format='d',
            tickMinStep=1)
        ),
        y=alt.Y('track_name', sort=None, title=None),
        tooltip=[
            alt.Tooltip('artists_clean', title='Artists'),
            alt.Tooltip('count', title='Count')
        ]
    ).configure_axis(
        labelLimit=0
    ),
    use_container_width=True
)
st.subheader('Most Played Artists')
st.altair_chart(
    alt.Chart(most_played_artists).mark_bar(color=spotify_green).encode(
        x=alt.X('track_length_minutes', title='Minutes Played'
        ),
        y=alt.Y('artists', sort=None, title=None),
        tooltip=[
            alt.Tooltip('track_length_minutes', title='Minutes Played')
        ]
    ),
    use_container_width=True
)
st.divider()
col1, col2 = st.columns(2)
with col1:
    st.altair_chart(
        alt.Chart(day_of_week_track_distribution).mark_bar(color=spotify_green).encode(
            x=alt.X('played_at_day_of_week:N', sort=day_order, title='Day of Week'),
            y=alt.Y('track_length_minutes:Q', title='Total Minutes'),
            tooltip=[
                alt.Tooltip('track_length_minutes:Q', title='Total Minutes')
            ]
        ).properties(
            title=alt.TitleParams(
                text='Minutes Listened by Day of Week',
                anchor='middle'
            )
        )
    )
with col2:
    st.altair_chart(
        alt.Chart(time_of_day_track_distribution).mark_bar(color=spotify_green).encode(
            x=alt.X('played_at_hour:O', bin=alt.Bin(step=1), title='Hour of Day'),
            y=alt.Y('track_length_minutes:Q', title='Total Minutes'),
            tooltip=[
                alt.Tooltip('track_length_minutes:Q', title='Total Minutes')
            ]
        ).properties(
            title=alt.TitleParams(
                text='Minutes Listened by Time of Day',
                anchor='middle'
            )
        )
    )
st.divider()
max_minutes = listening_heatmap['track_length_minutes'].max()
color_scale = alt.Scale(
    domain=[0, 0.25 * max_minutes, 0.5 * max_minutes, 0.75 * max_minutes, max_minutes],
    range=['#0E1117', '#033A16', '#196C2E', '#2EA043', spotify_green]
)
st.altair_chart(
    alt.Chart(listening_heatmap).mark_rect(
        stroke='black',
        strokeWidth=3,
        cornerRadius=5
    ).encode(
        x=alt.X('played_at_week_number:O', title='Week Number'),
        y=alt.Y('played_at_day_of_week:N', title='Day of Week', sort=day_order),
        color=alt.Color('track_length_minutes:Q', scale=color_scale, title='Minutes Listened'),
        tooltip=[
            alt.Tooltip('played_at_week_number:O', title='Week Number'),
            alt.Tooltip('played_at_day_of_week:N', title='Day of Week'),
            alt.Tooltip('track_length_minutes:Q', title='Total Minutes')
        ]
    ).properties(
        title=alt.TitleParams(
                text='Listening History Heatmap',
                anchor='middle'
            )
    )
)
