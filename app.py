import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import os
from hevysync import HevySync
import plotly.graph_objects as go

# --- Page Config ---
st.set_page_config(page_title="Hevy Analytics 2026", layout="wide", page_icon="🏋️")

# --- Helper Functions ---
@st.cache_resource
def get_sync_engine(username):
    return HevySync(username=username)

def simplify_name(name):
    """Groups variants like (Barbell) or (Dumbbell) into a single movement pattern."""
    suffixes = [' (Barbell)', ' (Dumbbell)', ' (Smith Machine)', ' - Barbell', ' - Dumbbell', ' (Close Grip)']
    for s in suffixes:
        name = name.replace(s, '')
    return name.strip()

def load_analytics_data(engine):
    query = "SELECT * FROM v_workout_analytics"
    df = pd.read_sql(query, engine.conn)
    df['start_time'] = pd.to_datetime(df['start_time']).dt.tz_localize(None)
    # Essential for preventing zigzags: create a date-only column for aggregation
    df['workout_date'] = df['start_time'].dt.date
    return df

# --- Sidebar: User & Sync ---
with st.sidebar:
    st.header("👤 User Settings")
    user_input = st.text_input("Hevy Username", value="martin")
    
    if st.button("🔄 Sync New Workouts"):
        with st.spinner("Fetching data from Hevy..."):
            engine = get_sync_engine(user_input)
            engine.sync_workouts()
            st.rerun()
    st.divider()

# --- Initialize Engine & Load Data ---
sync_engine = get_sync_engine(user_input)

if not os.path.exists(sync_engine.db):
    st.error(f"### ⚠️ Database Not Found")
    st.stop()

data = load_analytics_data(sync_engine)

if data.empty:
    st.warning("No workout data found.")
    st.stop()

# --- Global Filtering Logic ---
excluded_categories = ['Cardio', 'Warm Up']
strength_only_df = data[~data['muscle_group'].isin(excluded_categories)]

with st.sidebar:
    st.header("📊 Strength Filters")
    strength_muscle_options = sorted(strength_only_df['muscle_group'].unique())
    selected_muscles = st.multiselect(
        "Focus Muscle Groups", 
        options=strength_muscle_options,
        default=strength_muscle_options,
        key="sidebar_muscle_filter"
    )
    st.sidebar.metric("Total Active Days (All)", data['start_time'].dt.date.nunique())

# Sidebar filter applied to main dataframe
filtered_strength_df = strength_only_df[strength_only_df['muscle_group'].isin(selected_muscles)]

# --- Dashboard UI ---
st.title("🏋️ Hevy Performance Dashboard")

# --- Metrics Row ---
m1, m2, m3, m4 = st.columns(4)
total_vol = int(filtered_strength_df['volume'].sum())
m1.metric("Lifting Volume", f"{total_vol:,} kg")
m2.metric("Total Reps", int(filtered_strength_df['reps'].sum() or 0))
m3.metric("Lifting Sessions", filtered_strength_df['start_time'].dt.date.nunique())
m4.metric("Avg Volume/Set", f"{round(filtered_strength_df['volume'].mean(), 1)} kg")

# --- Progressive Overload (Top Sets) ---
st.divider()
st.subheader("🚀 Progressive Overload (Top Sets)")

# 1. PRE-FILTER: Weight > 0 and Min 5 Sessions
weighted_df = filtered_strength_df[filtered_strength_df['weight_kg'] > 0].copy()
exercise_counts = weighted_df.groupby('exercise_name')['start_time'].nunique()
frequent_exercises = exercise_counts[exercise_counts >= 5].index.tolist()
weighted_df = weighted_df[weighted_df['exercise_name'].isin(frequent_exercises)]

# 2. UI: Interactive Selection
col_select, col_toggle = st.columns([3, 1])

with col_select:
    display_options = sorted(list(set([simplify_name(ex) for ex in frequent_exercises])))
    selected_groups = st.multiselect(
        "Select Movement Patterns", 
        options=display_options,
        placeholder="Search (e.g. Bench Press)",
        key="movement_multiselect"
    )

with col_toggle:
    st.write("View Mode")
    aggregate_view = st.toggle("Combine Variants", value=False, key="agg_toggle")

# 3. Data Processing & Outlier Removal
if selected_groups:
    plot_df = weighted_df[weighted_df['exercise_name'].apply(simplify_name).isin(selected_groups)].copy()
    
    # Define outlier filter function
    def filter_outliers(group):
        if len(group) < 2: return group
        limit = group['weight_kg'].max() * 0.6
        return group[group['weight_kg'] >= limit]

    # Apply filter and FIX: include_groups=False silences the Pandas deprecation warning
    plot_df = plot_df.groupby('exercise_name', group_keys=False).apply(
        filter_outliers, 
        include_groups=False
    )

    # 4. Aggregation by DATE to fix zigzagging
    # Switching from start_time to workout_date ensures exactly one max point per day
    if aggregate_view:
        plot_df['display_name'] = plot_df['exercise_name'].apply(simplify_name)
        pr_data = plot_df.groupby(['workout_date', 'display_name'])['weight_kg'].max().reset_index()
        color_col = 'display_name'
    else:
        pr_data = plot_df.groupby(['workout_date', 'exercise_name'])['weight_kg'].max().reset_index()
        color_col = 'exercise_name'

    # Ensure sorting by date to prevent lines drawing out of order
    pr_data = pr_data.sort_values('workout_date')

    fig_pr = px.line(
        pr_data, 
        x='workout_date', 
        y='weight_kg', 
        color=color_col, 
        markers=True,
        template="plotly_dark",
        line_shape="linear"
    )
    
    fig_pr.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis_title="Max Weight (kg)",
        xaxis_title="",
        yaxis=dict(rangemode="normal") 
    )
    
    st.plotly_chart(fig_pr, width='stretch', key="overload_chart_v_final")
else:
    st.info("Select a movement pattern to track strength progression.")

# --- Volume & Balance ---
st.divider()
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Weekly Volume Trend")
    weekly = filtered_strength_df.groupby(['week_year', 'muscle_group'])['volume'].sum().reset_index()
    fig_weekly = px.bar(weekly, x='week_year', y='volume', color='muscle_group', barmode='stack', template="plotly_dark")
    st.plotly_chart(fig_weekly, width='stretch', key="weekly_volume_chart")

with col_right:
    st.subheader("Volume Distribution Balance")
    muscle_totals = filtered_strength_df.groupby('muscle_group')['volume'].sum().reset_index()
    fig_radar = go.Figure(data=go.Scatterpolar(r=muscle_totals['volume'], theta=muscle_totals['muscle_group'], fill='toself'))
    fig_radar.update_layout(template="plotly_dark", polar=dict(radialaxis=dict(visible=False)))
    st.plotly_chart(fig_radar, width='stretch', key="radar_volume_chart")

# --- 3-State Consistency Heatmap (All Activity) ---
st.divider()
st.subheader("📅 Full Year Training Consistency (All Activity)")

all_activity = data.copy()
all_activity['date'] = pd.to_datetime(all_activity['start_time']).dt.date
daily = all_activity.groupby('date')['start_time'].nunique().reset_index(name='sessions')

start_date, end_date = daily['date'].min(), daily['date'].max()
full_range = pd.date_range(start=start_date, end=end_date).date
calendar_df = pd.DataFrame({'date': full_range}).merge(daily, on='date', how='left').fillna(0)
calendar_df['state'] = calendar_df['sessions'].apply(lambda x: 2 if x > 1 else x)
calendar_df['date'] = pd.to_datetime(calendar_df['date'])
calendar_df['week'] = calendar_df['date'].dt.strftime('%G-W%V') 
calendar_df['day'] = calendar_df['date'].dt.day_name()

heatmap_input = calendar_df.groupby(['day', 'week'])['state'].max().reset_index()
heatmap_pivot = heatmap_input.pivot(index='day', columns='week', values='state').reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])

custom_colors = ["#161b22", "#26a641", "#39d353"]
fig_heat = px.imshow(heatmap_pivot, color_continuous_scale=custom_colors, zmin=0, zmax=2, template="plotly_dark", aspect="equal")
fig_heat.update_traces(xgap=3, ygap=3)
fig_heat.update_layout(
    height=320, 
    margin=dict(l=10, r=10, t=20, b=10),
    xaxis=dict(dtick=4, showgrid=False), 
    yaxis=dict(showgrid=False),
    coloraxis_colorbar=dict(
        title="Sessions",
        tickvals=[0, 1, 2],
        ticktext=["Rest", "1 Workout", "2+ Workouts"],
        lenmode="pixels", len=180
    )
)
st.plotly_chart(fig_heat, width='stretch', config={'displayModeBar': False}, key="consistency_heatmap_v3")

# --- Data Table ---
st.subheader("Exercise Logs (Strength Only)")
display_df = filtered_strength_df[['start_time', 'workout_name', 'exercise_name', 'set_index', 'weight_kg', 'reps', 'volume']].sort_values('start_time', ascending=False)
st.dataframe(display_df, width='stretch', hide_index=True, key="main_data_table")