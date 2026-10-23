# Changelog

All notable changes to MudaleTunnel are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Django control-plane with scope enforcement and process supervisor
- Services layer with hardened nmap XML parsing
- REST API and authenticated WebSocket layer
- `mudale` CLI for managing tunnels, scans, and forwards from the terminal
- Interactive console mode (`mudale console`) with tab-completion and inline help
- Engine daemon for background tunnel supervision and health checks
- React 18 dashboard (SPA) served in production
- Nmap-driven pivoting: scans run through SOCKS proxies, findings become local forwards
- Ligolo-ng adapter for TUN-based pivoting alongside SSH tunnels
- Docker and Docker Compose packaging (dev and production)
- Tag-driven CI/CD with GitHub Actions (release artifacts, container images, checksums)
- Frontend/backend API contract pinned by a test
- Dashboard screenshots and Mermaid architecture diagrams in the README
- Demo recording showing a full pivot workflow

### Changed

- Rewrote the entire codebase from v2 to v3 (Django + React)
- Pivoting strategy pivots on what nmap actually finds rather than assuming ligolo routing
- Dashboard served as a proper production static build

### Fixed

- Tunnel health reporting: a tunnel that carried no traffic no longer reports as healthy
- CI settings-module import error
- Process-group test no longer assumes bash (works under dash/CI)
- Removed accidentally committed Playwright scratch files

### Removed

- v2 codebase (fully replaced by v3)
