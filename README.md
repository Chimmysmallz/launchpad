# 🚀 LaunchPad

**Drop an app, get a link. Test it on your laptop and your phone, all on your own computer.**

[![Tests](https://github.com/YOUR-USERNAME/launchpad/actions/workflows/tests.yml/badge.svg)](https://github.com/YOUR-USERNAME/launchpad/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](LICENSE)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

You finish a build late at night and you want to see it on your phone before anyone else does. Uploading it to a hosting service just to check a button is slow, and on some networks the upload never finishes. LaunchPad gives you the drag-and-drop feel of a hosting dashboard, but it runs on your own machine. Every app you drop in gets its own link, and any phone on the same Wi-Fi can open it.

It is one Python file with no required installs.

## Features

- **Drag-and-drop deploys.** Drop a folder, a `.zip` or a single `.html` file.
- **A link for every app.** For example, `http://localhost:8101` on the laptop and `http://192.168.x.x:8101` on the phone. Links stay the same after a restart.
- **Phone QR codes.** Scan with your phone camera to open the app.
- **Linked folders with live reload.** Point LaunchPad at your project folder. Save a file, and the page refreshes on every open device within about a second.
- **Version history and one-click rollback.** The last 10 deploys of each app are kept.
- **Smart detection.** It skips `node_modules` and `.git`, unwraps zip files that have one folder inside, and serves `dist`, `build`, `public`, `out` or `docs` when that is where `index.html` lives.
- **Hosting features you expect.** Single-page app routing, short links (`/about` opens `about.html`), custom `404.html`, and video streaming that works on iPhone.
- **Download any live version as a `.zip`.** Ready to publish on GitHub Pages.

## Quick start

### Windows
1. Download the latest **LaunchPad-Kit.zip** from [Releases](../../releases) and unzip it.
2. Double-click **Start LaunchPad.bat**.
3. When Windows asks about network access for Python, tick **Private networks** and allow it.

### macOS and Linux
```sh
git clone https://github.com/YOUR-USERNAME/launchpad.git
cd launchpad
./start-launchpad.sh
```

The dashboard opens at **http://localhost:8100**.

You need **Python 3.8 or newer** from [python.org](https://www.python.org/downloads/). On Windows, tick *Add Python to PATH* during setup.

## Testing on your phone

1. Connect your phone to the same Wi-Fi as your computer. A phone hotspot also works: connect the laptop to it.
2. Open the app card on the dashboard and tap **Phone QR**, or type the phone link.

If the phone cannot connect, the cause is almost always the computer's firewall. Allow Python on private networks and make sure the Wi-Fi is set as a *Private* network, not *Public*.

## Two ways to work

| | Uploaded app | Linked folder |
|---|---|---|
| How it updates | Click **Deploy new version** | Automatically when you save a file |
| History and rollback | Yes, last 10 versions | No, it always serves the folder as it is now |
| Best for | Comparing builds and sharing a stable version | Active development |
| Files are copied | Yes, into `data/` | No, nothing is copied or deleted |

## Options

| Setting | How |
|---|---|
| Change dashboard port | `set LAUNCHPAD_PORT=9000` (Windows) or `LAUNCHPAD_PORT=9000 ./start-launchpad.sh` |
| Store data elsewhere | `LAUNCHPAD_DATA=/path/to/folder` |
| Open dashboard from other devices | `python launchpad.py --lan-dashboard` |
| Do not open a browser on start | `python launchpad.py --no-browser` |

## Publishing to the world

LaunchPad is for testing on your own network. When an app is ready for the public:

1. Click **Download .zip** on the app card and unzip it.
2. Create a GitHub repository and upload the files.
3. Open **Settings → Pages**, select the `main` branch and the root folder, and save.

## Security and privacy

LaunchPad passes the common 20-point app security checklist and a 7-point privacy checklist. Points written for public sites with accounts or payments are marked not applicable. See the full review in [docs/SECURITY-CHECKLIST.md](docs/SECURITY-CHECKLIST.md).

- **Safe dashboard.** It listens on this computer only. Every change needs a per-run token, and it blocks cross-site requests and DNS rebinding.
- **Safe uploads.** Size limits, zip-bomb and zip-slip protection, and no file can escape its folder.
- **Strict security headers** on the dashboard.
- **No tracking at all.** No cookies, analytics or outside fonts, and nothing leaves your computer.
- **Scanned automatically.** CodeQL and Dependabot run on GitHub.

Apps are visible to devices on your network, which is what makes phone testing work, so avoid public Wi-Fi. To report a problem, see [SECURITY.md](SECURITY.md).

## What LaunchPad is not

LaunchPad serves static websites: HTML, CSS, JavaScript and built front-end apps from React, Vue, Svelte, Vite and similar tools. It does not run server code such as PHP, Node.js back ends or Python web apps. Tools like Streamlit already print their own *Network URL*, so open that on your phone directly.

## Project layout

```
launchpad.py            the whole server: dashboard, deploys and app hosting
static/dashboard.html   the dashboard interface
Start LaunchPad.bat     Windows launcher
start-launchpad.sh      macOS and Linux launcher
tests/                  end-to-end and security tests (standard library only)
docs/                   security and privacy checklist
```

## Running the tests

```sh
python -m unittest discover -s tests -v
```

## Contributing

Ideas and fixes are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first.

## License

[MIT](LICENSE) © 2026 Chiamaka Nwabulue
