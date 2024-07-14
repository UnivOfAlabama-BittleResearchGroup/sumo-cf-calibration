from copy import deepcopy
from dataclasses import MISSING, dataclass
from pathlib import Path
from typing import Generator
from omegaconf import OmegaConf
import polars as pl

from sumo_pipelines.config import PipelineConfig


@dataclass
class TrajectoryGenerator:
    pair_file: Path
    max_queue_size: int
    trajectory_file: Path = MISSING
    db_path: Path = MISSING
    leader_id: int = MISSING
    follower_id: int = MISSING


TABLE_NAME = "trajectories"


def trajectory_pair_generator(
    config: TrajectoryGenerator,
    global_config: PipelineConfig,
    dotpath: str,
    # queue: Queue,
    *args,
    **kwargs,
) -> Generator[PipelineConfig, None, None]:
    # load the trajectory pair file
    pair_df = pl.read_parquet(config.pair_file)

    # supress the error for missing
    try:
        if OmegaConf.select(
            global_config,
            f"{dotpath}.leader_id",
        ) is not None:
            yield deepcopy(global_config)
            return
    # this bad practice, but I am lazy
    except Exception as e:
        pass
            
    # iterate over the pairs
    for i, row in enumerate(pair_df.iter_rows(named=True)):
        new_conf = deepcopy(global_config)
        OmegaConf.update(
            new_conf,
            f"{dotpath}.leader_id",
            row["vehicle_id_leader"],
        )
        OmegaConf.update(
            new_conf,
            f"{dotpath}.follower_id",
            (row["vehicle_id"], row["lane"], row["lane_index"], row["other_leader"]),
        )
        OmegaConf.update(
            new_conf,
            "Metadata.run_id",
            str(i),
        )

        yield new_conf
