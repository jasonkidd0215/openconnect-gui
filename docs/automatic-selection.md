# Automatic server selection

This fork tracks the current GitLab upstream `main`, retaining its history and
the GitHub fork relationship to the archived repository.

Create VPN profiles normally. In **Servers**, enable **Automatically select
before connecting**. Each press of Connect probes the saved direct gateways,
selects the lowest measured TCP connection latency and enters the existing
certificate/authentication flow for that profile. The preference defaults off.

**Servers > Probe and choose server** displays probe results and lets you choose
a reachable profile manually. With automatic selection off, the original profile
dropdown and Connect button behave as before.

Probing is asynchronous, limited to six simultaneous sockets, with a three-second
deadline per gateway. Cancel closes probes and does not start a VPN. Probes send
no application payload or credentials. Profiles configured to use a proxy are
excluded because direct reachability would not measure their actual path.

TCP reachability does not prove TLS identity, successful authentication, Internet
access, or download speed. Certificate verification remains in the existing VPN
connection path. The selector does not trust certificates, migrate credentials
between profiles, retry another profile after an authentication error, or switch
a working connection in the background. Existing upstream authentication behavior
within the chosen profile is unchanged.

No provider membership data or private server inventory is included in this fork.

## Validation

GitHub Actions builds the complete application on Ubuntu and runs local-loopback
Qt tests for profile filtering, unreachable servers, payload-free probes,
cancellation, and bounded multi-batch completion.

This is a source-level feature branch, not a tested Windows VPN release. Windows
upstream still uses its `vpnc-script.js` route helper; this feature does not fix
endpoint-protection compatibility or promise the custom Python launcher's private
network routing behavior. Those require separate Windows integration validation
before replacing a working client.
