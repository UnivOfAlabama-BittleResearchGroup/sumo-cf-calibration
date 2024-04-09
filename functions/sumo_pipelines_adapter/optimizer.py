from dataclasses import dataclass
import importlib
from pathlib import Path
import time

from omegaconf import DictConfig

# from ray.util.queue import Queue
import polars as pl
import nevergrad as ng

# from sumo_pipelines.utils.queue_helpers import unpack_queue

from functions.sumo import BasicRunner
from functions.sumo_pipelines_adapter.cf_config import CFModelParameters


def actionStepLength_constraint(x):
    return x[1]["tau"] - x[1]["actionStepLength"]


@dataclass
class CFOptimizeConfig:
    optimization_algo: str
    budget: int
    simulation_config: DictConfig
    early_stopping: bool = True
    early_stopping_tolerance: int = 20
    seed: int = 42


def optimize_single(
    config: CFOptimizeConfig,
    cf_params: CFModelParameters,
    runner: BasicRunner,
    working_dir: Path,
) -> None:
    try:
        opt_cls = ng.optimizers.registry[config.optimization_algo]
    except KeyError:
        opt_cls = getattr(
            importlib.import_module("nevergrad.optimization.optimizerlib"),
            config.optimization_algo,
        )

    parameters = CFModelParameters.to_ng_opt(cf_params)
    parameters.random_state.seed(config.seed)

    optimizer = opt_cls(
        parametrization=CFModelParameters.to_ng_opt(cf_params),
        budget=config.budget,
    )

    # create the callbacks
    if config.early_stopping:
        # callbacks.append(ng.callbacks.EarlyStopping.no_improvement_stopper(tolerance_window=10))
        optimizer.register_callback(
            "ask",
            ng.callbacks.EarlyStopping.no_improvement_stopper(
                tolerance_window=config.early_stopping_tolerance
            ),
        )

    logger = ng.callbacks.ParametersLogger(
        working_dir / "optimization_dump.json", append=False
    )
    optimizer.register_callback("tell", logger)

    if ("actionStepLength" in optimizer.parametrization.kwargs) and (
        "tau" in optimizer.parametrization.kwargs
    ):
        optimizer.parametrization.register_cheap_constraint(actionStepLength_constraint)

    # run the optimization
    recommendation = optimizer.minimize(
        runner,
    )

    return recommendation


# create a fail safely wrapper
# @fail_safely
def fail_safely(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(e)
            return {}

    return wrapper


@fail_safely
def optimize(
    config: CFOptimizeConfig,
    global_config: DictConfig,
    # queue: Queue,
    *args,
    **kwargs,
) -> None:
    # build the ouptut directory
    if not Path(f"{global_config.Metadata.cwd}").exists():
        Path(f"{global_config.Metadata.cwd}").mkdir(parents=True)

    # build the runner
    runner = BasicRunner()

    g_config = global_config
    # run the simulation
    runner.setup(
        g_config,
        # config.simulation_config,
    )

    t0 = time.time()
    # optimize the model
    recommendation = optimize_single(
        config,
        cf_params=g_config.Blocks.CFModelParameters,
        runner=runner,
        working_dir=Path(f"{global_config.Metadata.cwd}"),
    )
    t1 = time.time()

    # simulated with the best model (cause not sure if last value in model is the best)
    runner(
        **recommendation[1].value,
    )

    # calculate the error across all metrics
    all_errors = runner.get_all_error()
    runner.save_best_trajectory()

    return {
        **recommendation[1].value,
        **all_errors,
        **{
            "leader_id": g_config.Blocks.TrajectoryGenerator.leader_id,
            "follower_id": g_config.Blocks.TrajectoryGenerator.follower_id[0],
        },
        # car following model
        "cf_model": g_config.Blocks.CFModelParameters.model,
        "run_id": g_config.Metadata.run_id,
        "collision": recommendation.loss > 1e3,
        "opt_time": t1 - t0,
    }


@fail_safely
def dummy_optimize(
    config: CFOptimizeConfig,
    global_config: DictConfig,
    # queue: Queue,
    *args,
    **kwargs,
) -> None:
    # build the ouptut directory
    if not Path(f"{global_config.Metadata.cwd}").exists():
        Path(f"{global_config.Metadata.cwd}").mkdir(parents=True)

    # build the runner
    runner = BasicRunner()

    g_config = global_config
    # run the simulation
    runner.setup(
        g_config,
        # config.simulation_config,
    )

    # optimize the model
    res = runner(**CFModelParameters.to_flat_dict(g_config.Blocks.CFModelParameters))

    runner.save_best_trajectory()
    all_errors = runner.get_all_error()

    return {
        **CFModelParameters.to_flat_dict(g_config.Blocks.CFModelParameters),
        **all_errors,
        **{
            "leader_id": g_config.Blocks.TrajectoryGenerator.leader_id,
            "follower_id": g_config.Blocks.TrajectoryGenerator.follower_id[0],
        },
        # car following model
        "cf_model": g_config.Blocks.CFModelParameters.model,
        "run_id": g_config.Metadata.run_id,
        "collision": res > 1e3,
    }


def dump_results(
    func_config,
    global_config,
    results,
):
    if len(results) == 0:
        return

    if not Path(f"{global_config.Metadata.output}").exists():
        Path(f"{global_config.Metadata.output}").mkdir(parents=True)

    # print(len(my_results)

    # print(my_results)
    pl.DataFrame([r for r in results if r is not None]).write_parquet(
        f"{global_config.Metadata.output}/results.parquet"
    )
