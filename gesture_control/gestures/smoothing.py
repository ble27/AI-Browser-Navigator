"""Time-based filters for low-latency pointer tracking.

The 1€ filter (Casiez, Roussel, Vogel, CHI 2012) keeps a low cutoff while the
signal is still, which removes camera jitter, and raises the cutoff as speed
increases, which keeps a moving fingertip from lagging behind the hand.
Filtering by the wall-clock gap between samples, rather than by a fixed
fraction per frame, means a dropped camera frame does not add extra delay.
"""

from __future__ import annotations

import math


class OneEuroFilter:
    """Adaptively smooth one scalar signal with the 1€ filter.

    Args:
        min_cutoff_hz: Cutoff used when the signal is stationary. Higher
            values follow small motion more quickly and reject less jitter.
        beta: How much extra cutoff to add per unit of speed. Speed is in
            the same units as the signal, per second.
        derivative_cutoff_hz: Cutoff of the filter that estimates speed.
            Keeping this low stops high-frequency jitter from being mistaken
            for real motion, which would otherwise open the filter and let
            the jitter through.
    """

    def __init__(
        self,
        min_cutoff_hz: float,
        beta: float,
        derivative_cutoff_hz: float,
    ) -> None:
        """Create a filter with no samples yet."""
        if min_cutoff_hz <= 0.0 or derivative_cutoff_hz <= 0.0 or beta < 0.0:
            raise ValueError("cutoffs must be positive and beta must be non-negative.")
        self._min_cutoff_hz = min_cutoff_hz
        self._beta = beta
        self._derivative_cutoff_hz = derivative_cutoff_hz
        self._value: float | None = None
        self._derivative = 0.0
        self._last_timestamp_s: float | None = None

    def filter(self, value: float, timestamp_s: float) -> tuple[float, float]:
        """Filter one sample.

        Args:
            value: Raw sample, in the same units the filter was tuned for.
            timestamp_s: Sample time in seconds. Must be monotonic for a
                meaningful speed estimate.

        Returns:
            The filtered value and the smoothed speed in units per second.
        """
        if self._value is None or self._last_timestamp_s is None:
            self._value = value
            self._derivative = 0.0
            self._last_timestamp_s = timestamp_s
            return value, 0.0

        dt = timestamp_s - self._last_timestamp_s
        self._last_timestamp_s = timestamp_s
        # A repeated or reversed timestamp has no trustworthy speed. Hold the
        # last filtered value instead of dividing by zero or reversing time.
        if dt <= 0.0:
            return self._value, self._derivative

        raw_derivative = (value - self._value) / dt
        derivative_alpha = _alpha(dt, self._derivative_cutoff_hz)
        self._derivative += derivative_alpha * (raw_derivative - self._derivative)
        cutoff_hz = self._min_cutoff_hz + self._beta * abs(self._derivative)
        alpha = _alpha(dt, cutoff_hz)
        self._value += alpha * (value - self._value)
        return self._value, self._derivative


def _alpha(dt_s: float, cutoff_hz: float) -> float:
    """Convert a cutoff frequency into the smoothing weight for this gap.

    The exponential time constant ``tau = 1 / (2π f_c)`` is the standard
    1€ mapping from cutoff to a discrete low-pass weight. ``alpha`` is the
    fraction of the new sample to keep, so a higher cutoff (or a longer gap)
    trusts the new sample more.
    """
    tau_s = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau_s / dt_s)
