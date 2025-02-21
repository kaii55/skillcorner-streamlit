import streamlit as st
import pandas as pd
import requests
import os
from skillcornerviz.standard_plots import bar_plot as bar
from skillcornerviz.standard_plots import scatter_plot as scatter
from skillcornerviz.utils import skillcorner_physical_utils as p_utils
from skillcorner.client import SkillcornerClient

# API Credentials
USERNAME = st.secrets["credentials"]["SKILLCORNER_USERNAME"]
PASSWORD = st.secrets["credentials"]["SKILLCORNER_PASSWORD"]
BASE_URL = "https://skillcorner.com/api"

# Function to fetch competition editions
@st.cache_data
def fetch_competition_editions():
    url = f"{BASE_URL}/competition_editions/?user=true"
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, auth=(USERNAME, PASSWORD), headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if "results" not in data:
            st.error("❌ API Response does not contain 'results'")
            return None
        
        extracted_data = [
            {
                "competition_id": item["competition"]["id"],
                "competition_name": item["competition"]["name"],
                "season_id": item["season"]["id"],
                "season_name": f"{item['season']['start_year']}/{item['season']['end_year']}"
            }
            for item in data["results"]
        ]

        df = pd.DataFrame(extracted_data)
        return df
    
    except requests.exceptions.RequestException as e:
        st.error(f"❌ API Request Failed: {e}")
        return None

# Function to fetch all matches
@st.cache_data
def fetch_all_matches():
    url = f"{BASE_URL}/matches/?user=true"
    headers = {"Accept": "application/json"}
    results = []
    
    while url:
        response = requests.get(url, auth=(USERNAME, PASSWORD), headers=headers)
        if response.status_code == 200:
            data = response.json()
            results.extend(data["results"])
            url = data.get("next")
        else:
            st.error(f"❌ Error {response.status_code}: {response.text}")
            break
    
    df = pd.DataFrame(results)
    return df

# Function to fetch dynamic events for a match
@st.cache_data
def fetch_dynamic_events(match_id, file_format="csv"):
    url = f"{BASE_URL}/match/{match_id}/dynamic_events/?file_format={file_format}"
    headers = {"Accept": "application/json"}
    response = requests.get(url, auth=(USERNAME, PASSWORD), headers=headers)
    
    if response.status_code == 200:
        if file_format == "csv":
            df = pd.read_csv(response.url)
            return df
        else:
            return response.json()
    else:
        st.error(f"❌ Error {response.status_code}: {response.text}")
        return None

# Streamlit UI
st.title("SkillCorner Competition & Performance Explorer")

# Fetch Data
df_comp_seasons = fetch_competition_editions()
df_matches = fetch_all_matches()

if df_comp_seasons is not None:
    st.sidebar.subheader("Select a Competition")
    comp_options = {f"{row['competition_name']} ({row['competition_id']})": row['competition_id'] for _, row in df_comp_seasons.iterrows()}
    selected_competition = st.sidebar.selectbox("Choose Competition", list(comp_options.keys()))
    selected_comp_id = comp_options[selected_competition]
    
    filtered_seasons = df_comp_seasons[df_comp_seasons["competition_id"] == selected_comp_id]
    season_options = {f"{row['season_name']} ({row['season_id']})": row['season_id'] for _, row in filtered_seasons.iterrows()}
    selected_season = st.sidebar.selectbox("Choose Season", list(season_options.keys()))
    selected_season_id = season_options[selected_season]
    
    # Analysis selection
    analysis_option = st.sidebar.radio("Select Analysis Type", ["Visualise Player Aspects", "Analyse Match"])
    
    if analysis_option == "Visualise Player Aspects":
        # Visualization selection
        visualization_option = st.sidebar.radio("Choose Visualization", ["Bar Plot", "Scatter Plot"])
        
        # Fetch Physical Performance Data
        client = SkillcornerClient(username=USERNAME, password=PASSWORD)
        data = client.get_physical(params={
            'competition': selected_comp_id,
            'season': selected_season_id,
            'group_by': 'player,team,competition,season,group',
            'possession': 'all,tip,otip',
            'playing_time__gte': 60, 
            'count_match__gte': 8,
            'data_version': '3'
        })
        
        df_physical = pd.DataFrame(data)
        metrics = p_utils.add_standard_metrics(df_physical)
        df_physical['plot_label'] = df_physical['player_short_name'] + ' | ' + df_physical['position_group']
        
        if visualization_option == "Bar Plot":
            team_options = list(df_physical["team_name"].unique())
            selected_team = st.sidebar.selectbox("Choose Team", team_options)
            selected_metric = st.sidebar.selectbox("Choose Metric", metrics)
            st.subheader(f"Bar Plot: {selected_metric} for {selected_team}")
            fig, ax = bar.plot_bar_chart(
                df=df_physical[df_physical['team_name'] == selected_team],
                metric=selected_metric,
                label=f'{selected_metric} Metric',
                unit='km/h',
                add_bar_values=True,
                data_point_id='player_id',
                data_point_label='plot_label'
            )
            st.pyplot(fig)
        else:
            team_options = list(df_physical["team_name"].unique())
            primary_highlight_team = st.sidebar.selectbox("Choose Primary Highlight Team", team_options)
            secondary_highlight_team = st.sidebar.selectbox("Choose Secondary Highlight Team", team_options)
            
            x_metric = st.sidebar.selectbox("Choose X-Axis Metric", metrics)
            y_metric = st.sidebar.selectbox("Choose Y-Axis Metric", metrics)
            st.subheader(f"Scatter Plot: {x_metric} vs {y_metric}")
            fig, ax = scatter.plot_scatter(
                df=df_physical,
                x_metric=x_metric,
                y_metric=y_metric,
                data_point_id='team_name',
                data_point_label='player_short_name',
                primary_highlight_group=[primary_highlight_team],
                secondary_highlight_group=[secondary_highlight_team]
            )
            st.pyplot(fig)
        pass
    else:
        st.subheader("Analyse Match")
        filtered_matches = df_matches[(df_matches["competition_id"] == selected_comp_id) & (df_matches["season_id"] == selected_season_id)]
        st.dataframe(filtered_matches)
        
        # Select a Match
        match_options = {f"{row['date_time']} - {row['home_team']['short_name']} vs {row['away_team']['short_name']}": row['id'] for _, row in filtered_matches.iterrows()}
        selected_match = st.sidebar.selectbox("Choose Match", list(match_options.keys()))
        selected_match_id = match_options[selected_match]
        
        # Fetch Dynamic Events
        if st.button("Fetch Dynamic Events"):
            df_dynamic_events = fetch_dynamic_events(selected_match_id)
            if df_dynamic_events is not None:
                st.subheader("Dynamic Events Data")
                st.dataframe(df_dynamic_events)
        
        # File uploader for user-uploaded dynamic events CSV
        uploaded_file = st.file_uploader("Upload Dynamic Events CSV File", type=["csv"])
        if uploaded_file is not None:
            df_uploaded = pd.read_csv(uploaded_file)
            st.subheader("Uploaded Dynamic Events Data")
            st.dataframe(df_uploaded)
else:
    st.write("❌ Data Load Failed")
