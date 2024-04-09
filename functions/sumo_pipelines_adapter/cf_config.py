from dataclasses import dataclass, field
from typing import Any

from omegaconf import DictConfig, ListConfig
import nevergrad as ng


@dataclass
class CFModelParam:
    val: float
    search_space: str = ""
    args: ListConfig[Any] = field(default_factory=list)

    @staticmethod
    def to_ng_opt(
        cls: "CFModelParam",
    ):
        if cls.search_space == "uniform":
            return ng.p.Scalar(lower=cls.args[0], upper=cls.args[1])
        elif cls.search_space == "choice":
            return ng.p.Choice(choices=cls.args)
        else:
            raise ValueError(f"Invalid search space {cls.search_space}")


@dataclass
class CFModelParameters:
    model: str
    parameters: DictConfig[str, CFModelParam]

    @staticmethod
    def to_flat_dict(cls: "CFModelParameters"):
        return {"model": cls.model, **{k: v.val for k, v in cls.parameters.items()}}

    @staticmethod
    def to_ng_opt(
        cls: "CFModelParameters",
    ):
        return ng.p.Instrumentation(
            **{k: CFModelParam.to_ng_opt(v) for k, v in cls.parameters.items()}
        )

    @classmethod
    def from_flat_dict(cls, d: dict):
        return cls(
            model=d.pop("model"),
            parameters={k: CFModelParam(val=v) for k, v in d.items()},
        )

    def write_additional_file(self, f) -> None:
        param_string = " ".join(
            [f'{k}="{v.val}"' for k, v in self.parameters.items() if v.val is not None]
        )
        # with open(path, "w") as f:
        f.write(
            f"""
            <additional>
                \t\t<vType id="{self.vehType}" carFollowModel="{self.model}" {param_string}/>
            </additional>
            """
        )

    @property
    def vehType(self):
        return f"{self.model.upper()}_car"
