"""The Action Mapper: the single shared contract for gestures and voice.

Both a recognized gesture (from :mod:`gesture_control.gestures`) and a parsed
voice command (from :mod:`gesture_control.voice`) resolve to an ``Intent``,
defined in this package. The Action Mapper translates an ``Intent`` into one
or more calls on the :class:`gesture_control.backends.InputBackend`
interface. No caller outside this package should ever call an
``InputBackend`` directly.
"""
