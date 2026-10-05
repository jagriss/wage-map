# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "altair>=5.4",
#     "geopandas>=1.0",
#     "marimo>=0.25",
#     "numpy>=1.26",
#     "pandas>=2.2",
# ]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium", app_title="Minimum Wage Map")


@app.cell
def _():
    import io
    import re
    import time
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import urlopen

    import altair as alt
    import geopandas as gpd
    import marimo as mo
    import numpy as np
    import pandas as pd

    return (
        HTTPError,
        ThreadPoolExecutor,
        URLError,
        alt,
        date,
        gpd,
        io,
        mo,
        np,
        pd,
        re,
        time,
        urlencode,
        urlopen,
    )


@app.cell
def _(mo):
    mo.md("""
    # How far has the minimum wage really risen?

    Every state's minimum wage has gone up since 1968, but prices have gone up too.
    Pick a range of years to see how much each state's minimum wage changed, with or
    without adjusting for inflation. Click states on the map to compare their history.
    """)
    return


@app.cell
def _(mo):
    # chart colors from a validated palette; dark mode gets its own steps, not an inversion
    is_dark = mo.app_meta().theme == "dark"
    colors = {
        "ink": "#ffffff" if is_dark else "#0b0b0b",
        "ink_secondary": "#c3c2b7" if is_dark else "#52514e",
        "muted": "#898781",
        "grid": "#2c2c2a" if is_dark else "#e1e0d9",
        "surface": "#1a1a19" if is_dark else "#fcfcfb",
        # diverging: red = lost ground, gray = no change, blue = gained
        "decrease": "#e66767" if is_dark else "#e34948",
        "midpoint": "#383835" if is_dark else "#f0efec",
        "increase": "#3987e5" if is_dark else "#2a78d6",
        # sequential blue ramp, light to dark
        "sequential": ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
        # categorical slots in fixed order, for compared states
        "series": (
            ["#3987e5", "#d95926", "#199e70", "#c98500"]
            if is_dark
            else ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
        ),
    }

    def style_chart(chart):
        """Apply shared fonts, recessive axes, and a transparent background."""
        font = "system-ui, -apple-system, 'Segoe UI', sans-serif"
        return (
            chart.configure(background="transparent", font=font)
            .configure_view(stroke=None)
            .configure_axis(
                labelColor=colors["muted"],
                titleColor=colors["ink_secondary"],
                gridColor=colors["grid"],
                domainColor=colors["grid"],
                tickColor=colors["grid"],
                labelFontSize=12,
                titleFontSize=12,
                titleFontWeight="normal",
            )
            .configure_legend(
                labelColor=colors["ink_secondary"],
                titleColor=colors["ink_secondary"],
                titleFontWeight="normal",
                labelFontSize=12,
            )
        )

    return colors, style_chart


@app.cell
def _(HTTPError, URLError, time, urlopen):
    def download(url, attempts=3, timeout=30):
        """Return the body of a URL, retrying timeouts and server errors with a short backoff."""
        for attempt in range(attempts):
            try:
                with urlopen(url, timeout=timeout) as response:
                    return response.read()
            except HTTPError as e:
                # 4xx errors won't succeed on retry
                if e.code < 500 or attempt == attempts - 1:
                    raise
            except (URLError, TimeoutError):
                if attempt == attempts - 1:
                    raise
            time.sleep(2**attempt)

    return (download,)


@app.cell
def _(download, gpd, io, mo):
    CENSUS_YEAR = 2025
    states_url = (
        f"https://www2.census.gov/geo/tiger/GENZ{CENSUS_YEAR}/shp/"
        f"cb_{CENSUS_YEAR}_us_state_20m.zip"
    )

    with mo.persistent_cache("census_states"):
        states_gdf = gpd.read_file(io.BytesIO(download(states_url)))

    # keep the 50 states + DC (territories have FIPS codes of 60 and up)
    states_gdf = states_gdf[states_gdf["STATEFP"] < "60"]
    states_gdf = states_gdf[["STUSPS", "NAME", "geometry"]].rename(
        columns={"NAME": "state"}
    )
    return (states_gdf,)


@app.cell
def _(
    HTTPError,
    ThreadPoolExecutor,
    date,
    download,
    io,
    mo,
    np,
    pd,
    re,
    states_gdf,
    urlencode,
):
    FIRST_YEAR = 1968

    def fetch_fred(series_id, end):
        """Return a FRED series indexed by date, or None if FRED has no such series."""
        # series ids are built from downloaded state codes, so check them before use
        if not re.fullmatch(r"[A-Z0-9]+", series_id):
            raise ValueError(f"Unexpected FRED series id: {series_id!r}")
        query = urlencode({"id": series_id, "coed": end})
        try:
            body = download(f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}")
        except HTTPError as e:
            # states with no minimum wage law (e.g. AL, MS) have no series
            if e.code == 404:
                return None
            raise
        series = pd.read_csv(io.BytesIO(body), index_col=0, parse_dates=True).iloc[:, 0]
        # FRED marks missing observations with "."; drop them so gaps fill from earlier values
        series = pd.to_numeric(series, errors="coerce").dropna()
        return series if len(series) else None

    @mo.persistent_cache
    def fetch_all_series(state_codes, end):
        """Fetch federal minimum wage, CPI, and one minimum wage series per state."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            series = pool.map(
                lambda code: fetch_fred(f"STTMINWG{code}", end), state_codes
            )
            return (
                fetch_fred("FEDMINNFRWG", end),
                fetch_fred("CPIAUCSL", end),
                dict(zip(state_codes, series, strict=True)),
            )

    # the end date is part of the cache key, so the data refreshes once a day
    federal, cpi, state_series = fetch_all_series(
        tuple(sorted(states_gdf["STUSPS"])), date.today().isoformat()
    )
    if federal is None or cpi is None:
        raise RuntimeError("FRED returned no data for the federal minimum wage or CPI")

    # state series are annual (Jan 1). Stop at the latest year most states have, so one
    # early-updated state doesn't leave the rest falling back to the federal rate.
    last_year = int(
        pd.Series(
            [s.index.max().year for s in state_series.values() if s is not None]
        ).median()
    )
    year_starts = pd.date_range(f"{FIRST_YEAR}-01-01", f"{last_year}-01-01", freq="YS")

    # federal wage and CPI change mid-year; take the values in effect on Jan 1 of each year
    federal_annual = pd.Series(
        federal.reindex(year_starts, method="ffill").to_numpy(), index=year_starts.year
    )
    cpi_annual = pd.Series(
        cpi.reindex(year_starts, method="ffill").to_numpy(), index=year_starts.year
    )

    # one row per year, one column per state, holding the wage employers must pay:
    # the higher of the state and federal minimums (fmax treats a missing state wage as federal)
    wages = pd.DataFrame(
        {
            code: np.fmax(
                series.reindex(year_starts).to_numpy()
                if series is not None
                else np.nan,
                federal_annual.to_numpy(),
            )
            for code, series in state_series.items()
        },
        index=year_starts.year,
    )
    wages.columns.name = "STUSPS"
    return cpi_annual, federal_annual, wages


@app.cell
def _(mo, wages):
    year_range = mo.ui.range_slider(
        start=int(wages.index.min()),
        stop=int(wages.index.max()),
        value=[int(wages.index.min()), int(wages.index.max())],
        step=1,
        # recompute when the handle is released, not on every tick of a drag
        debounce=True,
        full_width=True,
    )
    dollars = mo.ui.radio(
        options=["Adjusted for inflation", "Dollars as paid"],
        value="Adjusted for inflation",
        inline=True,
    )
    return dollars, year_range


@app.cell
def _(dollars, mo, year_range):
    # shown here rather than with show_value, which formats years as "1,968"
    mo.hstack(
        [
            mo.vstack(
                [
                    mo.md(f"**Years:** {year_range.value[0]} to {year_range.value[1]}"),
                    year_range,
                ],
                gap=0.25,
            ),
            dollars,
        ],
        widths=[3, 2],
        gap=2,
        align="end",
        wrap=True,
    )
    return


@app.cell
def _(cpi_annual, dollars, federal_annual, mo, pd, states_gdf, wages, year_range):
    start_year, end_year = year_range.value
    mo.stop(
        start_year == end_year,
        mo.callout(
            mo.md("Pick a range of at least two years to see a change."), kind="info"
        ),
    )

    adjusted = dollars.value == "Adjusted for inflation"
    # multiplier that converts each year's dollars into end-year dollars
    to_end_dollars = (
        cpi_annual[end_year] / cpi_annual
        if adjusted
        else pd.Series(1.0, index=cpi_annual.index)
    )

    start_wage = wages.loc[start_year] * to_end_dollars[start_year]
    end_wage = wages.loc[end_year]
    summary = pd.DataFrame(
        {
            "start_wage": start_wage.round(2),
            "end_wage": end_wage,
            "change": end_wage / start_wage - 1,
        }
    )
    summary = states_gdf.merge(summary, left_on="STUSPS", right_index=True)

    federal_start = federal_annual[start_year] * to_end_dollars[start_year]
    federal_end = federal_annual[end_year]
    start_label = f"{start_year} wage" + (f" (in {end_year} $)" if adjusted else "")
    return (
        adjusted,
        end_year,
        federal_end,
        federal_start,
        start_label,
        start_year,
        summary,
        to_end_dollars,
    )


@app.cell
def _(adjusted, end_year, federal_end, federal_start, mo, start_year, summary):
    _top = summary.loc[summary["end_wage"].idxmax()]
    _above = int((summary["end_wage"] > federal_end).sum())
    _lost = int((summary["change"] < 0).sum())
    _median = summary["change"].median()
    _basis = "after inflation" if adjusted else "in dollars as paid"

    mo.hstack(
        [
            mo.stat(
                value=f"${federal_end:.2f}",
                label=f"Federal minimum, {end_year}",
                caption=f"{federal_end / federal_start - 1:+.0%} since {start_year} {_basis}",
                direction="increase" if federal_end >= federal_start else "decrease",
                bordered=True,
            ),
            mo.stat(
                value=f"{len(summary) - _above} of {len(summary)}",
                label="At the federal minimum",
                caption=f"in {end_year}, including DC",
                bordered=True,
            ),
            mo.stat(
                value=f"${_top['end_wage']:.2f}",
                label=f"Highest minimum, {end_year}",
                caption=_top["state"],
                bordered=True,
            ),
            mo.stat(
                value=f"{_median:+.0%}",
                label="Typical state's change",
                caption=(
                    f"{_lost} states lost ground {_basis}"
                    if _lost
                    else f"median across states, {_basis}"
                ),
                direction="increase" if _median >= 0 else "decrease",
                bordered=True,
            ),
        ],
        gap=1,
        wrap=True,
        justify="start",
    )
    return


@app.cell
def _(
    adjusted, alt, colors, end_year, mo, start_label, start_year, style_chart, summary
):
    if adjusted:
        # diverging scale centered on zero, symmetric so equal gains and losses look equal
        # floor keeps the scale valid if no state changed at all
        _reach = max(float(summary["change"].abs().max()), 0.01)
        _scale = alt.Scale(
            domain=[-_reach, 0, _reach],
            range=[colors["decrease"], colors["midpoint"], colors["increase"]],
            interpolate="lab",
        )
    else:
        _scale = alt.Scale(range=colors["sequential"], interpolate="lab")

    _picked = alt.selection_point(name="states", fields=["STUSPS"], toggle="true")

    _map = (
        alt.Chart(
            summary,
            title=alt.TitleParams(
                f"Change in minimum wage, {start_year} to {end_year}",
                subtitle="Adjusted for inflation" if adjusted else "In dollars as paid",
                anchor="start",
                color=colors["ink"],
                subtitleColor=colors["ink_secondary"],
                fontSize=15,
                fontWeight=600,
            ),
        )
        .mark_geoshape(cursor="pointer")
        .encode(
            color=alt.Color(
                "change:Q",
                scale=_scale,
                legend=alt.Legend(
                    title=None,
                    format="+.0%",
                    orient="top",
                    direction="horizontal",
                    gradientLength=280,
                    gradientThickness=10,
                ),
            ),
            # others fade only while something is picked; picked states get an ink outline
            opacity=alt.when(_picked).then(alt.value(1)).otherwise(alt.value(0.35)),
            stroke=alt.when(_picked, empty=False)
            .then(alt.value(colors["ink"]))
            .otherwise(alt.value(colors["surface"])),
            strokeWidth=alt.when(_picked, empty=False)
            .then(alt.value(1.5))
            .otherwise(alt.value(0.5)),
            tooltip=[
                alt.Tooltip("state:N", title="State"),
                alt.Tooltip("change:Q", title="Change", format="+.0%"),
                alt.Tooltip("start_wage:Q", title=start_label, format="$.2f"),
                alt.Tooltip("end_wage:Q", title=f"{end_year} wage", format="$.2f"),
            ],
        )
        .project("albersUsa")
        .properties(width="container", height=360)
        .add_params(_picked)
    )

    state_map = mo.ui.altair_chart(style_chart(_map), legend_selection=False)
    return (state_map,)


@app.cell
def _(end_year, mo, pd, start_label, state_map, summary):
    _table = (
        pd.DataFrame(summary.drop(columns="geometry"))
        .sort_values("change", ascending=False)
        .reset_index(drop=True)
        .rename(
            columns={
                "state": "State",
                "STUSPS": "Code",
                "start_wage": start_label,
                "end_wage": f"{end_year} wage",
                "change": "Change",
            }
        )
    )
    mo.ui.tabs(
        {
            "Map": state_map,
            "Table": mo.ui.table(
                _table,
                format_mapping={
                    start_label: "${:.2f}".format,
                    f"{end_year} wage": "${:.2f}".format,
                    "Change": "{:+.0%}".format,
                },
                selection=None,
                pagination=False,
                show_column_summaries=False,
                show_data_types=False,
            ),
        }
    )
    return


@app.cell
def _(mo):
    # remembers the order states were picked, so each keeps its color as others are added
    get_pick_order, set_pick_order = mo.state([])
    return get_pick_order, set_pick_order


@app.cell
def _(
    adjusted,
    alt,
    colors,
    end_year,
    federal_annual,
    get_pick_order,
    mo,
    pd,
    set_pick_order,
    start_year,
    state_map,
    style_chart,
    summary,
    to_end_dollars,
    wages,
):
    _MAX_STATES = 4
    _selected = set(state_map.value["STUSPS"]) if len(state_map.value) else set()
    # keep earlier picks in place and append new ones, so colors don't shuffle
    _kept = [c for c in get_pick_order() if c in _selected]
    _picked = _kept + sorted(_selected - set(_kept))
    set_pick_order(_picked)
    if _picked:
        _codes = _picked[:_MAX_STATES]
        _hint = (
            f"Showing the first {_MAX_STATES} states you picked. Click a state again to remove it."
            if len(_picked) > _MAX_STATES
            else "Click a state again to remove it."
        )
    else:
        # nothing picked yet: show the state with the largest change
        _codes = [summary.loc[summary["change"].idxmax(), "STUSPS"]]
        _hint = "Showing the state with the largest change. Click states on the map to compare up to four."

    _names = summary.set_index("STUSPS")["state"]
    _years = wages.loc[start_year:end_year].index
    _history = pd.DataFrame(
        {_names[c]: wages.loc[_years, c] * to_end_dollars[_years] for c in _codes}
        | {"Federal minimum": federal_annual[_years] * to_end_dollars[_years]},
        index=_years,
    ).round(2)
    _history.index.name = "year"
    _long = _history.reset_index().melt("year", var_name="series", value_name="wage")

    _series = [_names[c] for c in _codes] + ["Federal minimum"]
    _color = alt.Color(
        "series:N",
        scale=alt.Scale(
            domain=_series, range=colors["series"][: len(_codes)] + [colors["muted"]]
        ),
        legend=alt.Legend(
            title=None, orient="top", symbolType="stroke", symbolStrokeWidth=2
        ),
    )
    _y_title = (
        f"Minimum wage ({end_year} dollars)"
        if adjusted
        else "Minimum wage (dollars as paid)"
    )
    _x = alt.X(
        "year:Q",
        title=None,
        scale=alt.Scale(domain=[start_year, end_year], nice=False),
        axis=alt.Axis(format="d", grid=False),
    )

    # crosshair: snap to the nearest year and list every series there
    _nearest = alt.selection_point(
        nearest=True, on="pointermove", fields=["year"], empty=False
    )
    _lines = (
        alt.Chart(_long)
        .mark_line(strokeWidth=2, interpolate="step-after")
        .encode(
            x=_x,
            y=alt.Y("wage:Q", title=_y_title, axis=alt.Axis(format="$.0f")),
            color=_color,
            strokeDash=alt.condition(
                alt.datum.series == "Federal minimum",
                alt.value([4, 3]),
                alt.value([1, 0]),
            ),
        )
    )
    # draw the dashed federal line in its own top layer so it stays visible where a state matches it
    _is_federal = alt.datum.series == "Federal minimum"
    _state_lines = _lines.transform_filter(~_is_federal)
    _federal_line = _lines.transform_filter(_is_federal)
    _rule = (
        alt.Chart(_history.reset_index())
        .mark_rule(color=colors["muted"], strokeWidth=1)
        .encode(
            x="year:Q",
            opacity=alt.condition(_nearest, alt.value(0.8), alt.value(0)),
            tooltip=[alt.Tooltip("year:Q", title="Year", format="d")]
            + [alt.Tooltip(f"{s}:Q", title=s, format="$.2f") for s in _series],
        )
        .add_params(_nearest)
    )
    _dots = _lines.mark_point(filled=True, size=60).encode(
        opacity=alt.condition(_nearest, alt.value(1), alt.value(0))
    )
    _chart = alt.layer(_state_lines, _federal_line, _dots, _rule).properties(
        width="container",
        height=300,
        title=alt.TitleParams(
            "Minimum wage over time",
            anchor="start",
            color=colors["ink"],
            fontSize=15,
            fontWeight=600,
        ),
    )

    mo.vstack([style_chart(_chart), mo.md(f"<small>{_hint}</small>")])
    return


@app.cell
def _(mo):
    mo.accordion(
        {
            "How it works": mo.md("""
    - **Which wage counts.** For each state and year, the notebook uses the wage employers
      must pay: the state minimum or the federal minimum, whichever is higher. States with
      no minimum wage law of their own (such as Alabama and Mississippi), or whose law is
      below the federal rate (such as Wyoming and Georgia), count at the federal rate.
    - **Which date.** Each year uses the rate in effect on January 1. Changes that take
      effect later in a year show up the following year. For example, the federal minimum
      rose from $1.40 to $1.60 in February 1968, so 1968 counts as $1.40.
    - **Change.** The wage in the last year of your range divided by the wage in the first
      year, minus one.
    - **Inflation.** With *Adjusted for inflation* selected, the earlier wage is converted
      to last-year dollars using the Consumer Price Index (CPI-U, January of each year).
      A negative change means the minimum wage buys less than it did.
    """),
            "Sources": mo.md("""
    - **Minimum wages:** [FRED](https://fred.stlouisfed.org/), Federal Reserve Bank of
      St. Louis, from U.S. Department of Labor data. State series `STTMINWG` plus the
      state's postal code (e.g. `STTMINWGCA`); federal series `FEDMINNFRWG`.
    - **Inflation:** [Consumer Price Index for All Urban Consumers](https://fred.stlouisfed.org/series/CPIAUCSL)
      (`CPIAUCSL`), U.S. Bureau of Labor Statistics, via FRED.
    - **State boundaries:** U.S. Census Bureau
      [cartographic boundary files](https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html),
      2025, 1:20 million scale.

    Data is downloaded when the notebook runs and cached for the rest of the day.
    """),
            "Limitations": mo.md("""
    - **Local minimum wages aren't included.** Many cities and counties set higher rates
      than their state.
    - **One rate per state.** Some states set different rates by region or employer size;
      FRED reports a single figure per state, which may not match every worker's rate.
    - **Tipped and youth wages,** exemptions, and other special rates aren't included.
    - **One national price index.** Prices rise at different speeds in different states,
      so the inflation adjustment is an approximation.
    """),
        }
    )
    return


if __name__ == "__main__":
    app.run()
