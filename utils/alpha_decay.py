"""Exponential alpha decay for signal freshness: V(t) = e^(-lambda * t), lambda = ln(2) / half_life."""

import numpy as np


def calculate_alpha_decay(signal_timestamp, current_timestamp, half_life):
    """
    Calculates the alpha decay factor for a trading signal using an exponential decay formula.

    Formula: V(t) = e^(-lambda * t)
    Where lambda = ln(2) / half_life

    Args:
        signal_timestamp (float or np.ndarray): Unix timestamp(s) when the signal was generated.
        current_timestamp (float or np.ndarray): Current Unix timestamp(s).
        half_life (float): The time period after which the signal value is reduced by 50%.
                           Units must match the timestamps (usually seconds).

    Returns:
        tuple: (decay_factor, is_expired)
            decay_factor (float or np.ndarray): Factor between 0 and 1.
            is_expired (bool or np.ndarray): True if decay_factor < 0.5.
    """
    delta_t = np.maximum(0, current_timestamp - signal_timestamp)
    decay_constant = np.log(2) / half_life
    decay_factor = np.exp(-decay_constant * delta_t)
    is_expired = decay_factor < 0.5
    return decay_factor, is_expired
