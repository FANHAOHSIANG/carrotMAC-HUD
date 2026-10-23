"""Adapt hkg's bounded JSON snapshots to the existing Carrot Mac renderer.

Install alongside the pinned, Mac-patched tools/jetlink/hud.py. The Carrot
renderer, H.264 encoder, TURZX driver and panel ownership remain unchanged.
"""
import base64
import json
import math
from pathlib import Path
import struct
import time
from types import SimpleNamespace

SOURCE = 'hkg_hud_v1'
MAX_BYTES = 14 * 1024
HEADER = struct.Struct('<d')
ALLOWED = ('carState', 'controlsState', 'selfdriveState', 'carControl', 'modelV2', 'radarState', 'deviceState', 'radarTracks')


def namespace(value):
  if isinstance(value, dict):
    return SimpleNamespace(**{k: namespace(v) for k, v in value.items()})
  if isinstance(value, list):
    return [namespace(v) for v in value]
  return value


def read_packet(path, epoch=None, mono=None):
  epoch = time.time() if epoch is None else epoch
  mono = time.monotonic() if mono is None else mono
  try:
    with path.open('rb') as stream:
      raw = stream.read(HEADER.size + MAX_BYTES + 1)
    if not HEADER.size < len(raw) <= HEADER.size + MAX_BYTES:
      return None
    received, = HEADER.unpack_from(raw)
    elapsed = epoch - received
    if not 0 <= elapsed < .5:
      return None
    record = json.loads(raw[HEADER.size:])
    if record.get('version') != 1 or record.get('source') != SOURCE:
      return None
    if not isinstance(record.get('hkg'), dict) or not isinstance(record.get('age'), dict):
      return None
    sent = float(record['sent'])
    if not math.isfinite(sent):
      return None
    data, age = {}, {}
    for name in ALLOWED:
      item = record['hkg'].get(name)
      source_age = record['age'].get(name)
      limit = 1.5 if name == 'deviceState' else .5
      if isinstance(item, dict) and isinstance(source_age, (int, float)) and 0 <= source_age + elapsed < limit:
        # Current HKG publishes RadarData as radarTracks; pinned Carrot uses
        # the points member of liveTracks. This alias is display-local only.
        target = 'liveTracks' if name == 'radarTracks' else name
        data[target] = item
        age[target] = source_age + elapsed
    record = dict(record, hkg=data, age=age, _received_epoch=received)
    return mono - elapsed, record
  except (OSError, ValueError, TypeError, KeyError, AttributeError, struct.error):
    return None


def snapshot():
  from hud_runtime import PACKET
  return read_packet(PACKET)


class HkgSubMaster:
  def __init__(self, services):
    self.services = services
    self.data = {name: SimpleNamespace() for name in services}
    self.updated = dict.fromkeys(services, False)
    self.valid = dict.fromkeys(services, False)
    self.alive = dict.fromkeys(services, False)
    self.recv_time = dict.fromkeys(services, 0.)
    self.logMonoTime = dict.fromkeys(services, 0)
    self.generation = None

  def __getitem__(self, key):
    return self.data[key]

  def update(self, timeout=0):
    if hasattr(self, 'pending_snapshot'):
      value = self.pending_snapshot
      del self.pending_snapshot
    else:
      value = snapshot()
    now = time.monotonic()
    record = value[1] if value else {}
    generation = record.get('_received_epoch')
    new = generation != self.generation
    self.generation = generation
    for name in self.services:
      item = record.get('hkg', {}).get(name)
      good = item is not None
      self.updated[name] = good and (new or not self.alive[name])
      self.valid[name] = self.alive[name] = good
      if good:
        if name == 'deviceState':
          # hkg currently forwards started/deviceType only. The pinned HUD
          # statistics reader accesses these attributes directly. Empty/None
          # means unavailable; do not invent a zero-percent vehicle reading.
          item = {'cpuUsagePercent': [], 'memoryUsagePercent': None, 'freeSpacePercent': None, **item}
        self.data[name] = namespace(item)
        self.recv_time[name] = now - record['age'][name]
        self.logMonoTime[name] = int(self.recv_time[name] * 1e9)
      else:
        self.data[name] = SimpleNamespace()
        self.recv_time[name] = 0.
        self.logMonoTime[name] = 0


def adapt_live_source(cluster_live):
  OriginalSource = cluster_live.OpenpilotLiveSource

  class HkgLiveSource(OriginalSource):
    previous_availability = None

    def update(self):
      value = snapshot()
      self.packet_connected = value is not None
      names = tuple(sorted(value[1]['hkg'])) if value else ()
      if names != self.previous_availability:
        # Carrot's parser caches paths, leads and latActive between updates.
        # Reset on source loss/recovery so stale objects cannot survive it.
        self.parser = cluster_live.live_route_parser()
        self.previous_availability = names
        self.sm.generation = None
        now = time.monotonic()
        if now >= getattr(self, 'next_availability_log', 0.):
          print('HKG HUD available sources: ' + (', '.join(names) or 'none (missing/stale packet)'), flush=True)
          self.next_availability_log = now + 2.
      # The parent calls sm.update(). Use the same snapshot for invalidation
      # and parsing, even if a packet arrives/expires between these two steps.
      self.sm.pending_snapshot = value
      return super().update()

    def _live_cluster_alert(self, current_alert, onroad):
      if not self._service_alive('carState'):
        if getattr(self, 'packet_connected', False):
          standby = self.onroad_state() is False
          return cluster_live.ClusterAlert(
            text1='HUD connected' if standby else 'Waiting for vehicle data',
            text2=('Vehicle standby | ' + time.strftime('%H:%M:%S')) if standby else 'C4 connected; carState unavailable',
            size=2, status=0 if standby else 1, alert_type='hkgHudStandby' if standby else 'hkgHudWaiting')
        return cluster_live.ClusterAlert(text1='HUD data unavailable', text2='Check C4 / USB connection',
                                        size=2, status=1, alert_type='hkgHudStale')
      return super()._live_cluster_alert(current_alert, onroad)

  return HkgLiveSource


def display_params(OriginalParams, display):
  class HkgParams(OriginalParams):
    def get(self, key, *args, **kwargs):
      override = display.get(key)
      if override is not None:
        return override
      if key == 'ClusterHud':
        return b'1'
      if key == 'ClusterHudDebug':
        # Carrot mode 1 permits live standby output at startup and offroad.
        # Modes 2/3 add debug panels. Never fake IsOnroad or vehicle.started.
        return b'1'
      if key == 'ShowDateTime':
        return b'1'
      # Preserve display mode across an interrupted USB lease, but never
      # cache vehicle state or a positive external-compute badge.
      if key == 'UsbGpuActive':
        value = snapshot()
        return b'1' if value and value[1].get('external_compute_label') == 'MAC' else b'0'
      if key == 'ClusterHudScreenMode':
        return b'0'  # driving scene; camera/map channels are not ported
      return super().get(key, *args, **kwargs)

  return HkgParams


def main():
  import hud
  import hud_protocol
  from hkg_display import DisplaySettings
  hud.read_snapshot = hud_protocol.read_snapshot = snapshot
  hud.RemoteSubMaster = HkgSubMaster
  hud.DisplayParams = display_params(hud.DisplayParams, DisplaySettings())
  import cluster_live
  cluster_live.OpenpilotLiveSource = adapt_live_source(cluster_live)
  hud.main()


if __name__ == '__main__':
  main()
