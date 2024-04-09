import polars as pl
import numpy as np

def calc_accel(
    df: pl.DataFrame,
    col: str,
    time_col: str,
    vehicle_col: str,
    threading: bool = False,
) -> pl.DataFrame:
    return df.with_columns(
        pl.struct([f"{col}", time_col])
        .apply(
            lambda x: pl.Series(
                name=f"{col}_accel",
                values=np.gradient(
                    x.struct[col],
                    x.struct[time_col],
                ),
                dtype=pl.Float64,
            ),
            strategy="threading" if threading else "thread_local",
            # return_dtype=pl.Float64,
        )
        .over(vehicle_col)
        .alias(f"{col}_accel")
        .fill_null(0)
    )


def calc_headway(
    df: pl.DataFrame,
    leader_pos_col: str,
    follower_pos_col: str,
    follower_velocity_col: str,
    headway_col: str,
) -> pl.DataFrame:
    # create
    return df.with_columns(
        (
            (pl.col(leader_pos_col) - pl.col(follower_pos_col))
            / pl.col(follower_velocity_col)
        ).alias(headway_col)
    )


def build_stacked_df(
    df: pl.DataFrame,
    rw_value_col: str,
    sim_value_col: str,
) -> pl.DataFrame:
    return (
        df.filter(
            pl.col(sim_value_col).is_not_nan() & pl.col(rw_value_col).is_not_nan()
        )
        .select([sim_value_col, "model_pretty", "run_id"])
        .melt(
            id_vars=["model_pretty", "run_id"],
            value_vars=[
                sim_value_col,
                # "run_id"
            ],
        )
        .vstack(
            # this serves as our baseline. all the models are the same
            df.filter(pl.col("model_pretty") == "IDM - Default")
            .filter(
                pl.col(rw_value_col).is_not_nan()
            )
            .select(
                [rw_value_col, pl.lit("Real World").alias("model_pretty"), "run_id"]
            )
            .melt(
                # id_vars=['model', 'calibrated'],
                id_vars=["model_pretty", "run_id"],
                value_vars=[
                    rw_value_col,
                ],
            )
        )
        .with_columns(
            pl.col("model_pretty").str.contains("Calibrated").alias("calibrated"),
            pl.col("model_pretty").str.split(" ").list.get(0).alias("model"),
        )
    )


def calc_spacing(
    df: pl.DataFrame,
    leader_pos_col: str,
    leader_length_col: str,
    follower_pos_col: str,
    spacing_col: str,
) -> pl.DataFrame:
    return df.with_columns(
        (
            pl.col(leader_pos_col)
            - pl.col(leader_length_col)
            - pl.col(follower_pos_col)
        ).alias(spacing_col)
    )


# taken directly from SUMO

GRAVITY_CONST = 9.81
AIR_DENSITY_CONST = 1.182
NORMALIZING_SPEED = 19.444
NORMALIZING_ACCELARATION = 0.45
SPEED_DCEL_MIN = 10 / 3.6
ZERO_SPEED_ACCURACY = 0.5
DRIVE_TRAIN_EFFICIENCY_All = 0.9
DRIVE_TRAIN_EFFICIENCY_CB = 0.8


RollingResData = {"Fr0": 0.0095104, "Fr1": 7.08e-05, "Fr2": 0.0, "Fr3": 0.0, "Fr4": 0.0}
VehicleData = {
    "MassType": "LV",
    "FuelType": "G",
    "CalcType": "Conv",
    "Mass": 1193.7,
    "Loading": 179.7,
    "RedMassWheel": 38.8,
    "WheelDiameter": 0.6064,
    "Cw": 0.3745,
    "A": 2.12,
}

RotMassF = [
    2.1106531442153624,
    2.1106531442153624,
    1.3550542766263412,
    1.1605588206788657,
    1.0925309339359672,
    1.0598062620163269,
    1.0598062620163269,
]


speedF = [
    0.0,
    11.161903925181518,
    29.412189004603665,
    50.349467492985347,
    70.242619060656054,
    107.97223660963981,
    250.0,
]


def calc_instant_power(
    df: pl.DataFrame,
    accel_col: str,
    velocity_col: str,
    output_col: str,
) -> pl.DataFrame:
    # this is take straight from https://github.com/eclipse-sumo/sumo/blob/main/src/foreign/PHEMlight/V5/cpp/CEP.cpp#L462
    # obviously, you could ignore the constants and just focus on where accel and speed matter, but nice to have in real units
    power = 0
    speed = df[velocity_col].to_numpy(zero_copy_only=True)
    acc = df[accel_col].to_numpy(zero_copy_only=True)
    rotFactor = np.interp(speed, speedF, RotMassF)

    rolling_resistance = (
        RollingResData["Fr0"]
        + RollingResData["Fr1"] * speed
        + RollingResData["Fr4"] * speed**4
    )
    # Calculate the power
    force = (
        # road load
        (
            (VehicleData["Mass"] + VehicleData["Loading"])
            * GRAVITY_CONST
            * rolling_resistance
            # * speed
        )
        + (VehicleData["A"] * VehicleData["Cw"] * AIR_DENSITY_CONST / 2) * speed**2
        + (
            (
                VehicleData["Mass"] * rotFactor
                + VehicleData["RedMassWheel"]
                + VehicleData["Loading"]
            )
            * acc
            # * speed
        )
    )
    power = force * speed
    # power += (_massVehicle + _vehicleLoading) * GRAVITY_CONST * gradient * 0.01 * speed  # ignore the gradient for now
    power /= 1000

    # Return result
    return df.with_columns(
        pl.Series(
            name=output_col,
            values=power,
            dtype=pl.Float64,
        )
    )
