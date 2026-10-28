# Security and privacy checklist

This page shows how LaunchPad measures up against two common pre-launch checklists. It covers a 20-point app security list and a 7-point privacy and data-protection list. Every **Pass** below is covered by an automated test in `tests/test_smoke.py` or can be checked in the code.

LaunchPad is a local developer tool. It has no user accounts, no database, no payments and no analytics, and it sends nothing from your computer to the internet. Several items on these lists are written for public web apps with sign-ups, so they are marked **Not applicable**, with the reason.

## Part 1: 20-point app security checklist

| # | Check | Result | How LaunchPad handles it |
|---|---|---|---|
| 1 | Hide API keys | Pass | The code contains no API keys or credentials. The only secret is a random dashboard token that is created in memory on every start and never saved. |
| 2 | Purge Git secrets | Pass | The history has no secrets. `.gitignore` excludes `data/`, so apps you deploy never reach GitHub. Turn on GitHub secret scanning and push protection for extra safety. |
| 3 | Use public DB key | Not applicable | There is no database. Settings are stored in a local JSON file. |
| 4 | Enable row-level security | Not applicable | There is no database and there are no other users' rows. |
| 5 | Encrypt sensitive data | Not applicable | LaunchPad stores no personal or sensitive data, only app names, port numbers and folder paths on your own computer. |
| 6 | Enforce server-side auth | Pass | Every action that changes something (deploy, link, rename, delete) is checked on the server. It must carry the per-run dashboard token, come from an allowed host and come from the same origin. The dashboard listens only on `127.0.0.1` by default. |
| 7 | Lock record access | Pass | Other web pages open in your browser cannot read or change your apps. Cross-site requests are refused, and DNS-rebinding attempts are blocked by checking the `Host` header. |
| 8 | Block field tampering | Pass | The server checks every field it receives. Ports must be numbers between 1024 and 65535. Sub-folders cannot contain `..` or a drive letter. Names are cleaned and capped at 80 characters. |
| 9 | Secure session cookies | Not applicable | LaunchPad sets no cookies. |
| 10 | Hash passwords | Not applicable | There are no passwords or accounts. |
| 11 | Rate limit login | Not applicable | There is no login. Only the computer running LaunchPad can make changes. |
| 12 | Add bot protection | Not applicable | It is not on the public internet, and nothing can be changed from outside your computer. |
| 13 | Parameterize queries | Not applicable | There is no SQL. File paths are built from cleaned parts and checked to stay inside their folder. |
| 14 | Validate all input | Pass | It checks names, ports, sub-folders, linked folder paths, upload sizes and upload IDs, and gives a clear error for bad input. |
| 15 | Escape user content | Pass | App names and paths are HTML-escaped in the dashboard and never placed inside JavaScript. Error pages and file listings escape file names. |
| 16 | Restrict file uploads | Pass | Each file is limited to 1 GB, and each deploy to 2 GB and 20,000 files. Zip files are size-checked as they unpack, so a "zip bomb" cannot fill your disk. Paths such as `../` cannot escape the deploy folder ("zip slip"). Uploaded files are only served, never run. LaunchPad refuses to share a whole drive or your home folder. |
| 17 | Trim API responses | Pass | The dashboard API answers only to the local computer, and it returns only what the dashboard shows. The server does not reveal its Python version. |
| 18 | Add security headers | Pass | The dashboard sends a strict Content-Security-Policy, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a Permissions-Policy and cross-origin isolation headers. Hosted apps get `nosniff`. |
| 19 | Force HTTPS | Not applicable (known limit) | LaunchPad serves plain HTTP on your own network, as most local test servers do. Anything public should go through GitHub Pages, which provides HTTPS. Phone browsers allow some features (camera, service workers, location) only over HTTPS, so test those after you publish. |
| 20 | Scan dependencies | Pass | There are no required dependencies. Dependabot watches the optional QR package and the GitHub Actions. CodeQL scans the Python and JavaScript on every change and every week. |

## Part 2: privacy and data-protection checklist

| # | Check | Result | How LaunchPad handles it |
|---|---|---|---|
| 1 | Age check | Not applicable | LaunchPad has no sign-ups and collects no personal data from anyone. |
| 2 | Google Fonts leaking IP | Pass | It uses system fonts only. The dashboard makes no requests to any outside server, and its Content-Security-Policy blocks them. |
| 3 | Hotjar recording passwords | Pass | There are no analytics, trackers or session recorders of any kind. |
| 4 | Waitlist email with no unsubscribe | Not applicable | LaunchPad collects no email addresses and sends no email. |
| 5 | Paystack button with no renewal terms | Not applicable | LaunchPad is free and has no payments. |
| 6 | Profile pictures as biometric data | Not applicable | There are no profiles or photos. |
| 7 | No cookie banner | Pass | No cookie banner is needed. LaunchPad sets no cookies. The only browser storage is one local setting that remembers which Wi-Fi address you picked, and it never leaves your computer. |

## Your own apps

These results cover **LaunchPad itself**. The apps you test with it are your responsibility. When an app has sign-ups, payments, analytics or emails, run the same two checklists against that app before launch.

## Network exposure

Apps you deploy can be opened by every device on the same network, which is how phone testing works. Use LaunchPad on home, office or hotspot networks you trust, and do not expose its ports to the internet.
