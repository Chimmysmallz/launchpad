# Security policy

LaunchPad is a local development tool. It is designed for trusted home, office and hotspot networks, not for the open internet.

For a full point-by-point review, see [docs/SECURITY-CHECKLIST.md](docs/SECURITY-CHECKLIST.md).

## Protections built in

- The dashboard listens only on `127.0.0.1` unless it is started with `--lan-dashboard`.
- Every change requires a random token that is created on each start, plus a same-origin check. Other web pages in your browser cannot drive LaunchPad (CSRF protection).
- Requests that use an unexpected `Host` are refused (DNS-rebinding protection).
- Uploads are size-limited, zip files are checked as they unpack, and no file can be written or served outside its own folder.
- LaunchPad will not share a whole drive or your home folder.
- Strict security headers are sent on the dashboard, and there are no cookies, trackers or outside requests.

## Known limits

- App links are reachable by every device on the same network. That is the point of phone testing, so avoid public Wi-Fi.
- Apps are served over plain HTTP. Publish to an HTTPS host such as GitHub Pages for anything public.

Please do not expose LaunchPad ports to the internet through port forwarding or tunnels.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use the **Report a vulnerability** button on the **Security** tab of this repository. You should receive a reply within seven days.
