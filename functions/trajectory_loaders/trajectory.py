import pandas as pd
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TimeStep:
    time: float
    velocity: float
    s: float
    length: float = 0.0
    accel: float = None


@dataclass
class VelocityData:
    lead_data: List[TimeStep]
    follow_data: List[TimeStep]
    real_world: bool = False

    # def an iterator that returns all the data in the VelocityData object
    def __iter__(self) -> Tuple[TimeStep, TimeStep]:
        return zip(self.lead_data, self.follow_data)

    def __next__(self) -> Tuple[TimeStep, TimeStep]:
        return next(self.__iter__())

    def to_df(self) -> pd.DataFrame:
        lead_df = pd.DataFrame(
            [(t.time, t.velocity, t.s, t.accel, t.length) for t in self.lead_data],
            columns=["time", "velocity_lead", "s_lead", "accel_lead", "length_lead"],
        )

        follow_df = pd.DataFrame(
            [(t.time, t.velocity, t.s, t.accel) for t in self.follow_data],
            columns=["time", "velocity_follow", "s_follow", "accel_follow"],
        )

        if self.real_world:
            lead_df["s_lead"] = lead_df["s_lead"].shift(-1)
            follow_df["s_follow"] = follow_df["s_follow"].shift(-1)
            lead_df.dropna(inplace=True)
            follow_df.dropna(inplace=True)

        return pd.merge(lead_df, follow_df, on="time", how="outer")

    @property
    def max_time(self) -> float:
        return max(
            self.lead_data[-1].time,
            self.follow_data[-1].time,
        )
