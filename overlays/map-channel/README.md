# carrot-nav mode 7 → Mac → TURZX

Candidate implementation for carrot-nav `49a342b7d4345591ac71c9d8c7874b88bbaeeaf9`.
The Mac helper remains pinned to `a564ce1d` with a small mode-7 renderer overlay.
This is a display preview of the C4 map, not a replacement for model map input.

## Mac update

Download the `feature/nav-map-hud` branch, quit JetLink and any old HUD helper,
then execute **05-Update-Map.command**. It builds the customized JetLink App,
runs Swift tests, and installs the App, supervisor and map renderer together.
Existing helper changes that conflict with the overlay stop the update.
Backups include the map renderer and receiver. To restore this candidate,
run **04-Rollback.command from this feature branch**; the older main rollback
script does not know about the additional map helper files.
Do not run main's 03-Update.command while testing this branch; it installs the
older App without the map capability.

## C4 sender update

Only on the compatible carrot-nav checkout, while offroad and powered:

```sh
git clone --depth 1 --branch feature/nav-map-hud https://github.com/FANHAOHSIANG/carrotMAC-HUD.git /data/CarrotMacHUD-map
python3 /data/CarrotMacHUD-map/overlays/map-channel/install_c4_map.py
```

If the clone directory already exists, use a new directory name. The installer
checks offroad state and patch compatibility before editing, backs up all three
sender files, and restores them if installation fails. It does not reboot or
switch your openpilot branch. Restart C4 while parked after successful install.

Set `ClusterHudScreenMode=7` using Carrot settings. If the UI lacks mode 7,
confirm that you are using carrot-nav; do not force a value on an unrelated
branch. A route, usable position, fresh navigation instruction, and map tiles
must be available. For mode-7 camera preview with ClusterHud=0, the separate
`overlays/protocol3/c4-camera-heartbeat.patch` is still needed.

## Protocol

HELLO capability `carrot_map_v1`; message ID `0x4004` on the existing USB link.
Wire payload is `<4sQB`: `CM01`, uint64 sequence, uint8 valid; valid=1 is
followed by a 256×256 JPEG; valid=0 is an explicit clear with no image.
Maximum payload is 32768 bytes. Encoding runs in a normal-priority C4 child,
at most 2 Hz. Only the latest packet is retained; images are not queued.
The daemon sends a map after replying to modeld, or during idle polling.
A USB write still uses the normal transport watchdog: real inference latency
under display load must be measured on hardware.

Swift writes an atomic `map.packet` with an 8-byte local receive epoch prefix,
on the background HUD writer. The Mac renderer validates the image, caches
one JPEG, and draws it in mode 7's right panel; the left driving HUD remains.
No Linux /dev/shm path is used on Mac. Invalid maps, missing HUD snapshots,
and packets at least 2 seconds old show the waiting text instead of old maps.
The existing Mac H.264/TURZX output is reused.

## Validation

Python sender→receiver roundtrip, invalid-route clearing, stale/oversize/wrong
image rejection and sequence restart tests are included. Both Swift overlays
and the Mac renderer overlay were checked against their pinned sources.
Swift tests/build run in GitHub's macOS workflow and during local installation.
Actual C4/Mac/TURZX rendering, sustained USB throughput and inference timing
have not been validated by this implementation environment.
