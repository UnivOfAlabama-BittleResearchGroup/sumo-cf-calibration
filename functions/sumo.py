import contextlib
import os
import uuid

from sumo_pipelines.blocks.simulation.functions import make_cmd
from sumo_pipelines.utils.config_helpers import load_function

from functions.config import Root, Error
from functions.error_metrics import error_metrics, fast_error
from functions.trajectory_loaders.read_trajectories import TimeStep, VelocityData
from functions.sumo_pipelines_adapter.cf_config import CFModelParameters

from copy import deepcopy
from pathlib import Path

import traci.constants as tc
from typing import TYPE_CHECKING, Any


# check if windows
import platform

try:
    if platform.system() != "Windows":
        import libsumo as traci

        LIBSUMO = True
    else:
        raise ImportError
except ImportError:
    import traci

    LIBSUMO = False


if TYPE_CHECKING:
    import traci as traci_conn

wand_b_ok = False


class BasicRunner:
    def __init__(self) -> None:
        self._config: Root = None
        self._traci: traci_conn.connection = None

        self._step_counter = 0
        self._initialized = False

        self._cf_params: CFModelParameters = None

    def _gen_traci_conn(self):
        # generate a random hash for the traci connection
        return str(uuid.uuid4())
        # return f"{uuidrandom.randint(0, 1000)}"

    def setup(self, run_config: Root = None):
        self._config = deepcopy(run_config)
        self._trajectories: VelocityData = load_function(
            self._config.Blocks.TrajectoryProcessing.generate_function
        )(**self._config.Blocks.TrajectoryProcessing.kwargs)

        self._cf_params = run_config.Blocks.CFModelParameters

        if self._initialized is False:
            self._init_sumo()

        if self._sim_time > 1e6:
            self._sim_time = 0
            self.cleanup_sim()

        if self._traci is None:
            print("Starting SUMO")
            self._start_sumo()

    def _init_sumo(
        self,
    ) -> None:
        self._traci_conn = self._gen_traci_conn()
        self._sim_time = 0
        self._sim_step = int(self._config.Blocks.SimulationConfig.step_length * 1000)
        self._initialized = True

    def _start_sumo(self):
        if LIBSUMO:
            traci.start(
                make_cmd(self._config.Blocks.SimulationConfig),
            )
            self._traci = traci
        else:
            traci.start(
                make_cmd(self._config.Blocks.SimulationConfig),
                label=self._traci_conn,
            )
            self._traci = traci.getConnection(self._traci_conn)
            print(f"Starting SUMO with connection number {self._traci_conn}")

    def add_vehicle(self, traj_data: TimeStep, name: str, follower: bool = False):
        self._traci.vehicle.add(
            name,
            self._config.Blocks.SimulationConfig.route_name,
            departSpeed=str(traj_data.velocity),
            departPos=0,  # cause I'm gonna move it to the correct position down below
        )

        if follower:
            self._traci.vehicle.setType(name, self._cf_params.vehType)
        else:
            self._traci.vehicle.setLength(name, traj_data.length)
            self._traci.vehicle.setSpeedMode(name, 32)

        # force the vehicle in the position with vehicle moveTo
        self._traci.vehicle.moveTo(
            name,
            self._config.Blocks.SimulationConfig.target_lane,
            traj_data.s,
            reason=tc.MOVE_AUTOMATIC,
        )
        self._traci.vehicle.subscribe(
            name, (tc.VAR_SPEED, tc.VAR_LANEPOSITION, tc.VAR_ACCELERATION)
        )

    def __call__(self, **param_dict) -> Any:
        # this is for NgOpt
        param_dict["model"] = self._cf_params.model
        self._cf_params = CFModelParameters.from_flat_dict(param_dict)
        param_dict.update({"model": self._cf_params.model})

        with open(Path(self._config.Metadata.cwd) / "cf_params.add.xml", "w") as f:
            self._cf_params.write_additional_file(f)

        self._config.Blocks.SimulationConfig.additional_files = [f.name]

        self._start_sumo()

        res = self.float_step()

        self.cleanup()

        return res

    def run(self) -> VelocityData:
        leader_name = f"leader_{int(self._sim_time)}"
        follower_name = f"follower_{int(self._sim_time)}"

        self.add_vehicle(self._trajectories.lead_data[0], leader_name, follower=False)
        # add the follower
        self.add_vehicle(
            self._trajectories.follow_data[0], follower_name, follower=True
        )

        # reset the sim time
        self._sim_time = int(self._traci.simulation.getTime() * 1000)
        start_time = self._sim_time

        sim_trajs = VelocityData(
            [],
            [],
        )
        # step the sim once top get the vehicles on the lane
        # self._traci.simulationStep()
        # self._sim_time += self._sim_step

        lane = self._traci.vehicle.getLaneID(leader_name)
        removed = False
        collision = False
        leader_nulled = False

        leader_traj = deepcopy(self._trajectories.lead_data)
        max_time = int(self._trajectories.max_time * 1000)

        while (self._sim_time - start_time) < max_time:
            done = len(leader_traj) == 0

            if done and not removed:
                self._traci.vehicle.unsubscribe(leader_name)
                self._traci.vehicle.remove(leader_name)
                removed = True

            elif not removed and (
                ((self._sim_time - start_time) - self._sim_step)
                <= int(leader_traj[0].time * 1000)
                < ((self._sim_time - start_time) + self._sim_step)
            ):
                leader = leader_traj.pop(0)

                if leader.velocity is None:
                    # remove the leader
                    self._traci.vehicle.remove(leader_name)
                    self._traci.vehicle.unsubscribe(leader_name)
                    leader_nulled = True
                else:
                    if leader_nulled:
                        self.add_vehicle(leader, leader_name, follower=False)
                        leader_nulled = False
                    try:
                        self._traci.vehicle.setSpeed(leader_name, leader.velocity)
                        self._traci.vehicle.setPreviousSpeed(
                            leader_name, leader.velocity
                        )
                        self._traci.vehicle.moveTo(leader_name, lane, leader.s)
                    except traci.exceptions.TraCIException:
                        print(f"Leader: {leader_name} not found")
                        print(f"Sim time: {self._sim_time}")
                        print(f"Leader position: {leader.s}")
                        if not done:
                            collision = True
                            break

            self._traci.simulationStep()
            self._sim_time += self._sim_step

            # get subscription results
            positions = self._traci.vehicle.getAllSubscriptionResults()

            # print(f"Sim time: {self._sim_time}")
            # print(positions)

            # add the data to the VelocityData object
            if leader_name in positions:
                sim_trajs.lead_data.append(
                    TimeStep(
                        time=(self._sim_time - start_time) / 1000,
                        velocity=positions[leader_name][tc.VAR_SPEED],
                        s=positions[leader_name][tc.VAR_LANEPOSITION],
                        accel=positions[leader_name][tc.VAR_ACCELERATION],
                    )
                )
            with contextlib.suppress(KeyError):
                sim_trajs.follow_data.append(
                    TimeStep(
                        time=(self._sim_time - start_time) / 1000,
                        velocity=positions[follower_name][tc.VAR_SPEED],
                        s=positions[follower_name][tc.VAR_LANEPOSITION],
                        accel=positions[follower_name][tc.VAR_ACCELERATION],
                    )
                )

            # check if there was a collision
            if self._traci.simulation.getCollisions():
                print(f"Collision at time {self._sim_time}")
                collision = True
                break

            # if the leader is ever behind the follower, break the loop
            if (
                (sim_trajs.lead_data[-1].s < sim_trajs.follow_data[-1].s)
                and not done
                and not removed
                and not leader_nulled
            ):
                print(f"Leader behind follower at time {self._sim_time}")
                collision = True
                break

        return sim_trajs, collision

    def cleanup_sim(self):
        self._traci.close()
        self._traci = None
        self._sim_time = 0
        # remove the temp file
        os.remove(Path(self._config.Metadata.cwd) / "cf_params.add.xml")

    def cleanup(self):
        self.cleanup_sim()

    def float_step(
        self,
    ) -> float:
        sim_data, collision = self.run()
        self._sim_data = sim_data
        if not collision:
            return fast_error(
                rw_df=self._trajectories.to_df(),
                sim_df=sim_data.to_df(),
                conf=self._config.Blocks.Error,
            )
        else:
            return 1e6

    def get_all_error(
        self,
    ) -> Error:
        error_metrics(
            rw_df=self._trajectories.to_df(),
            sim_df=self._sim_data.to_df(),
            conf=self._config.Blocks.Error,
        )

        return self._config.Blocks.Error

    def save_best_trajectory(
        self,
    ) -> None:
        from functions.error_metrics import _join_n_add_spacing

        (
            _join_n_add_spacing(
                self._trajectories.to_df(),
                self._sim_data.to_df(),
            )
            .assign(
                leader_id=self._config.Blocks.TrajectoryGenerator.leader_id,
                follower_id=self._config.Blocks.TrajectoryGenerator.follower_id[0],
            )
            .to_parquet(Path(self._config.Metadata.cwd) / "best_trajectory.parquet")
        )
