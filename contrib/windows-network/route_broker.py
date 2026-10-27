# SPDX-License-Identifier: GPL-2.0-or-later
"""Privileged route lifecycle only; never accepts VPN credentials."""
import ipaddress
import json
import os
import sys
from vpn_network import Network, process_identity, recover_stale, watchdog


def main():
    action = sys.argv[1]
    if action == 'watchdog':
        watchdog(sys.argv[2])
        return
    request = json.load(sys.stdin)
    if action == 'prepare':
        owner = int(request['owner'])
        identity = process_identity(owner)
        if not identity:
            raise RuntimeError('GUI process is not running')
        recover_stale()
        network = Network.create()
        try:
            state = network.read()
            state['OwnerPid'], state['OwnerStart'] = owner, identity
            network.save(state)
            network.start_watchdog()
            print(json.dumps({'state': str(network.path)}))
        except BaseException:
            network.cleanup()
            raise
    elif action in ('configure', 'cleanup'):
        network = Network(request['state'])
        state = network.read()
        owner = int(request['owner'])
        if state['OwnerPid'] != owner or state['OwnerStart'] != process_identity(owner):
            raise RuntimeError('Session ownership mismatch')
        if action == 'configure':
            network.configure({'address':str(ipaddress.IPv4Address(request['address'])),
                               'gateway':str(ipaddress.IPv4Address(request['gateway']))})
        else:
            network.cleanup()
        print(json.dumps({'ok': True}))
    else:
        raise ValueError('Unknown action')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
