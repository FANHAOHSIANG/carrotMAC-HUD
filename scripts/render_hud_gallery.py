"""Capture the installed HUD renderer with deterministic synthetic telemetry, never car I/O."""
import io, json, os, sys, time
from dataclasses import replace
from pathlib import Path
from PIL import Image, ImageChops

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
out.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(root),str(root/'openpilot/selfdrive/carrot/cluster')]
from cluster_renderer import ClusterUiRenderer
from cluster_models import (SimulatorInput, NaviItemMeta, NaviLiveState, NaviSpeedInfo,
                            NaviTrafficLightInfo, NaviGuidanceInfo, NaviStatusInfo, NaviRouteInfo,
                            NaviVehicleInfo, DetectedVehicle, ModelPathPoint)
from cluster_simulator import ClusterSimulator
import mac_vision_overlay as vision

sim=ClusterSimulator()
state=replace(sim.update(SimulatorInput(),.05),onroad=True,gear_text='D',
              speed_kph=58.,cruise_kph=65,speed_limit_kph=60,speed_limit_source='v',
              live_brake_lamps=False,detected_vehicles=(DetectedVehicle('L1',24.,0.,source='radarState',primary=True,absolute_speed_kph=54.),))
renderer=ClusterUiRenderer(width=1920,height=480,theme_mode='dark',screen_mode=0,language='zh-TW')
renderer.open(hidden=True)

def capture(s,mode=0,signals=None):
    renderer.set_screen_mode(mode)
    # Signal phase is an explicit simulated input to the real renderer.
    original=renderer._turn_signal_lights
    if signals is not None: renderer._turn_signal_lights=lambda _: signals
    try:
        result=Image.open(io.BytesIO(renderer.render_to_png_bytes(s))).convert('RGB')
        result.load()
        if result.getbbox() is None or len(result.getcolors(maxcolors=256) or [])<=1 and result.getcolors(maxcolors=256) is not None:
            raise RuntimeError('blank HUD capture')
        return result
    finally: renderer._turn_signal_lights=original

def still(name,s,mode=0):
    capture(s,mode).save(out/name,optimize=True)
def gif(name,brake,left,right):
    s=replace(state,live_brake_lamps=brake,left_signal=left,right_signal=right)
    off=capture(s,signals=(False,False))
    on=capture(s,signals=(left,right))
    if not(left or right):
        off=capture(replace(s,live_brake_lamps=False),signals=(False,False))
    assert ImageChops.difference(off,on).getbbox() is not None,name
    off.save(out/name,save_all=True,append_images=[on],duration=[500,500],loop=0,disposal=2)

try:
    still('driving.png',state)
    gif('brake.gif',True,False,False)
    gif('left.gif',False,True,False)
    gif('right.gif',False,False,True)
    gif('hazard-brake.gif',True,True,True)
    def nav(green=False,camera=True,exit=False):
        now=time.monotonic()
        meta=NaviItemMeta(1,round(time.time()*1000),now)
        speed=NaviSpeedInfo(meta,58.,road_limit_kph=60,sdi_type=0 if camera else None,sdi_distance_m=350 if camera else None,sdi_speed_limit_kph=50 if camera else None)
        traffic=NaviTrafficLightInfo(distance_m=180,red_on=not green,straight_on=green,red_s=24 if not green else None,straight_s=12 if green else None,meta=meta,counter_s=12 if green else 24,source='amap_auto')
        return NaviLiveState(1,'demo',vehicle=NaviVehicleInfo(meta,24.8,121.0,0.,58.,'台68線'),current=NaviGuidanceInfo(meta,800,45,13,'縣道120','右轉'),speed=speed,traffic_light=traffic,status=NaviStatusInfo(meta,'navigation',True,False,True),route=NaviRouteInfo(meta,12300,900,2000,120,14300,((24.8,121.),(24.802,121.),(24.804,121.001),(24.806,121.002))),amap_exit_name='竹北交流道' if exit else '',amap_exit_deadline_s=now+1.9 if exit else 0.,amap_exit_direction='右側' if exit else '',amap_route_remaining_text='12.3 km' if exit else '')
    still('speed-limit.png',replace(state,navi_live=None))
    still('camera-red.png',replace(state,navi_live=nav()))
    still('camera-green.png',replace(state,navi_live=nav(green=True)))
    still('navigation.png',replace(state,navi_live=nav(exit=True)),6)
    still('mode7.png',replace(state,navi_live=nav()),7)
    # The legend uses the actual detection-class drawing path. These are fixtures,
    # not detections made by YOLO. No fake calibration is supplied.
    vision.RESULT.parent.mkdir(parents=True,exist_ok=True)
    vision.RESULT.write_text(json.dumps([time.time(),[[kind,.5,.7,.05,.1] for kind in vision.KINDS]]))
    still('object-legend.png',state)
    vision.RESULT.unlink(missing_ok=True)
finally:
    renderer.close()
