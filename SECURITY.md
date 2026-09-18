# Security policy

## Supported versions

Only the latest Macast RTX Edition release is supported. The upstream Macast `v0.7` binaries and the retired workflow retained for historical reference are not supported by this fork.

## Reporting

Please use GitHub's private vulnerability reporting feature for `ccjjxx99/Macast-RTX-Edition` when available. Do not publish working exploit details in a public issue before a fix is ready.

Include:

- affected version and Windows version;
- whether the request originated locally or from another LAN device;
- minimal reproduction steps;
- relevant log lines with tokens, private URLs, and media addresses removed.

## Trust boundaries

- DLNA control traffic is accepted from the local network because that is required for a Media Renderer.
- The settings page, settings API, logs, and component inventory are restricted to loopback clients and use a per-process CSRF token.
- Plugin installation is only reachable from that same loopback-only settings session and additionally requires the CSRF token. Downloads are limited to `.py` files hosted in this repository's `plugins/` directory or the upstream `xfangfang/Macast-plugins` repository, size capped, and validated for `<macast.renderer>`/`<macast.protocol>` metadata before they are written to the plugin directory. No other URL is accepted, even if the settings page is compromised.
- Files in the local `renderer` or `protocol` plugin directory are executable Python code and have the same permissions as the application. Only install reviewed plugins from trusted sources.
- Cast media URLs may contain temporary tokens or private addresses. Logs and copied playback URLs should be treated as sensitive.
