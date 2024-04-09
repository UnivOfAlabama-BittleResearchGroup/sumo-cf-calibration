from pathlib import Path
from typing import List, Union
import polars as pl
from functions.trajectory_loaders.trajectory import TimeStep, VelocityData


def database_loader(
    traj_file: Union[Path, pl.DataFrame],
    follower_id: Union[int, List[int]],
    leader_id: int,
    step_length: int = 0.1,
) -> pl.DataFrame:
    traj_df = (
        pl.scan_parquet(traj_file)
        .filter(
            (pl.col("vehicle_id") == follower_id[0])
            & (pl.col("lane") == follower_id[1])
            & (pl.col("lane_index") == follower_id[2])
            & (pl.col("vehicle_id_leader") == leader_id)
            & (pl.col("other_leader") == follower_id[3])
        )
        .sort("epoch_time", "front_s_smooth")
    )

    interest_df = (
        traj_df.with_columns(
            (
                (pl.col("epoch_time") - pl.col("epoch_time").first()).dt.milliseconds()
                / 1000
            ).alias("sim_time"),
            pl.col(
                [
                    "s_velocity_smooth_filtered",
                    "s_velocity_smooth_leader_filtered",
                ]
            ).clip(lower_bound=0),
        )
        .filter(((pl.col("sim_time") * 1000).cast(int) % int(step_length * 1000)) == 0)
        .with_columns(
            *(
                pl.col(f"front_s_smooth{ext}").shift_and_fill(
                    pl.col(f"front_s_smooth{ext}").first()
                    - pl.col(f"s_velocity_smooth{ext}_filtered").first() * step_length
                )
                for ext in ["", "_leader"]
            )
        )
        .collect()
    )

    # assert that there are no nulls in the follower columns
    assert interest_df["front_s_smooth"].null_count() == 0

    # fill the nulls in the leader column with

    def build_traj(ext: str = "") -> List[TimeStep]:
        return [
            TimeStep(
                time=t["sim_time"],
                velocity=t[f"s_velocity_smooth{ext}_filtered"],
                s=t[f"front_s_smooth{ext}"],
                length=t.get(f"length_s{ext}", 0.0),
                accel=t[f"s_velocity_smooth{ext}_filtered_diff"],
            )
            for t in interest_df[
                [
                    "sim_time",
                    f"front_s_smooth{ext}",
                    f"s_velocity_smooth{ext}_filtered",
                    f"length_s{ext}",
                    f"s_velocity_smooth{ext}_filtered_diff",
                ]
            ].to_dicts()
        ]

    return VelocityData(
        lead_data=build_traj("_leader"),
        follow_data=build_traj(),
        real_world=True,
    )
