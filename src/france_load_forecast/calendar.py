"""Calendar features of the daily load model."""

import datetime as dt

import holidays
import numpy as np
import pandas as pd

DAY_TYPES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday")

# National lockdowns, from the decrees of 16 March 2020, 29 October 2020 and 2 April 2021.
LOCKDOWNS = {
    "lockdown_1": (dt.date(2020, 3, 17), dt.date(2020, 5, 10)),
    "lockdown_2": (dt.date(2020, 10, 30), dt.date(2020, 12, 14)),
    "lockdown_3": (dt.date(2021, 4, 3), dt.date(2021, 5, 2)),
}


def calendar_features(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Day type, bridge days, holiday periods and lockdowns, one row per date."""
    # The following year is included to detect a bridge on 31 December.
    years = range(dates.year.min(), dates.year.max() + 2)
    public_holidays = pd.DatetimeIndex(sorted(holidays.country_holidays("FR", years=years)))
    is_holiday = dates.isin(public_holidays)
    weekday = dates.day_of_week
    # A bridge is a working day squeezed between a public holiday and the weekend.
    bridge = ~is_holiday & (
        ((weekday == 0) & (dates + pd.Timedelta(days=1)).isin(public_holidays))
        | ((weekday == 4) & (dates - pd.Timedelta(days=1)).isin(public_holidays))
    )

    features = pd.DataFrame(
        {
            "day_type": pd.Categorical(
                np.where(is_holiday, "holiday", np.asarray(DAY_TYPES)[weekday]),
                categories=DAY_TYPES,
            ),
            "bridge": bridge.astype(int),
            "christmas": ((dates.month == 12) & (dates.day >= 24)).astype(int),
            "august": (dates.month == 8).astype(int),
        },
        index=dates,
    )
    for name, (start, end) in LOCKDOWNS.items():
        features[name] = ((dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))).astype(int)
    return features
