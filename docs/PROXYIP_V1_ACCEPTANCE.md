# ProxyIP Optimizer V1 Acceptance

## V1 scope

- Lightweight Go backend with embedded native HTML/CSS/JavaScript UI; no Electron runtime.
- Glass-style local desktop Web interface.
- Candidate import from TXT/CSV or pasted `IP:port` data.
- SNI defaults blank; example text is placeholder-only.
- Host follows SNI by default and is only exposed in advanced settings.
- Fast / Standard / Precise modes.
- Repeated local TCP/TLS/HTTP probing from the machine running the program.
- HTTP/1.1 probe with actual SNI/Host/Path instead of fixed `speed.cloudflare.com` availability gating.
- Valid HTTP responses, including 4xx/5xx, are retained as chain evidence rather than hard-rejected.
- Missing `/cdn-cgi/trace` colo data is not a hard failure.
- Four result levels: excellent / usable / edge / failed.
- Precise-mode reference speed is ranking-only and does not change availability classification.
- Default listener is `127.0.0.1:13335`.
- Windows amd64 CI smoke build and Go regression tests.

## Required regression behavior

1. Blank SNI never silently falls back to a public test hostname; only TCP filtering is performed.
2. TCP/TLS reachable candidates are retained as edge candidates when HTTP probing is inconclusive.
3. HTTP 403 with Cloudflare response headers is valid evidence and is not discarded.
4. Multi-port candidate syntax and CSV input remain supported and deduplicated.
5. SNI/Host user values stay local in browser localStorage and are not committed as defaults.
6. UI disconnect or failed WebSocket send must restore the Start button instead of leaving the page stuck.
7. Startup does not perform geo, release, or speed-source network probes solely to render the local UI.

## Current automated checks

`ProxyIP Optimizer CI` verifies product markers and safe SNI defaults, runs `go test ./...`, cross-builds Windows amd64, and uploads a short-lived test EXE artifact.
