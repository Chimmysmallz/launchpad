# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-28

### Added
- Drag-and-drop deploys from a folder, a `.zip` or a single `.html` file
- A fixed link for each app on the laptop and on the local network
- Optional phone QR codes
- Linked folders with live reload
- Version history with one-click rollback (last 10 versions)
- Single-page app routing, short links, custom 404 pages and video streaming (range requests)
- Download a live version as a `.zip`
- Windows, macOS and Linux launchers
- End-to-end test suite and GitHub Actions on Windows, macOS and Linux

### Security
- Per-run dashboard token, same-origin and Host checks (CSRF and DNS-rebinding protection)
- Strict security headers on the dashboard; `nosniff` on hosted apps
- Upload limits (1 GB per file, 2 GB and 20,000 files per deploy) with zip-bomb and zip-slip protection
- Refuses to share a whole drive or the home folder; sub-folders cannot leave a linked folder
- App names cleaned and length-limited; no names inside dashboard JavaScript
- CodeQL code scanning and Dependabot updates
- Security and privacy checklist in `docs/SECURITY-CHECKLIST.md`
