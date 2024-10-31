import streamlit as st
import pandas as pd
import plotly.express as px

# Set Streamlit page configuration
st.set_page_config(page_title="Utility Dashboard", layout="wide")

# Title of the App
st.title("Utility Dashboard")

# Sidebar Filters
st.sidebar.header("Filter Options")

# Default file paths if no files are uploaded
default_commodity_file = 'utility.xlsx'  # Update with your file path
default_temperature_file = 'tempdata.xlsx'  # Update with your file path

# Load the datasets
progress_bar = st.sidebar.progress(0)

try:
    data_commodity = pd.read_excel(default_commodity_file)
except FileNotFoundError:
    st.error(f"Default commodity file '{default_commodity_file}' not found. Please ensure the file is available.")
    st.stop()

try:
    data_temperature = pd.read_excel(default_temperature_file)
except FileNotFoundError:
    st.error(f"Default temperature file '{default_temperature_file}' not found. Please ensure the file is available.")
    st.stop()

progress_bar.progress(20)

# Ensure 'BillStartDate' and 'BillEndDate' are in datetime format in the commodity dataset
for date_col in ['BillStartDate', 'BillEndDate']:
    if date_col in data_commodity.columns:
        data_commodity[date_col] = pd.to_datetime(data_commodity[date_col], errors='coerce')
    else:
        st.error(f"Column '{date_col}' not found in the commodity dataset.")
        st.stop()

# Extract 'TAVG' (temperature) and 'Year-month' from the temperature dataset
if 'Year-month' in data_temperature.columns and 'TAVG' in data_temperature.columns:
    data_temperature['Year-month'] = pd.to_datetime(data_temperature['Year-month'], format='%Y-%m')
else:
    st.error("The temperature dataset must contain 'Year-month' and 'TAVG' columns.")
    st.stop()

progress_bar.progress(40)

# Campus selection (always required)
selected_campus = st.sidebar.selectbox('Select Campus', sorted(data_commodity['ComplexName'].dropna().unique()))

# Filter data by selected campus to get available commodities, buildings, meters, and years
filtered_campus_data = data_commodity[data_commodity['ComplexName'] == selected_campus]

# Commodity selection (filtered based on the selected campus)
available_commodities = sorted(filtered_campus_data['Commodity'].dropna().unique())
selected_commodity = st.sidebar.selectbox('Select Commodity', available_commodities)

# Filter the dataset based on the selected commodity
commodity_filtered_data = filtered_campus_data[filtered_campus_data['Commodity'] == selected_commodity]

# Building Name selection (filtered based on selected commodity)
available_buildings = sorted(commodity_filtered_data['BuildingName'].dropna().unique())
selected_buildings = st.sidebar.multiselect('Select Building(s) (Optional)', available_buildings, default=[])

# Meter Name selection (filtered based on selected building(s))
if selected_buildings:
    building_filtered_data = commodity_filtered_data[commodity_filtered_data['BuildingName'].isin(selected_buildings)]
else:
    building_filtered_data = commodity_filtered_data

available_meters = sorted(building_filtered_data['MeterName'].dropna().unique())
selected_meters = st.sidebar.multiselect('Select Meter(s) (Optional)', available_meters, default=[])

# Year selection (filtered based on selected commodity and buildings)
available_years = sorted(building_filtered_data['Year'].dropna().unique())
selected_years = st.sidebar.multiselect('Select Year(s) (Optional)', available_years, default=[])

# Filter the data based on selected filters
filtered_data = building_filtered_data

if selected_meters:
    filtered_data = filtered_data[filtered_data['MeterName'].isin(selected_meters)]

if selected_years:
    filtered_data = filtered_data[filtered_data['Year'].isin(selected_years)]

progress_bar.progress(60)

# Handle the case when no data is available after filtering
if filtered_data.empty:
    st.warning("No data available for the selected filters. Please adjust your filter options.")
    st.stop()

# Extract unique unit(s)
units = filtered_data['Units'].dropna().unique()
if len(units) == 1:
    unit = units[0]
elif len(units) > 1:
    unit = "Multiple Units"
else:
    unit = "Units"

# Create a date range for each billing period
filtered_data['DateRange'] = filtered_data.apply(
    lambda row: pd.date_range(start=row['BillStartDate'], end=row['BillEndDate']).tolist(),
    axis=1
)

# Explode the date range into individual dates
df_exploded = filtered_data.explode('DateRange')

# Calculate the number of billing days
df_exploded['BillDays'] = (df_exploded['BillEndDate'] - df_exploded['BillStartDate']).dt.days + 1

# Handle division by zero or missing 'BillDays'
df_exploded['BillDays'] = df_exploded['BillDays'].replace(0, pd.NA)
df_exploded['DailyConsumption'] = df_exploded['TotalConsumption'] / df_exploded['BillDays']
df_exploded['DailyConsumption'] = df_exploded['DailyConsumption'].fillna(0)

# Merge the temperature data based on 'Year-Month'
df_exploded['Year-month'] = df_exploded['DateRange'].dt.to_period('M').dt.to_timestamp()
df_exploded = pd.merge(df_exploded, data_temperature[['Year-month', 'TAVG']], on='Year-month', how='left')

# Add a radio button to allow users to select the normalization method
normalization_method = st.sidebar.radio(
    "Choose Normalization Method",
    options=["None", "Weather Normalized Energy Use", "Energy Use Intensity (EUI)"]
)

# Select the appropriate data based on the user's selection
if normalization_method == "Weather Normalized Energy Use" and 'TAVG' in df_exploded.columns:
    df_exploded['TAVG'] = df_exploded['TAVG'].replace(0, pd.NA)  # Avoid division by zero
    df_exploded['NormalizedConsumption'] = df_exploded['TotalConsumption'] / df_exploded['TAVG']
    df_exploded['NormalizedConsumption'] = df_exploded['NormalizedConsumption'].fillna(0)  # Handle any NaN values
    y_axis_column = 'NormalizedConsumption'
    y_axis_title = f'Normalized Consumption ({unit} / celsius)'
elif normalization_method == "Energy Use Intensity (EUI)" and 'BuildingSizeSQFT' in df_exploded.columns:
    df_exploded['BuildingSizeSQFT'] = df_exploded['BuildingSizeSQFT'].replace(0, pd.NA)  # Avoid division by zero
    df_exploded['NormalizedConsumption'] = df_exploded['TotalConsumption'] / df_exploded['BuildingSizeSQFT']
    df_exploded['NormalizedConsumption'] = df_exploded['NormalizedConsumption'].fillna(0)
    y_axis_column = 'NormalizedConsumption'
    y_axis_title = f'Normalized Consumption ({unit} / SQFT)'
else:
    y_axis_column = 'TotalConsumption'
    y_axis_title = f'Total Consumption ({unit})'

progress_bar.progress(80)

# ---- First Visualization: Time Series plot with full date axis ----
st.header(f"{y_axis_title} Over Time (Monthly Aggregation)")
st.write("This time series visualization shows the consumption of the selected commodity over time, aggregated by month.")
consumption_by_month = df_exploded.groupby('Year-month')[[y_axis_column]].sum().reset_index()
if not consumption_by_month.empty:
    time_series_fig = px.line(
        consumption_by_month,
        x='Year-month',
        y=y_axis_column,
        title=f"{y_axis_title} of {selected_commodity} for {selected_campus} Over Time (Monthly Aggregation)",
        markers=True
    )

    # Customize the layout
    time_series_fig.update_layout(
        xaxis_title='Month',
        yaxis_title=y_axis_title,
        xaxis_tickangle=-45,  # Rotate x-axis labels
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',  # Transparent background
        title={'x': 0.5, 'xanchor': 'center'},  # Center the title
        xaxis=dict(showgrid=True),
        yaxis=dict(showgrid=True),
    )

    # Display the time series plot
    st.plotly_chart(time_series_fig, use_container_width=True)
else:
    st.info(f"No data available for the {y_axis_title} Time Series visualization.")

# ---- Second Visualization: Clustered bar chart of TotalConsumption across months, clustered by year ----
st.header(f"Monthly {y_axis_title} by Building for {selected_commodity} - {selected_campus}")
st.write("This clustered bar chart compares the monthly consumption of the selected commodity for different buildings, grouped by month.")

# Ensure months are in the correct order (January to December)
df_exploded['Month'] = df_exploded['DateRange'].dt.month

# Group by 'Month' and 'BuildingName' to get the monthly consumption for each building
monthly_consumption_building = df_exploded.groupby(['Month', 'BuildingName'])[y_axis_column].sum().reset_index()

# Map numeric months to their names
monthly_consumption_building['Month'] = monthly_consumption_building['Month'].map({
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
})

# Create a grouped bar chart, where each building has a separate bar for each month
if not monthly_consumption_building.empty:
    clustered_bar_chart_fig = px.bar(
        monthly_consumption_building,
        x='Month',
        y=y_axis_column,
        color='BuildingName',  # Differentiate by building using color
        barmode='group',  # Group bars side-by-side for comparison
        title=f"Monthly {y_axis_title} by Building for {selected_commodity} in {selected_campus}"
    )

    # Customize layout
    clustered_bar_chart_fig.update_layout(
        xaxis_title='Month',
        yaxis_title=y_axis_title,
        plot_bgcolor='rgba(0,0,0,0)',  # Transparent background
        legend_title_text='Building',
        xaxis_tickangle=-45  # Rotate x-axis labels
    )

    st.plotly_chart(clustered_bar_chart_fig, use_container_width=True)
else:
    st.info(f"No data available for the {y_axis_title} Clustered Bar Chart visualization.")

# ---- Third Visualization: TotalConsumption by PrimaryUse and Year ----
primaryuse_consumption = df_exploded.groupby(['Year', 'PrimaryUse'])[y_axis_column].sum().reset_index()

st.header(f"Total {y_axis_title} by Primary Use and Year")
st.write("This clustered bar chart compares the total consumption by the primary use of the building for different years.")

if not primaryuse_consumption.empty:
    primaryuse_bar_chart_fig = px.bar(
        primaryuse_consumption,
        x='PrimaryUse',
        y=y_axis_column,
        color='Year',
        barmode='group',
        title=f"Total {y_axis_title} by Primary Use and Year"
    )

    primaryuse_bar_chart_fig.update_layout(
        xaxis_title='Primary Use',
        yaxis_title=y_axis_title,
        plot_bgcolor='rgba(0,0,0,0)'  # Transparent background
    )

    st.plotly_chart(primaryuse_bar_chart_fig, use_container_width=True)
else:
    st.info(f"No data available for the {y_axis_title} by Primary Use visualization.")

# ---- Fourth Visualization: Scatterplot of Total Consumption versus Building Size ----
if 'BuildingSizeSQFT' in df_exploded.columns and 'TotalCost' in df_exploded.columns:
    st.header(f"Total {y_axis_title} vs Building Size (Bubble size represents TotalCost)")

    consumption_building_size = df_exploded.groupby('BuildingName').agg({
        y_axis_column: 'sum',
        'TotalCost': 'sum',
        'BuildingSizeSQFT': 'first'
    }).reset_index()

    if not consumption_building_size.empty:
        scatterplot_fig = px.scatter(
            consumption_building_size,
            x='BuildingSizeSQFT',
            y=y_axis_column,
            size='TotalCost',
            hover_name='BuildingName',
            title=f"Total {y_axis_title} vs Building Size for {selected_commodity} in {selected_campus}"
        )

        scatterplot_fig.update_layout(
            xaxis_title='Building Size (sq ft)',
            yaxis_title=y_axis_title,
            plot_bgcolor='rgba(0,0,0,0)'  # Transparent background
        )

        st.plotly_chart(scatterplot_fig, use_container_width=True)
    else:
        st.info(f"No data available for the {y_axis_title} vs Building Size scatterplot.")
else:
    st.warning("The dataset does not contain a 'BuildingSizeSQFT' column.")

# ---- Documentation Section ----
st.sidebar.markdown("### Insights & Analysis")
st.sidebar.write("""
1. **Consumption Trends:** Visualize total or normalized consumption over time.
2. **Monthly Comparisons:** Clustered bar charts show how monthly consumption compares across years.
3. **Building Analysis:** View the relationship between total consumption and building size.
4. **Usage by Primary Use:** Compare total consumption by primary use across years.
5. **Weather Normalized Energy Use: adjust energy usage for variations in weather, allowing for a fair comparison of energy use across time or between buildings with similar weather patterns.Temperature data in Celcius which was gotten from NOAA.
""")
