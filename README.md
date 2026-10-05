# Wage Growth Aggregation Map in USA (1968-present)

<img width="777" alt="Interactive Wage Map Visualization" src="https://user-images.githubusercontent.com/85628038/201722346-4c36491d-0feb-4ae8-8a15-0f9f1cee222d.png">


Compare how much each state's minimum wage has changed over any range of years since 1968, with or without adjusting for inflation, and click states to compare their history.

## Technology Stack
* Python
* [marimo](https://marimo.io) (reactive notebook and app)
* Altair (map and charts)
* pandas, GeoPandas, NumPy

## Running the notebook
This is a [marimo](https://marimo.io) notebook. Dependencies are declared inline in `wage_map.py`, so with [uv](https://docs.astral.sh/uv/) installed you can run:

```bash
uvx marimo edit --sandbox wage_map.py
```

Use `marimo run wage_map.py` to open it as an app instead of in edit mode.

Data is downloaded when the notebook runs (and cached for the day), so there are no data files to manage:
* State and federal minimum wages and inflation (CPI-U): [FRED](https://fred.stlouisfed.org/) (`STTMINWG<state>`, `FEDMINNFRWG` and `CPIAUCSL` series, from the U.S. Department of Labor and Bureau of Labor Statistics)
* State boundaries: U.S. Census Bureau [cartographic boundary files](https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html)
