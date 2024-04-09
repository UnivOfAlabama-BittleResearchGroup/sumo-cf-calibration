import numpy as np
import pandas as pd

from functions.config import Error


def _join_n_add_spacing(rw_df: pd.DataFrame, sim_df: pd.DataFrame) -> pd.DataFrame:
    # join dataframes
    df = sim_df.join(
        rw_df,
        how="inner",
        lsuffix="_sim",
    ).dropna()

    df["spacing_follow"] = df["s_lead"] - df["length_lead"] - df["s_follow"]
    df["spacing_follow_sim"] = df["s_lead_sim"] - df["length_lead"] - df["s_follow_sim"]

    return df


def fast_error(rw_df: pd.DataFrame, sim_df: pd.DataFrame, conf: Error) -> float:
    # only calculate the error function specified in the config file
    return float(
        globals()[conf.error_func](
            _join_n_add_spacing(rw_df, sim_df),
            col="spacing" if conf.method == "spacing" else "velocity",
        )
    )


def error_metrics(rw_df: pd.DataFrame, sim_df: pd.DataFrame, conf: Error) -> Error:
    # join dataframes
    df = _join_n_add_spacing(rw_df, sim_df)
    """Calculate error metrics and update config file."""
    error_strings = ["s", "velocity"]
    if conf.include_accel:
        error_strings.append("accel")
    for f in [rmsn, rmspe, mpe, nrmse_s_v, nrmse, rmse, nrmse_s_v_a]:
        for col in error_strings:
            if f.__name__ == "nrmse_s_v" or f.__name__ == "nrmse_s_v_a":
                conf[f"{f.__name__}"] = float(
                    f(
                        df=df,
                    )
                )
            else:
                conf[f"{f.__name__}_{col}"] = float(
                    f(
                        df=df,
                        col="spacing" if col == "s" else col,
                    )
                )

    return conf


def rmse(df: pd.DataFrame, col: str = "s") -> float:
    # root mean square error
    return np.sqrt(
        np.mean(np.square(df[f"{col}_follow_sim"].values - df[f"{col}_follow"].values))
    )


def rmsn(df: pd.DataFrame, col: str = "s") -> float:
    # root mean square error normalized
    return np.sqrt(
        df.shape[0]
        * np.mean(
            np.square(df[f"{col}_follow_sim"].values - df[f"{col}_follow"].values)
        )
    ) / np.sum(df[f"{col}_follow"].values)


def rmspe(df: pd.DataFrame, col: str = "s") -> float:
    # root mean square percentage error
    return np.sqrt(
        np.mean(
            np.square(
                (df[f"{col}_follow_sim"].values - df[f"{col}_follow"].values)
                / df[f"{col}_follow"].values
            )
        )
    )


def mpe(df: pd.DataFrame, col: str = "s") -> float:
    # mean percentage error
    return np.mean(
        (df[f"{col}_follow_sim"].values - df[f"{col}_follow"].values)
        / df[f"{col}_follow"].values
    )


def nrmse(df: pd.DataFrame, col: str = "s") -> float:
    # normalized root mean square error
    return rmse(df, col) / np.sqrt(np.mean(np.square(df[f"{col}_follow"].values)))


def nrmse_s_v(df: pd.DataFrame, *args, **kwargs) -> float:
    return nrmse(df, col="spacing") + nrmse(df, col="velocity")


def nrmse_s_v_a(df: pd.DataFrame, *args, **kwargs) -> float:
    return (
        nrmse(df, col="spacing") + nrmse(df, col="velocity") + nrmse(df, col="accel")
    ) / 3
