# Windows portable build

Extract the complete archive into a writable local directory and open
`openconnect-gui.exe`. Accept the normal administrator prompt to manage VPN routes.
This custom build uses its own profile settings, separate from upstream.

Use Servers > Import server list (JSON) with a local city/IP array, or create
profiles normally. Set the VPN username in the profile editor. Passwords can be
entered in the existing authentication dialog; leave Batch mode disabled to avoid
storing them. Verify the certificate when connecting to a server for the first time.

Enable Servers > Automatically select before connecting to choose a reachable
gateway by direct TCP latency. The manual probe dialog is also available. This
does not measure download speed or prove successful VPN authentication.

## Windows networking

This build supports direct AnyConnect/OpenConnect over TLS with IPv4 only. It
refuses an existing IPv6 default route or conflicting VPN/NRPT rules, rather than
silently providing incomplete coverage. Other VPN protocols and upstream proxy
profiles are not supported by this Windows routing backend.

The bundled standard Python runtime manages routing using ordinary Windows
network cmdlets; no cscript/wscript is invoked. It adds a specific route to the
selected gateway, IPv4 half-default routes for external traffic, and preserves
RFC1918 private networks and internal DNS suffixes on the original gateway.
It does not alter system proxy settings or security software.

Per-session route/DNS metadata is stored under
`%LOCALAPPDATA%/OpenConnect-GUI-Auto/network-state`. A separate Python watchdog
checks the GUI process identity and cleans the owned routes if the GUI exits.
Normal disconnection cleans routes immediately. No credentials are passed to the
network helper or stored in its state files.

The portable build includes Python 3.12.10 from python.org. Source and GPL notices
are in the repository. This custom build is not signed with upstream's certificate.
