import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import os
from hevysync import HevySync
import plotly.graph_objects as go

st.set_page_config(page_title="Hevy Analytics 2026", layout="wide", page_icon="🏋️")

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

sync_engine = get_sync_engine(user_input)
if not os.path.exists(sync_engine.db):
    st.error(f"### ⚠️ Database for '{user_input}' Not Found")
    st.stop()

data = load_analytics_data(sync_engine)

# Filtering Logic - Keep 'Warm Up' here to block mobility drills if mapped there.
excluded_categories = ['Cardio', 'Warm Up'] 
strength_only_df = data[~data['muscle_group'].isin(excluded_categories)]

with st.sidebar:
    st.header("📊 Strength Filters")
    # Generate options from the filtered strength dataframe to avoid showing 'Cardio' options
    strength_muscle_options = sorted(strength_only_df['muscle_group'].unique())
    selected_muscles = st.multiselect(
        "Focus Muscle Groups", 
        options=strength_muscle_options,
        default=strength_muscle_options
    )
    # Use start_time for accurate session counts in the sidebar metric too
    st.sidebar.metric("Total Active Days", data['workout_date'].nunique())

filtered_strength_df = strength_only_df[strength_only_df['muscle_group'].isin(selected_muscles)]

chart_config = {
    'displayModeBar': False,
    'responsive': True,
    'staticPlot': False
}

######################################################################
# Top Bar Metrics
######################################################################

st.title("🏋️ Hevy Performance Dashboard")
m1, m2, m3, m4 = st.columns(4)

# metric calculations using rounded values and proper session counting
m1.metric("Lifting Volume", f"{round(filtered_strength_df['volume'].sum()):,} kg")
m2.metric("Total Reps", f"{int(filtered_strength_df['reps'].sum() or 0):,}")
m3.metric("Lifting Sessions", filtered_strength_df['start_time'].nunique())
m4.metric("Avg Volume/Set", f"{round(filtered_strength_df['volume'].mean(), 1)} kg")

######################################################################
# Progressive Overload
######################################################################

st.divider()
st.subheader("🚀 Progressive Overload (Top Sets)")

# Include sets with volume > 0 to capture bodyweight progress like Climbing/Pullups
weighted_df = filtered_strength_df[filtered_strength_df['volume'] > 0].copy()
exercise_counts = weighted_df.groupby('exercise_name')['workout_date'].nunique()
frequent_exercises = exercise_counts[exercise_counts >= 5].index.tolist()
weighted_df = weighted_df[weighted_df['exercise_name'].isin(frequent_exercises)]

col_select, col_toggle = st.columns([3, 1])
with col_select:
    display_options = sorted(list(set([simplify_name(ex) for ex in frequent_exercises])))
    selected_groups = st.multiselect("Select Movement Patterns", options=display_options)
with col_toggle:
    aggregate_view = st.toggle("Combine Variants", value=False)

if selected_groups:
    plot_df = weighted_df.copy()
    plot_df['simplified_name'] = plot_df['exercise_name'].apply(simplify_name)
    plot_df = plot_df[plot_df['simplified_name'].isin(selected_groups)]

    # 1. CALCULATE E1RM (Brzycki Formula)
    plot_df['e1rm'] = plot_df['weight_kg'] / (1.0278 - (0.0278 * plot_df['reps']))
    
    # 2. COLLAPSE TO DAILY MAX E1RM
    daily_peaks = plot_df.groupby(['workout_date', 'exercise_name'], as_index=False)['e1rm'].max()

    # 3. SMOOTHING
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
    
    st.plotly_chart(fig_e1rm, config=chart_config, use_container_width=True)
else:
    st.info("Select a movement pattern above to see your progress.")


######################################################################
# Weekly Volume Trend
######################################################################
st.subheader("📈 Enhanced Weekly Volume Trend")

df_vol = filtered_strength_df.copy()
df_vol['workout_date'] = pd.to_datetime(df_vol['workout_date'])
df_vol['year'] = df_vol['workout_date'].dt.isocalendar().year
df_vol['week'] = df_vol['workout_date'].dt.isocalendar().week
df_vol['sort_key'] = df_vol['year'] * 100 + df_vol['week']

weekly_data = df_vol.groupby(['sort_key', 'week_year', 'muscle_group'])['volume'].sum().reset_index()

all_weeks = weekly_data[['sort_key', 'week_year']].drop_duplicates()
all_muscles = weekly_data['muscle_group'].unique()

dense_data = weekly_data.groupby(['sort_key', 'muscle_group'])['volume'].sum().reset_index()

dense_index = pd.MultiIndex.from_product(
    [all_weeks['sort_key'].unique(), all_muscles], 
    names=['sort_key', 'muscle_group']
)

weekly_data = dense_data.set_index(['sort_key', 'muscle_group']).reindex(dense_index, fill_value=0).reset_index()

weekly_data = weekly_data.merge(all_weeks, on='sort_key', how='left')
weekly_data = weekly_data.sort_values('sort_key')

# INTERACTIVE PICKER
selected_muscles_vol = st.multiselect(
    "Focus Muscle Groups (Volume Trend)", 
    options=sorted(all_muscles), 
    default=sorted(all_muscles)
)
filtered_weekly = weekly_data[weekly_data['muscle_group'].isin(selected_muscles_vol)]

# CALCULATE TREND
totals = filtered_weekly.groupby(['sort_key', 'week_year'])['volume'].sum().reset_index()
totals = totals.sort_values('sort_key')
totals['moving_avg'] = totals['volume'].rolling(window=4, min_periods=1).mean()

fig_vol = go.Figure()

for muscle in selected_muscles_vol:
    m_df = filtered_weekly[filtered_weekly['muscle_group'] == muscle]
    fig_vol.add_trace(go.Bar(
        x=m_df['week_year'], 
        y=m_df['volume'], 
        name=muscle
    ))

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

st.plotly_chart(fig_vol, config=chart_config, use_container_width=True)


######################################################################
# Muscle Radar
######################################################################
st.subheader("🎯 Muscle Volume Distribution & Progress")

df_radar = filtered_strength_df.copy()
df_radar['workout_date'] = pd.to_datetime(df_radar['workout_date'])
latest_date = df_radar['workout_date'].max()

# Ensure we have a valid start date (fallback to today if no data)
if pd.isnull(latest_date):
    latest_date = pd.Timestamp.now()

# UI Controls
col1, col2 = st.columns([2, 1])
with col1:
    radar_mode = st.radio(
        "Compare Focus Over:", 
        ["1 Month", "3 Months", "6 Months", "1 Year", "Specific Month"], 
        horizontal=True
    )

# Date Logic Calculation
if radar_mode == "Specific Month":
    # --- MONTH STEPPER LOGIC ---
    
    if 'radar_selected_month' not in st.session_state:
        # Default to the 1st day of your latest workout month
        st.session_state.radar_selected_month = latest_date.replace(day=1)

    with col2:
            # SPACER STRATEGY:
            # [Spacer] [Prev] [Month Name] [Next] [Spacer]
            # This forces the middle 3 elements to be close together in the center of the column
            _, c_prev, c_disp, c_next, _= st.columns([1,  0.5, 2, 0.5, 1])
            
            # Previous Button
            if c_prev.button("◀️", key="radar_prev"):
                st.session_state.radar_selected_month -= pd.DateOffset(months=1)
                st.rerun()

            # Next Button
            if c_next.button("▶️", key="radar_next"):
                st.session_state.radar_selected_month += pd.DateOffset(months=1)
                st.rerun()

            # Display Current Month (Centered and vertically aligned)
            current_view = st.session_state.radar_selected_month
            c_disp.markdown(
                f"<div style='text-align: center; white-space: nowrap; font-weight: bold; padding-top: 5px;'>{current_view.strftime('%B %Y')}</div>", 
                unsafe_allow_html=True
            )
            
    # Calculate Ranges based on Session State
    # Current Month Range
    current_start = st.session_state.radar_selected_month
    next_month_start = current_start + pd.offsets.MonthBegin(1)
    current_end = next_month_start - pd.Timedelta(days=1)
    
    # Previous Month Range (The benchmark)
    prev_start = current_start - pd.offsets.MonthBegin(1)
    prev_end = current_start - pd.Timedelta(days=1)
    
    label_curr = current_start.strftime("%B %Y")
    label_prev = prev_start.strftime("%B %Y")

else:
    # Relative Logic (Anchored to latest workout)
    period_map = {"1 Month": 30, "3 Months": 90, "6 Months": 180, "1 Year": 365}
    days = period_map[radar_mode]
    
    current_end = latest_date
    current_start = current_end - pd.Timedelta(days=days)
    
    prev_end = current_start - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=days)
    
    label_curr = f"Current {radar_mode}"
    label_prev = f"Previous {radar_mode}"

df_curr = df_radar[(df_radar['workout_date'] >= current_start) & (df_radar['workout_date'] <= current_end)]
df_prev = df_radar[(df_radar['workout_date'] >= prev_start) & (df_radar['workout_date'] <= prev_end)]

curr_sets = df_curr.groupby('muscle_group').size().reset_index(name='sets')
prev_sets = df_prev.groupby('muscle_group').size().reset_index(name='sets')

all_muscles_radar = sorted(df_radar['muscle_group'].unique())
curr_sets = curr_sets.set_index('muscle_group').reindex(all_muscles_radar, fill_value=0).reset_index()
prev_sets = prev_sets.set_index('muscle_group').reindex(all_muscles_radar, fill_value=0).reset_index()

curr_closed = pd.concat([curr_sets, curr_sets.iloc[[0]]])
prev_closed = pd.concat([prev_sets, prev_sets.iloc[[0]]])

fig_radar = go.Figure()

fig_radar.add_trace(go.Scatterpolar(
    r=prev_closed['sets'],
    theta=prev_closed['muscle_group'],
    fill='toself',
    name=label_prev,
    line_color='rgba(255, 255, 255, 0.2)',
    fillcolor='rgba(255, 255, 255, 0.1)'
))

fig_radar.add_trace(go.Scatterpolar(
    r=curr_closed['sets'],
    theta=curr_closed['muscle_group'],
    fill='toself',
    name=label_curr,
    line_color='#00CC96',
    fillcolor='rgba(0, 204, 150, 0.3)'
))

fig_radar.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, showticklabels=False, gridcolor='rgba(255,255,255,0.1)',showline=False),
        angularaxis=dict(gridcolor='rgba(255,255,255,0.1)')
    ),
    template="plotly_dark",
    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
    margin=dict(t=20, b=20, l=40, r=40)
)

st.plotly_chart(fig_radar, config=chart_config, use_container_width=True)

######################################################################
# Heat Map
######################################################################

st.divider()
st.subheader("📅 Training Consistency")

start_date = data['workout_date'].min()
end_date = data['workout_date'].max()
all_days = pd.date_range(start=start_date, end=end_date, freq='D')

full_df = pd.DataFrame({'workout_date': all_days})
full_df['week'] = full_df['workout_date'].dt.strftime('%G-W%V')
full_df['day'] = full_df['workout_date'].dt.day_name()
full_df['hover_date'] = full_df['workout_date'].dt.strftime('%b %d %Y')

actual_sessions = data.groupby('workout_date')['start_time'].nunique().reset_index(name='sessions')
actual_sessions['workout_date'] = pd.to_datetime(actual_sessions['workout_date'])

merged = pd.merge(full_df, actual_sessions, on='workout_date', how='left')

merged['sessions'] = merged['sessions'].fillna(0)

days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

heatmap_data = merged.pivot(index='day', columns='week', values='sessions').reindex(days_order)
heatmap_dates = merged.pivot(index='day', columns='week', values='hover_date').reindex(days_order)

custom_colors = [
    "#ffffff",  # 0: White (Blank)
    "#29953d",  # 1: Light Green
    "#13632A",  # 2: Darker Green
    "#064518"   # 3+: Darkest Green
]

fig_heat = px.imshow(
    heatmap_data, 
    color_continuous_scale=custom_colors,
    zmin=0, 
    zmax=3, 
    template="plotly_dark",
    aspect="auto",
)

fig_heat.update_traces(
    customdata=heatmap_dates,
    hovertemplate="%{customdata}<br>Sessions: %{z}<extra></extra>",
    xgap=2, 
    ygap=2
)

fig_heat.update_layout(
    height=320, 
    coloraxis_showscale=False,
    margin=dict(l=0, r=0, t=30, b=0),
    xaxis=dict(title="", showgrid=False),
    yaxis=dict(title="", showgrid=False, tickmode='array', tickvals=[0,1,2,3,4,5,6], ticktext=days_order)
)

st.plotly_chart(fig_heat, config=chart_config)


######################################################################
# Muscle Strength Index
######################################################################
st.subheader("💪 Ultimate Muscle Strength Index")

df_idx = filtered_strength_df.copy()
df_idx['e1rm'] = df_idx['weight_kg'] / (1.0278 - (0.0278 * df_idx['reps']))
df_idx['ex_max'] = df_idx.groupby('exercise_name')['e1rm'].transform('max')
df_idx['score'] = (df_idx['e1rm'] / df_idx['ex_max']) * 100

muscle_trend = df_idx.groupby(['workout_date', 'muscle_group'], as_index=False)['score'].max()
muscle_trend = muscle_trend.sort_values('workout_date')

muscle_trend['smoothed'] = muscle_trend.groupby('muscle_group')['score'].transform(
    lambda x: x.rolling(window=14, min_periods=1, center=True).mean()
)

col1, col2 = st.columns([3, 1])

with col1:
    all_muscles_idx = sorted(muscle_trend['muscle_group'].unique())
    selected_muscles_idx = st.multiselect(
        "Select Muscle Groups", 
        options=all_muscles_idx, 
        default=all_muscles_idx
    )

with col2:
    view_mode = st.radio("Y-Axis View", ["Zoomed (80-100%)", "Full (Show All)"], horizontal=True)

plot_data = muscle_trend[muscle_trend['muscle_group'].isin(selected_muscles_idx)]
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

st.plotly_chart(fig_final, config=chart_config)

######################################################################
# Detailed Exercise Logs
######################################################################

st.subheader("Detailed Exercise Logs")
# Use dataframe with use_container_width instead of width='stretch' if possible, or just default behavior
st.dataframe(
    filtered_strength_df[['start_time', 'exercise_name', 'weight_kg', 'reps', 'volume']].sort_values('start_time', ascending=False), 
    width='stretch', 
    hide_index=True
)
