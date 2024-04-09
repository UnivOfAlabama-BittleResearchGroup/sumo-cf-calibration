from dataclasses import dataclass, field, fields
from typing import Any
from omegaconf import OmegaConf, SCMode


@dataclass
class Config:
    leader_file: str
    run_id: str
    output_path: str
    CFmodel: str
    seed: int = 42


@dataclass
class SUMOParameters:
    step: float
    cmd_line: list
    seed: int = 42
    gui: bool = False
    route_name: str = "r_0"
    lane_name: str = "E2_0"


@dataclass
class Error:
    val: str = field(default="nrmse_s_v")
    method: str = field(default="spacing")
    include_accel: bool = field(default=False)
    mpe: float = field(default=0)
    rmsn: float = field(default=0)
    rmspe: float = field(default=0)
    rmse_s_v: float = field(default=0)
    rmse: float = field(default=0)
    nrmse_s_v: float = field(default=0)
    nrmse: float = field(default=0)

    def __setitem__(self, key, value):
        if key not in {f.name for f in fields(self)}:
            raise AttributeError(f'No field named "{key}"')
        setattr(self, key, value)

    @property
    def error(self) -> float:
        return getattr(self, self.val)

    def to_dict(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class TrajectoryProcessing:
    generate_function: str = ""
    leader_id: Any = ""
    follower_id: Any = ""


@dataclass
class Root:
    Config: Config
    CFParameters: dict
    SUMOParameters: SUMOParameters
    Error: Error
    TrajectoryProcessing: TrajectoryProcessing


def parse_config(
    file_path: str,
) -> Root:
    # actually intialize the config
    d = OmegaConf.structured(Root)
    return OmegaConf.merge(d, OmegaConf.load(file_path))


def parse_config_object(
    file_path: str,
    resolve: bool = False,
    # config_object: Root
) -> Root:
    return OmegaConf.to_container(
        parse_config(file_path=file_path),
        structured_config_mode=SCMode.INSTANTIATE,
        resolve=True,
        throw_on_missing=False,
    )
