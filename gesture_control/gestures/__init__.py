"""Pure-Python gesture recognition over hand-landmark coordinates.

Everything in this package operates on normalized landmark coordinates
(floats in ``[0, 1]``) produced by :mod:`gesture_control.vision`. It performs
no I/O and makes no OS calls, so it is fully unit-testable with synthetic
landmark data -- no camera or display required.
"""
