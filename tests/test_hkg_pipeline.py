"""C4 publisher -> wire JSON -> Mac reader -> pinned Carrot live UI state.

Run with CARROT_HELPER_ROOT and HKG_CHECKOUT pointing to the two source trees.
No vehicle, GPU, USB or control messages are used.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch


def load_module(name, path):
  spec = importlib.util.spec_from_file_location(name, path)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


@unittest.skipUnless(os.environ.get('CARROT_HELPER_ROOT') and os.environ.get('HKG_CHECKOUT'),
                     'requires pinned Carrot helper and HKG checkout')
class PipelineTests(unittest.TestCase):
  def setUp(self):
    root = Path(__file__).resolve().parents[1]
    helper = Path(os.environ['CARROT_HELPER_ROOT']).resolve()
    publisher_dir = Path(os.environ['HKG_CHECKOUT']).resolve() / 'openpilot/selfdrive/modeld/jetlink'
    wire = load_module('pipeline_wire', publisher_dir / 'hud.py')
    with patch.dict(sys.modules, {'openpilot.selfdrive.modeld.jetlink.hud': wire}):
      self.publisher = load_module('pipeline_publisher', publisher_dir / 'hud_publisher.py')
    self.adapter = load_module('pipeline_adapter', root / 'hkg/hkg_hud.py')
    sys.path[:0] = [str(helper), str(helper / 'openpilot/selfdrive/carrot/cluster')]
    import cluster_live
    self.cluster_live = cluster_live
    cereal = types.ModuleType('openpilot.cereal')
    messaging = types.ModuleType('openpilot.cereal.messaging')
    messaging.SubMaster = self.adapter.HkgSubMaster
    cereal.messaging = messaging
    with patch.dict(sys.modules, {'openpilot.cereal': cereal, 'openpilot.cereal.messaging': messaging}):
      self.source = self.adapter.adapt_live_source(cluster_live)()
    self.addCleanup(self.source.close)
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.packet = Path(self.temp.name) / 'snapshot.packet'
    self.generation = 1000.
    def line(y):
      return dict(x=[i * 4. for i in range(33)], y=[y + .0001 * (i * 4.) ** 2 for i in range(33)],
                  z=[0.] * 33, t=[i * .1 for i in range(33)])
    self.values = {
      'carState': dict(vEgo=20., vEgoCluster=20.5, vCruiseCluster=90., aEgo=-.5,
                       gearShifter='drive', leftBlinker=False, rightBlinker=False,
                       leftBlindspot=True, rightBlindspot=False, cruiseState=dict(available=True, enabled=True)),
      'controlsState': dict(curvature=.001),
      'selfdriveState': dict(enabled=False, active=False, personality='standard', alertSize='none'),
      'carControl': dict(latActive=True, longActive=False),
      'deviceState': dict(started=True),
      'modelV2': dict(position=line(.2), laneLines=[line(y) for y in (-5.4, -1.8, 1.8, 5.4)],
                      laneLineProbs=[.9, .95, .98, .9], roadEdges=[line(-8.), line(8.)], roadEdgeStds=[.1, .2],
                      meta=dict(laneChangeState='off', laneChangeDirection='none')),
      # These are the current HKG schema names, not Carrot's older status field.
      'radarState': dict(leadOne=dict(present=True, dRel=30., yRel=1.5, vRel=-2., vLead=18., radar=True),
                        leadTwo=dict(present=True, dRel=55., yRel=-2., vRel=1., vLead=21., radar=False)),
    }

  def update(self, elapsed=.01):
    class Sources:
      def __getitem__(_, name):
        return self.values.get(name, {})
    sm = Sources()
    sm.valid = sm.alive = {k: k in self.values for k in self.publisher.SERVICES}
    sm.recv_time = dict.fromkeys(self.publisher.SERVICES, 10.)
    record = self.publisher.snapshot(sm, 10.01, True, True)
    payload = self.publisher.encode(record)
    self.assertLessEqual(len(payload), self.publisher.MAX_BYTES)
    self.payload_size = len(payload)
    self.generation += 1.
    # Mac receiver stamps its own epoch. C4 monotonic time is not compared to it.
    self.packet.write_bytes(self.adapter.HEADER.pack(self.generation) + payload)
    with patch.object(self.adapter, 'snapshot', side_effect=lambda: self.adapter.read_packet(
        self.packet, epoch=self.generation + elapsed, mono=time.monotonic())):
      return self.source.update()

  def test_lane_path_edges_keep_curves_sides_probabilities_and_endpoints(self):
    state = self.update()
    self.assertEqual(len(state.model_path), 17)
    self.assertEqual(state.model_path[-1].forward_m, 128.)
    self.assertAlmostEqual(state.model_path[-1].lateral_m, 1.8384)
    lanes = [lane for lane in state.lanes if lane.model_points]
    self.assertEqual(len(lanes), 4)
    self.assertEqual([lane.model_points[0].lateral_m for lane in lanes], [-5.4, -1.8, 1.8, 5.4])
    self.assertTrue(all(lane.visible for lane in lanes))
    self.assertEqual(len(state.left_road_edge_points), 17)
    self.assertEqual(state.left_road_edge_points[0].lateral_m, -8.)
    self.assertEqual(state.right_road_edge_points[0].lateral_m, 8.)
    self.assertAlmostEqual(self.source.parser.left_road_edge_confidence, .95)
    self.values['modelV2']['laneLineProbs'][1] = .01
    state = self.update()
    lanes = [lane for lane in state.lanes if lane.model_points]
    self.assertFalse(lanes[1].visible)
    self.assertTrue(lanes[2].visible)

  def test_speed_cluster_speed_cruise_and_stop_units(self):
    state = self.update()
    self.assertEqual(state.speed_kph, 72.)
    self.assertAlmostEqual(state.display_speed_kph, 73.8)
    self.assertEqual(state.cruise_kph, 90.)
    self.assertEqual(state.accel_mps2, -.5)
    self.assertEqual(state.gear_text, 'D')
    self.assertTrue(state.left_blindspot)
    self.assertFalse(state.right_blindspot)
    self.assertTrue(state.lfa_active)  # MADS lateral may be active while selfdrive is disabled.
    self.values['carState'].update(vEgo=0., vEgoCluster=0., gearShifter='park')
    state = self.update()
    self.assertEqual((state.speed_kph, state.display_speed_kph, state.gear_text), (0., 0., 'P'))

  def test_two_hkg_present_leads_render_correct_sides_speed_and_ttc(self):
    vehicles = self.update().detected_vehicles
    self.assertEqual(len(vehicles), 2)
    left, right = vehicles
    self.assertEqual((left.label, left.longitudinal_m, left.lateral_m), ('L1', 30., -1.5))
    self.assertEqual((right.label, right.longitudinal_m, right.lateral_m), ('L2', 55., 2.))
    self.assertEqual(left.relative_speed_mps, -2.)
    self.assertAlmostEqual(left.absolute_speed_kph, 64.8)
    self.assertEqual(left.ttc_s, 15.)
    self.assertIsNone(right.ttc_s)
    self.values['radarState']['leadOne']['present'] = False
    self.assertEqual([v.label for v in self.update().detected_vehicles], ['L2'])
    self.values['radarState']['leadTwo']['present'] = False
    self.assertEqual(self.update().detected_vehicles, ())

  def test_model_visual_leads_without_radar_and_low_probability_rejection(self):
    from cluster_route_replay import RADAR_TO_CAMERA_M
    self.values.pop('radarState')
    def lead(prob, y):
      return dict(prob=prob, probTime=0., x=[40., 80.], y=[y, 7.], v=[18., 50.], a=[-.2, 2.],
                  xStd=[.5, 5.], yStd=[.1, 1.])
    self.values['modelV2'].update(leadsV3=[lead(.9, -1.), lead(.8, 2.), lead(.1, 0.)],
                                 velocity={'x': [20., 50.]})
    vehicles = self.update().detected_vehicles
    self.assertEqual(len(vehicles), 2)
    self.assertEqual({v.source for v in vehicles}, {'modelV2.leadsV3'})
    self.assertEqual([v.lateral_m for v in vehicles], [-1., 2.])
    self.assertAlmostEqual(vehicles[0].longitudinal_m, 40. - RADAR_TO_CAMERA_M)
    self.assertEqual(vehicles[0].relative_speed_mps, -2.)
    self.assertAlmostEqual(vehicles[0].absolute_speed_kph, 64.8)
    self.assertEqual(vehicles[0].x_std_m, .5)

  def test_missing_geometry_and_expired_packet_clear_real_objects(self):
    self.update()
    self.values.pop('modelV2')
    self.values.pop('radarState')
    state = self.update()
    self.assertEqual(state.model_path, ())
    self.assertEqual(state.detected_vehicles, ())
    self.assertFalse(any(lane.model_points for lane in state.lanes))
    self.assertEqual(state.left_road_edge_points, ())
    state = self.update(elapsed=.51)
    self.assertEqual(state.alert.alert_type, 'hkgHudStale')
    self.assertEqual(state.detected_vehicles, ())

  def test_adjacent_radar_tracks_reach_scene_with_real_speed_and_normal_priority(self):
    from cluster_scene import build_cluster_scene
    self.values['radarTracks'] = dict(points=[
      dict(trackId=101, dRel=20., yRel=3.5, vRel=-2.),
      dict(trackId=102, dRel=25., yRel=-3.5, vRel=1.),
      dict(trackId=103, dRel=10., yRel=float('nan'), vRel=0.),
    ])
    state = self.update()
    points = {p.label: p for p in state.radar_points}
    self.assertEqual(set(points), {'T101', 'T102'})
    self.assertEqual(points['T101'].lateral_m, -3.5)
    self.assertEqual(points['T102'].lateral_m, 3.5)
    self.assertAlmostEqual(points['T101'].absolute_speed_kph, 64.8)
    self.assertAlmostEqual(points['T102'].absolute_speed_kph, 75.6)
    scene = build_cluster_scene(state)
    vehicles = {v.label: v for v in scene.vehicles}
    self.assertIn('T101', vehicles)
    self.assertIn('T102', vehicles)
    self.assertFalse(vehicles['T101'].primary)
    self.assertFalse(vehicles['T102'].primary)
    self.assertTrue(vehicles['L1'].primary)
    self.values['radarTracks']['points'] = []
    self.assertEqual(self.update().radar_points, ())

  def test_radar_track_fault_loss_and_no_lateral_data_never_invent_side_cars(self):
    self.values['radarTracks'] = dict(points=[dict(trackId=1, dRel=20., yRel=3.5, vRel=1.)])
    self.assertTrue(self.update().radar_points)
    self.values['radarTracks']['errors'] = {'canError': True}
    self.assertEqual(self.update().radar_points, ())
    self.values['radarTracks'].pop('errors')
    self.assertTrue(self.update().radar_points)
    self.values.pop('radarTracks')
    self.assertEqual(self.update().radar_points, ())
    self.values['radarTracks'] = dict(points=[dict(trackId=1, dRel=20., yRel=float('nan'), vRel=1.)])
    state = self.update()
    self.assertEqual(state.radar_points, ())
    self.assertTrue(state.left_blindspot)
    self.assertEqual(len(state.detected_vehicles), 2)  # only the original L1/L2
    self.assertEqual(self.update(elapsed=.51).radar_points, ())


if __name__ == '__main__':
  unittest.main()
