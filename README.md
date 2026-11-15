# linksys-wifi-tray

See at a glance whether your Linksys router's WiFi is on or off, without logging in to the router's web page.

It asks the router (over its local JNAP API) whether any WiFi radio is enabled, and shows the answer as:

- a **tray icon**: green = WiFi on, red = WiFi off, amber = can't read the router
- a **one-shot check** you can run any time (`--once`)
- **desktop notifications** whenever the state changes (`--notify`)

It only reads status. It never changes any router setting.

## Tested on

- Linksys EA9500, firmware 1.1.9.210876
- Pop!_OS with the COSMIC desktop

Other Linksys routers that use the same JNAP API (the "Smart Wi-Fi" family) may work, but I haven't tested them. Reports are welcome.

## Install

Needs Python 3 (tested with 3.12).

```bash
git clone https://github.com/rhst1/linksys-wifi-tray.git
cd linksys-wifi-tray

pip install --user requests            # enough for --once and --notify
pip install --user pystray pillow      # also needed for the tray icon
```

If pip refuses with "externally-managed-environment", use a virtual environment, or add `--break-system-packages` if you accept the risk.

### Extra steps for the tray icon

- **Debian / Ubuntu / Pop!_OS:** `sudo apt install gir1.2-ayatanaappindicator3-0.1`
- **COSMIC:** add the **Notifications Tray** applet to your panel (Settings -> Desktop -> Panel -> Applets -> Add applet). Without it the icon has nowhere to appear.
- **GNOME:** needs an AppIndicator/tray
