# Derived from TonyBinheWu/sunnypilot 0d3860b94a2b71776a12c1ac8d5ca291c5b63f05; see LICENSE.upstream.
"""Pair a recorded ROAD frame and primary model output with a causal ego-motion window."""
from bisect import bisect_right
import math


def history_at(eof, times, motion):
  # Vehicle yaw rate is clockwise about down. The VLA's local y axis points left.
  poses = [(0., 0., 0.)]
  x = y = heading = 0.
  for step in range(40):
    tick = eof - (40-step) * 50_000_000
    i = bisect_right(times, tick) - 1
    if i < 0 or tick-times[i] > 100_000_000 or motion[i] is None:
      return None
    speed, yaw_right = motion[i]
    dtheta = -.05 * yaw_right
    x += .05 * speed * math.cos(heading + dtheta/2)
    y += .05 * speed * math.sin(heading + dtheta/2)
    heading += dtheta
    if (step+1) % 5 == 0:
      poses.append((x,y,heading))
  # Require a valid terminal observation as well, including any disengaged sensor/gear interval.
  j = bisect_right(times, eof)-1
  window = motion[bisect_right(times, eof-2_000_000_000):j+1]
  if j < 0 or eof-times[j] > 100_000_000 or motion[j] is None or any(point is None for point in window):
    return None
  c, s = math.cos(heading), math.sin(heading)
  return [[(px-x)*c + (py-y)*s, -(px-x)*s + (py-y)*c, math.remainder(yaw-heading, math.tau)] for px,py,yaw in poses]


class MotionWindow:
  def __init__(self):
    self.times, self.motion = [], []
    self.speed = self.vehicle_down = None
    self.speed_time = self.calibration_time = 0

  def observe(self, kind, t, valid, data):
    point = None
    if kind == 'liveCalibration':
      self.vehicle_down = None
      self.calibration_time = t
      if valid and data.calStatus == 'calibrated' and len(data.rpyCalib) == 3 and all(map(math.isfinite, data.rpyCalib)):
        # z column of device_from_calib (Rz Ry Rx), used to rotate measured device rates to vehicle yaw.
        r, p, yaw = data.rpyCalib
        self.vehicle_down = (math.cos(yaw)*math.sin(p)*math.cos(r) + math.sin(yaw)*math.sin(r),
                             math.sin(yaw)*math.sin(p)*math.cos(r) - math.cos(yaw)*math.sin(r), math.cos(p)*math.cos(r))
        return
    elif kind == 'carState':
      self.speed_time = t
      self.speed = data.vEgo if valid and data.canValid and data.gearShifter == 'drive' and math.isfinite(data.vEgo) and data.vEgo >= 0 else None
      if self.speed is not None:
        return
    elif kind == 'livePose':
      pose, rate = data, data.angularVelocityDevice
      valid = (0 < pose.timestamp <= t and t-pose.timestamp <= 100_000_000 and valid and pose.inputsOK and pose.posenetOK and
               pose.sensorsOK and rate.valid and self.vehicle_down is not None and
               self.speed is not None and 0 <= t-self.speed_time <= 100_000_000 and 0 <= t-self.calibration_time <= 5_000_000_000 and
               all(map(math.isfinite, (rate.x, rate.y, rate.z))))
      if valid:
        point = (self.speed, sum(a*b for a,b in zip(self.vehicle_down, (rate.x,rate.y,rate.z), strict=True)))
    else:
      return
    if self.times and t < self.times[-1]:
      self.times.clear()
      self.motion.clear()
    self.times.append(t)
    self.motion.append(point)

  def trim(self, since):
    n = bisect_right(self.times, since)
    del self.times[:n]
    del self.motion[:n]

  def at(self, eof):
    return history_at(eof, self.times, self.motion)


def primary_action(m):
  if m.visionCameraInputs not in ('road', 'roadWide') or not m.timestampEof:
    return None
  if not all(map(math.isfinite, (m.action.desiredAcceleration, m.action.desiredCurvature))):
    return None
  return {'compute': str(m.visionCompute), 'desired_acceleration': m.action.desiredAcceleration,
          'desired_curvature': m.action.desiredCurvature, 'should_stop': m.action.shouldStop}


