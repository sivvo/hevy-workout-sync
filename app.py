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
    suffixes = [' (Barbell)', ' (Dumbbell)', ' (Smith Machine)', ' - Barbell', ' - Dumbbell', ' (Close Grip)']
    for s in suffixes:
        name = name.replace(s, '')
    return name.strip()

def load_analytics_data(engine):
    query = "SELECT * FROM v_workout_analytics"
    df = pd.read_sql(query, engine.conn)
    df['start_time'] = pd.to_datetime(df['start_time']).dt.tz_localize(None)
    # Using date instead of time prevents vertical zigzags on the same day
    df['workout_date'] = df['start_time'].dt.date
    return df

# --- Sidebar: User & Sync  ---
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
    st.error(f"### ⚠️ Database for '{user_input}' Not Found")
    st.stop()

data = load_analytics_data(sync_engine)

# --- Global Filtering Logic ---
excluded_categories = ['Cardio', 'Warm Up']
strength_only_df = data[~data['muscle_group'].isin(excluded_categories)]

with st.sidebar:
    st.header("📊 Strength Filters")
    strength_muscle_options = sorted(strength_only_df['muscle_group'].unique())
    selected_muscles = st.multiselect(
        "Focus Muscle Groups", 
        options=strength_muscle_options,
        default=strength_muscle_options
    )
    st.sidebar.metric("Total Active Days", data['workout_date'].nunique())

filtered_strength_df = strength_only_df[strength_only_df['muscle_group'].isin(selected_muscles)]

# 
######################################################################
######################################################################
#Top Bar
######################################################################
######################################################################


# --- Metrics Row ---
st.title("🏋️ Hevy Performance Dashboard")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Lifting Volume", f"{int(filtered_strength_df['volume'].sum()):,} kg")
m2.metric("Total Reps", int(filtered_strength_df['reps'].sum() or 0))
m3.metric("Lifting Sessions", filtered_strength_df['workout_date'].nunique())
m4.metric("Avg Volume/Set", f"{round(filtered_strength_df['volume'].mean(), 1)} kg")


######################################################################
######################################################################
#Progressive Overload
######################################################################
######################################################################

st.divider()
st.subheader("🚀 Progressive Overload (Top Sets)")

weighted_df = filtered_strength_df[filtered_strength_df['weight_kg'] > 0].copy()
exercise_counts = weighted_df.groupby('exercise_name')['workout_date'].nunique()
frequent_exercises = exercise_counts[exercise_counts >= 5].index.tolist()
weighted_df = weighted_df[weighted_df['exercise_name'].isin(frequent_exercises)]

col_select, col_toggle = st.columns([3, 1])
with col_select:
    display_options = sorted(list(set([simplify_name(ex) for ex in frequent_exercises])))
    selected_groups = st.multiselect("Select Movement Patterns", options=display_options)
with col_toggle:
    aggregate_view = st.toggle("Combine Variants", value=False)

# --- Updated Progressive Overload Section ---
# --- Updated Strength Logic using E1RM ---
if selected_groups:
    plot_df = weighted_df.copy()
    plot_df['simplified_name'] = plot_df['exercise_name'].apply(simplify_name)
    plot_df = plot_df[plot_df['simplified_name'].isin(selected_groups)]

    # 1. CALCULATE E1RM (Brzycki Formula)
    # This turns (60kg x 10) and (75kg x 2) into comparable numbers
    plot_df['e1rm'] = plot_df['weight_kg'] / (1.0278 - (0.0278 * plot_df['reps']))
    
    # 2. COLLAPSE TO DAILY MAX E1RM
    # This removes zigzags caused by multiple sets in one day
    daily_peaks = plot_df.groupby(['workout_date', 'exercise_name'], as_index=False)['e1rm'].max()

    # 3. SMOOTHING (Optional but recommended)
    # Adds a 3-session rolling average to show the true trend through deloads
    daily_peaks = daily_peaks.sort_values('workout_date')
    daily_peaks['smoothed_e1rm'] = daily_peaks.groupby('exercise_name')['e1rm'].transform(
        lambda x: x.rolling(window=3, min_periods=1).mean()
    )

    fig_e1rm = px.line(
        daily_peaks, 
        x='workout_date', 
        y='smoothed_e1rm', 
        color='exercise_name', 
        markers=True,
        template="plotly_dark",
        title="Strength Trend (Estimated 1-Rep Max)"
    )
    
    fig_e1rm.update_layout(
        hovermode="x unified",
        yaxis_title="Est. 1RM (kg)",
        yaxis=dict(rangemode="normal")
    )
    
    st.plotly_chart(fig_e1rm, width='stretch')
else:
    st.info("Select a movement pattern above to see your progress.")


######################################################################
######################################################################
#Weekly Volume Trend
######################################################################
######################################################################
st.subheader("📈 Enhanced Weekly Volume Trend")

# 1. DATA PREP & DATETIME CONVERSION
df_vol = filtered_strength_df.copy()
df_vol['workout_date'] = pd.to_datetime(df_vol['workout_date'])
df_vol['year'] = df_vol['workout_date'].dt.isocalendar().year
df_vol['week'] = df_vol['workout_date'].dt.isocalendar().week
df_vol['sort_key'] = df_vol['year'] * 100 + df_vol['week']

# 2. MANDATORY UNIQUE AGGREGATION
# This step collapses all sessions in a week into one row per muscle 
# to prevent the "non-unique multi-index" error
weekly_data = df_vol.groupby(['sort_key', 'week_year', 'muscle_group'])['volume'].sum().reset_index()

# 3. FIX: DENSE DATA REINDEXING (Prevents "Floating Bars")
# Capture unique mappings before reindexing
all_weeks = weekly_data[['sort_key', 'week_year']].drop_duplicates()
all_muscles = weekly_data['muscle_group'].unique()

# Reindex using only the keys needed for the matrix
# Using .groupby().first() here acts as a safety net for uniqueness
dense_data = weekly_data.groupby(['sort_key', 'muscle_group'])['volume'].sum().reset_index()

dense_index = pd.MultiIndex.from_product(
    [all_weeks['sort_key'].unique(), all_muscles], 
    names=['sort_key', 'muscle_group']
)

# This reindex now works because the previous groupby guaranteed uniqueness
weekly_data = dense_data.set_index(['sort_key', 'muscle_group']).reindex(dense_index, fill_value=0).reset_index()

# 4. RESTORE LABELS & SORT
weekly_data = weekly_data.merge(all_weeks, on='sort_key', how='left')
weekly_data = weekly_data.sort_values('sort_key')

# 5. INTERACTIVE PICKER
selected_muscles = st.multiselect(
    "Focus Muscle Groups", 
    options=sorted(all_muscles), 
    default=sorted(all_muscles)
)
filtered_weekly = weekly_data[weekly_data['muscle_group'].isin(selected_muscles)]

# 6. CALCULATE TREND (Using unique sort keys)
totals = filtered_weekly.groupby(['sort_key', 'week_year'])['volume'].sum().reset_index()
totals = totals.sort_values('sort_key')
totals['moving_avg'] = totals['volume'].rolling(window=4, min_periods=1).mean()

fig_vol = go.Figure()

# 7. ADD BARS (Properly Stacked and Grounded)
for muscle in selected_muscles:
    m_df = filtered_weekly[filtered_weekly['muscle_group'] == muscle]
    fig_vol.add_trace(go.Bar(
        x=m_df['week_year'], 
        y=m_df['volume'], 
        name=muscle
    ))

# 8. ADD TREND LINE
fig_vol.add_trace(go.Scatter(
    x=totals['week_year'], 
    y=totals['moving_avg'], 
    name='4-Week Trend',
    line=dict(color='white', width=3, dash='dot'),
    mode='lines'
))

fig_vol.update_layout(
    barmode='stack',
    template="plotly_dark",
    hovermode="x unified",
    xaxis=dict(type='category', categoryorder='array', categoryarray=totals['week_year'], tickangle=-45),
    yaxis=dict(title="Total Volume (kg)")
)

st.plotly_chart(fig_vol, use_container_width=True)


######################################################################
######################################################################
#Muscle Radar
######################################################################
######################################################################
# --- Muscle Volume Distribution (The Radar) ---
st.subheader("🎯 Muscle Volume Distribution & Progress")

# 1. Period Selection Logic
# Anchor all calculations to the latest workout date in your data
df_radar = filtered_strength_df.copy()
df_radar['workout_date'] = pd.to_datetime(df_radar['workout_date'])
latest_date = df_radar['workout_date'].max()

col1, col2 = st.columns([2, 1])
with col1:
    period_label = st.radio(
        "Compare Focus Over:", 
        ["1 Month", "3 Months", "6 Months", "1 Year"], 
        horizontal=True
    )

# Map labels to days for calculation
period_map = {"1 Month": 30, "3 Months": 90, "6 Months": 180, "1 Year": 365}
days = period_map[period_label]

# 2. Define Date Ranges
current_start = latest_date - pd.Timedelta(days=days)
prev_start = current_start - pd.Timedelta(days=days)

# 3. Filter and Aggregate
# Current Period Data
df_curr = df_radar[df_radar['workout_date'] > current_start]
curr_sets = df_curr.groupby('muscle_group').size().reset_index(name='sets')

# Previous Period Data (The Overlay)
df_prev = df_radar[(df_radar['workout_date'] > prev_start) & (df_radar['workout_date'] <= current_start)]
prev_sets = df_prev.groupby('muscle_group').size().reset_index(name='sets')

# 4. Align Muscle Groups (Ensure both traces have the same axes)
all_muscles = sorted(df_radar['muscle_group'].unique())
curr_sets = curr_sets.set_index('muscle_group').reindex(all_muscles, fill_value=0).reset_index()
prev_sets = prev_sets.set_index('muscle_group').reindex(all_muscles, fill_value=0).reset_index()

# ENSURE THE LOOP CLOSES
# We append the first row of data to the end of the dataframe
curr_closed = pd.concat([curr_sets, curr_sets.iloc[[0]]])
prev_closed = pd.concat([prev_sets, prev_sets.iloc[[0]]])

# 5. Create the Comparative Radar Chart
fig_radar = go.Figure()

# Trace 1: Previous Period (The faint "Shadow" or Benchmark)
fig_radar.add_trace(go.Scatterpolar(
    r=prev_closed['sets'],
    theta=prev_closed['muscle_group'],
    fill='toself',
    name=f'Previous {period_label}',
    line_color='rgba(255, 255, 255, 0.2)',
    fillcolor='rgba(255, 255, 255, 0.1)'
))

# Trace 2: Current Period (The Active Focus)
fig_radar.add_trace(go.Scatterpolar(
    r=curr_closed['sets'],
    theta=curr_closed['muscle_group'],
    fill='toself',
    name=f'Current {period_label}',
    line_color='#00CC96',
    fillcolor='rgba(0, 204, 150, 0.3)'
))

fig_radar.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, showticklabels=False, gridcolor='rgba(255,255,255,0.1)'),
        angularaxis=dict(gridcolor='rgba(255,255,255,0.1)')
    ),
    template="plotly_dark",
    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
    margin=dict(t=20, b=20, l=40, r=40)
)

st.plotly_chart(fig_radar, use_container_width=True)


######################################################################
######################################################################
#Heat Map
######################################################################
######################################################################


# --- Heatmap 
st.divider()
st.subheader("📅 Training Consistency")
daily = data.groupby('workout_date')['start_time'].nunique().reset_index(name='sessions')
daily['workout_date'] = pd.to_datetime(daily['workout_date'])
daily['week'] = daily['workout_date'].dt.strftime('%G-W%V') 
daily['day'] = daily['workout_date'].dt.day_name()
daily['state'] = daily['sessions'].apply(lambda x: 2 if x > 1 else x)

heatmap_pivot = daily.pivot(index='day', columns='week', values='state').reindex(
    ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
)

fig_heat = px.imshow(heatmap_pivot, color_continuous_scale=["#161b22", "#26a641", "#39d353"], 
                     zmin=0, zmax=2, template="plotly_dark")
fig_heat.update_layout(height=320, coloraxis_showscale=False)
st.plotly_chart(fig_heat, width='stretch')

######################################################################
######################################################################
#Exercise Logs
######################################################################
######################################################################

st.subheader("Detailed Exercise Logs")
st.dataframe(filtered_strength_df[['start_time', 'exercise_name', 'weight_kg', 'reps', 'volume']].sort_values('start_time', ascending=False), width='stretch', hide_index=True)

######################################################################
######################################################################
#Muscle Strengh Index
######################################################################
######################################################################
# --- Dashboard Header ---
st.subheader("💪 Ultimate Muscle Strength Index")

# 1. Processing Data (E1RM Normalization)
df_idx = filtered_strength_df.copy()
# Normalized E1RM eliminates zigzags caused by rep changes
df_idx['e1rm'] = df_idx['weight_kg'] / (1.0278 - (0.0278 * df_idx['reps']))
df_idx['ex_max'] = df_idx.groupby('exercise_name')['e1rm'].transform('max')
df_idx['score'] = (df_idx['e1rm'] / df_idx['ex_max']) * 100

# 2. Aggregation: Daily Peak per Muscle
# Taking the MAX per day ensures warmups don't create zigzags
muscle_trend = df_idx.groupby(['workout_date', 'muscle_group'], as_index=False)['score'].max()
muscle_trend = muscle_trend.sort_values('workout_date')

# 3. Smoothing (14-Day Rolling Window)
# Removes session jitter to reveal long-term trends
muscle_trend['smoothed'] = muscle_trend.groupby('muscle_group')['score'].transform(
    lambda x: x.rolling(window=14, min_periods=1, center=True).mean()
)

# --- NEW: User Controls for Readability ---
col1, col2 = st.columns([3, 1])

with col1:
    # Picker allows individual lines to be turned on/off
    all_muscles = sorted(muscle_trend['muscle_group'].unique())
    selected_muscles = st.multiselect(
        "Select Muscle Groups", 
        options=all_muscles, 
        default=all_muscles
    )

with col2:
    # Fix for data loss: Toggle between Zoomed and Full view
    view_mode = st.radio("Y-Axis View", ["Zoomed (80-100%)", "Full (Show All)"], horizontal=True)
# 4. Filter and Render
plot_data = muscle_trend[muscle_trend['muscle_group'].isin(selected_muscles)]
y_range = [80, 102] if view_mode == "Zoomed (80-100%)" else [None, 105]

fig_final = px.line(
    plot_data, 
    x='workout_date', 
    y='smoothed', 
    color='muscle_group',
    template="plotly_dark",
    title="Long-Term Strength Development (E1RM Normalized)"
)

fig_final.update_layout(
    yaxis=dict(range=y_range, title="Strength Index (%)"),
    xaxis=dict(title=""),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig_final, width='stretch')