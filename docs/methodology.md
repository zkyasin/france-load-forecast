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

    load[d] = climate[d] + calendar[d] + lockdown[d] + level[d] + ar[d]

- `climate`: natural cubic spline of the smoothed national temperature published by RTE. The
  smoothing is an exponential moving average with a weight of 0.5 on the current day.
- `calendar`: day type (weekday, Saturday, Sunday, public holiday), bridge days, 24 to 31
  December, August, two annual harmonics.
- `lockdown`: one indicator per national lockdown, in 2020 and 2021.
- `level`: random walk, the structural drift of consumption.
- `ar`: first-order autoregressive term for deviations that last a few days.

A Kalman filter estimates the coefficients, the level and the autoregressive term jointly
(statsmodels `UnobservedComponents`), on consolidated days only. Components are declared in
[`config/model.toml`](../config/model.toml).

## Climate correction

    corrected[d] = load[d] - climate(temperature_smooth[d]) + climate(reference_smooth[d])

`reference_smooth` is RTE's reference temperature, smoothed the same way. RTE's corrected series
also leaves out 29 February, so annual corrected energies do the same.

## Results on data up to August 2026

- Winter thermosensitivity, December to February: 2.00 GW/°C.
- Annual corrected energy against RTE's corrected series, 2014-2025: 0.39 % mean absolute gap,
  1.10 % at most (2022).

`flf fit` and `flf correct` print these figures.
