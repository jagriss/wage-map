# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "folium",
#     "geopandas",
#     "marimo",
#     "numpy",
#     "pandas",
# ]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import numpy as np
    import geopandas as gpd
    import folium
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    from urllib.error import HTTPError

    return HTTPError, ThreadPoolExecutor, date, folium, gpd, mo, np, pd


@app.cell
def _(mo):
    mo.md("""
    # Wage Growth Aggregation Map in USA

    Compound growth of each state's minimum wage over the selected years.
    States without their own minimum wage fall back to the federal minimum.

    Data: minimum wages from [FRED](https://fred.stlouisfed.org/) (U.S. Department of Labor),
    state boundaries from the U.S. Census Bureau's cartographic boundary files.
    """)
    return


@app.cell
def _(gpd, mo):
    CENSUS_YEAR = 2025
    states_url = (
        f"https://www2.census.gov/geo/tiger/GENZ{CENSUS_YEAR}/shp/"
        f"cb_{CENSUS_YEAR}_us_state_20m.zip"
    )

    with mo.persistent_cache("census_states"):
        states_gdf = gpd.read_file(states_url)

    # keep the 50 states + DC (territories have FIPS codes of 60 and up)
    states_gdf = states_gdf[states_gdf["STATEFP"] < "60"]
    states_gdf = states_gdf[["STUSPS", "NAME", "geometry"]].rename(columns={"NAME": "State"})
    return (states_gdf,)


@app.cell
def _(HTTPError, ThreadPoolExecutor, date, mo, np, pd, states_gdf):
    FIRST_YEAR = 1968

    def fetch_fred(series_id, end):
        """Return a FRED series indexed by date, or None if FRED has no such series."""
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&coed={end}"
        try:
            series = pd.read_csv(url, index_col=0, parse_dates=True).iloc[:, 0]
        except HTTPError as e:
            # states with no minimum wage law (e.g. AL, MS) have no series
            if e.code == 404:
                return None
            raise
        # FRED marks missing observations with "."
        return pd.to_numeric(series, errors="coerce")

    @mo.persistent_cache
    def fetch_minimum_wages(state_codes, end):
        """Fetch the federal series and one series per state, keyed by postal code."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            series = pool.map(lambda code: fetch_fred(f"STTMINWG{code}", end), state_codes)
            return fetch_fred("FEDMINNFRWG", end), dict(zip(state_codes, series))

    # the end date is part of the cache key, so the data refreshes once a day
    federal, state_series = fetch_minimum_wages(
        tuple(sorted(states_gdf["STUSPS"])), date.today().isoformat()
    )

    # state series are annual (Jan 1); stop at the latest year FRED has published
    last_year = max(s.index.max().year for s in state_series.values() if s is not None)
    year_starts = pd.date_range(f"{FIRST_YEAR}-01-01", f"{last_year}-01-01", freq="YS")
    # federal series lists each change date; take the rate in effect on Jan 1 of each year
    federal_annual = federal.reindex(year_starts, method="ffill").to_numpy()

    wages = pd.concat(
        pd.DataFrame(
            {
                "Year": year_starts.year,
                "STUSPS": code,
                "State Minimum Wage": (
                    series.reindex(year_starts).to_numpy() if series is not None else np.nan
                ),
                "Federal Minimum Wage": federal_annual,
            }
        )
        for code, series in state_series.items()
    ).set_index(["Year", "STUSPS"])

    # replace missing State Minimum Wage data with Federal wage data
    wages["State Minimum Wage"] = (
        wages["State Minimum Wage"].replace(0, np.nan).fillna(wages["Federal Minimum Wage"])
    )
    return (wages,)


@app.cell
def _(mo, wages):
    years = wages.index.get_level_values("Year")
    year_range = mo.ui.range_slider(
        start=int(years.min()),
        stop=int(years.max()),
        value=[int(years.min()), int(years.max())],
        step=1,
        full_width=True,
        label="Years",
    )
    year_range
    return (year_range,)


@app.cell
def _(states_gdf, wages, year_range):
    start_year, end_year = year_range.value
    selected_years = wages.index.get_level_values("Year")
    selected = wages[(selected_years >= start_year) & (selected_years <= end_year)].copy()

    # percent change per year in each state
    selected["Wage_growth"] = selected.groupby("STUSPS")["State Minimum Wage"].pct_change()

    # aggregate wage_growth data per state across years to create a single data point
    compound_wage_growth = (
        selected["Wage_growth"].groupby("STUSPS").agg(lambda x: (x + 1).prod() - 1).round(2)
    )

    # display the max State and Federal minimum wages with the assumption that there is no decline in wage across years
    state_summary = (
        selected[["State Minimum Wage", "Federal Minimum Wage"]]
        .groupby("STUSPS")
        .max()
        .join(compound_wage_growth.rename("Wage Growth Percentage"))
    )

    # merge wage and boundary dataframes on the state postal code
    final_df = states_gdf.merge(state_summary, on="STUSPS", how="inner").dropna()
    final_df.drop(columns="geometry")
    return end_year, final_df, start_year


@app.cell
def _(end_year, final_df, folium, np, start_year):
    # set starting coordinates for when map loads
    us_lat, us_long = 37.0902, -95.7129

    # initiate folium map using base coordinates
    us_map = folium.Map([us_lat, us_long], tiles="OpenStreetMap", zoom_start=4.25)

    # quantile bins; np.unique drops repeated edges, which narrow year ranges can produce
    my_thresh = np.unique(
        final_df["Wage Growth Percentage"].quantile(
            (0, 0.005, 0.01, 0.02, 0.03, 0.4, 0.5, 0.7, 0.9, 1)
        )
    ).tolist()

    # create choropleth map using folium
    choropleth = folium.Choropleth(
        # merged geodataframe file
        geo_data=final_df,
        data=final_df,
        # key and values for bound data
        columns=("STUSPS", "Wage Growth Percentage"),
        # geojson variable to bind to
        key_on="feature.properties.STUSPS",
        # styling for map
        fill_color="YlOrBr",
        fill_opacity=0.8,
        nan_fill_color="white",
        line_opacity=0.2,
        legend_name=f"Wage Growth in the USA ({start_year}-{end_year})",
        highlight=True,
        reset=True,
        threshold_scale=my_thresh if len(my_thresh) > 1 else None,
    ).add_to(us_map)

    folium.LayerControl().add_to(us_map)

    choropleth.geojson.add_child(
        folium.features.GeoJsonTooltip(
            ["State", "State Minimum Wage", "Federal Minimum Wage", "Wage Growth Percentage"],
            labels=True,
        )
    )

    us_map
    return


if __name__ == "__main__":
    app.run()
