# Methodology

## Perimeter

The load series is the national consumption published in éCO2mix (`eco2mix-national-cons-def`):
48 half-hourly values per civil day, in local time. RTE keeps 48 values on clock-change days: in
March the skipped hour is filled with repeated values, in October the repeated hour appears once.
The daily load is the mean of the day's values. Energies multiply it by the real length of the day:
23, 24 or 25 hours.

RTE's monthly series (`conso_brute_corrigee_client_direct`) covers mainland France including
Corsica, with transmission and distribution losses. Over 2014-2025 the éCO2mix series is 0.1 to
0.8 % below its gross consumption. This gap is not corrected: read the corrected gaps below
against it.

## Daily model

    load[d] = climate[d] + calendar[d] + lockdown[d] + level[d] + seasonal[d] + ar[d]

- `climate`: natural cubic spline of the smoothed national temperature published by RTE. The
  smoothing is an exponential moving average with a weight of 0.5 on the current day.
- `calendar`: day type (weekday, Saturday, Sunday, public holiday), bridge days, 24 to 31
  December, August.
- `lockdown`: one indicator per national lockdown, in 2020 and 2021.
- `level`: random walk, the structural drift of consumption.
- `seasonal`: two annual harmonics whose amplitudes drift slowly, so the shape of the year can
  change.
- `ar`: first-order autoregressive term for deviations that last a few days.

A Kalman filter estimates the coefficients and the three states jointly
(statsmodels `UnobservedComponents`), on consolidated days only. Components are declared in
[`config/model.toml`](../config/model.toml).

## Climate correction

    corrected[d] = load[d] - climate(temperature_smooth[d]) + climate(reference_smooth[d])

`reference_smooth` is RTE's reference temperature, smoothed the same way. RTE's corrected series
also leaves out 29 February, so annual corrected energies do the same.

## Forecast

The forecasting model is fitted on the last three years of consolidated days. Each forecast path replays the weather of one
complete past year, 2012 to 2025 today: on each calendar day, the reference temperature plus the
anomaly to the reference observed that day in the past year. The smoothed temperature continues
from the last observed day, the level stays at its last filtered value and the autoregressive term
fades out. Monthly energies are summed over the real length of each day.

P10 and P90 across paths only reflect weather. Model and structural errors are not in them yet.

## Backtest

`flf backtest` forecasts from the first day of each month since January 2016, with only the data
known then: the model is re-estimated at the first origin of each year on the three preceding
years, then filtered day by day.
Weather paths come from complete years outside the forecast window. Each forecast is compared with
two naive ones: the same month a year earlier, raw and climate-corrected.

Mean absolute percentage error of monthly energy, origins from January 2016 to September 2026:

| Horizon | P50 | Same month a year earlier | Same, climate-corrected |
|---|---|---|---|
| 1 month | 2.96 % | 4.41 % | 3.56 % |
| 2-3 months | 3.45 % | 4.40 % | 3.57 % |
| 4-6 months | 3.54 % | 4.41 % | 3.57 % |
| 7-12 months | 3.57 % | 4.48 % | 3.62 % |

The model beats both naive forecasts at every horizon. On origins from 2023 it is level with the
climate-corrected one four to six months ahead (2.51 % against 2.46 %) and better at other horizons.

Two choices come from this backtest. With fixed annual harmonics and all years of data, the model
only beat the climate-corrected naive forecast one month ahead, and from 2023 it underestimated
June to August by about 5 %: the response to temperature and the shape of the year changed after
the 2022 energy crisis. A drifting seasonal state and a three-year estimation window bring the
error down at every horizon and the summer bias to about 3 %.

## Results on data up to August 2026

- Winter thermosensitivity, December to February: 2.00 GW/°C.
- Annual corrected energy against RTE's corrected series, 2014-2025: 0.38 % mean absolute gap,
  1.09 % at most (2022).

`flf fit` and `flf correct` print these figures.
