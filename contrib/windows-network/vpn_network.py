import contextlib
import ctypes
import json
import ipaddress
import msvcrt
import os
import random
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'OpenConnect-GUI-Auto' / 'network-state'
POWERSHELL = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
PREFIX = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "

CONTEXT_COMMAND = r"""
$routes = @(Get-NetRoute -AddressFamily IPv4)
if (@($routes | Where-Object DestinationPrefix -in '0.0.0.0/1','128.0.0.0/1').Count) { throw '另一个全局 VPN 正在使用分流路由，请先断开它。' }
if (@(Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0' -ErrorAction SilentlyContinue).Count) { throw '本开关只接管 IPv4，检测到 IPv6 默认出口，暂不连接。' }
$interfaces = @(Get-NetIPInterface -AddressFamily IPv4)
$route = $routes | Where-Object DestinationPrefix -eq '0.0.0.0/0' | Sort-Object {
    $candidate = $_
    $interface = $interfaces | Where-Object InterfaceIndex -eq $candidate.InterfaceIndex | Select-Object -First 1
    [int]$candidate.RouteMetric + [int]$interface.InterfaceMetric
} | Select-Object -First 1
if (-not $route -or $route.NextHop -eq '0.0.0.0') { throw '没有可保留的办公默认网关。' }
$adapter = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex
$dns = @((Get-DnsClientServerAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4).ServerAddresses)
$suffixes = @((Get-DnsClientGlobalSetting).SuffixSearchList)
$suffixes += @(Get-DnsClient | Where-Object ConnectionSpecificSuffix | ForEach-Object ConnectionSpecificSuffix)
if ($env:USERDNSDOMAIN) { $suffixes += $env:USERDNSDOMAIN }
$suffixes = @($suffixes | Where-Object { $_ -and $_ -match '^[a-zA-Z0-9.-]+$' } | ForEach-Object { $_.Trim('.') } | Select-Object -Unique)
$namespaces = @('.') + @($suffixes | ForEach-Object { '.' + $_ })
if (@(Get-DnsClientNrptRule | Where-Object { @($_.Namespace | Where-Object { $_ -in $namespaces }).Count }).Count) { throw '已有 DNS 分流规则冲突，不自动覆盖。' }
if (Get-NetAdapter -Name 'KABENEKO-VPN' -ErrorAction SilentlyContinue) { throw '同名 VPN 网卡已存在，不接管其他连接。' }
[pscustomobject]@{InterfaceIndex=$route.InterfaceIndex;InterfaceGuid=[string]$adapter.InterfaceGuid;NextHop=[string]$route.NextHop;DnsServers=$dns;InternalSuffixes=$suffixes} | ConvertTo-Json -Depth 5 -Compress
"""

CONFIGURE_COMMAND = r"""
$path = $env:KABENEKO_NETWORK_STATE
$state = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
function Save {
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath ($path + '.tmp') -Encoding UTF8
    Move-Item -LiteralPath ($path + '.tmp') -Destination $path -Force
}
function Add-Route($prefix,$index,$guid,$nextHop,$skipExisting) {
    $existing = @(Get-NetRoute -DestinationPrefix $prefix -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    if ($skipExisting -and $existing.Count) { return }
    if (@($existing | Where-Object { $_.InterfaceIndex -eq $index -and $_.NextHop -eq $nextHop }).Count) { return }
    $state.Routes = @($state.Routes) + @([pscustomobject]@{Prefix=$prefix;InterfaceIndex=$index;InterfaceGuid=$guid;NextHop=$nextHop})
    Save
    New-NetRoute -DestinationPrefix $prefix -InterfaceIndex $index -NextHop $nextHop -RouteMetric $state.RouteMetric -PolicyStore ActiveStore | Out-Null
}
$adapter = Get-NetAdapter -Name 'KABENEKO-VPN' -ErrorAction Stop
if ($adapter.InterfaceDescription -ne 'OpenConnect Tunnel') { throw 'VPN 网卡身份不符，拒绝修改。' }
$state.TunnelIndex = $adapter.ifIndex
$state.TunnelGuid = [string]$adapter.InterfaceGuid
Save
Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Dhcp Disabled -NlMtuBytes 1280 -InterfaceMetric 10 -PolicyStore ActiveStore
New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $state.TunnelAddress -PrefixLength 32 -PolicyStore ActiveStore | Out-Null
Add-Route ($state.Gateway + '/32') $state.Network.InterfaceIndex $state.Network.InterfaceGuid $state.Network.NextHop $false
foreach ($prefix in '10.0.0.0/8','172.16.0.0/12','192.168.0.0/16') {
    Add-Route $prefix $state.Network.InterfaceIndex $state.Network.InterfaceGuid $state.Network.NextHop $true
}
foreach ($prefix in '0.0.0.0/1','128.0.0.0/1') {
    Add-Route $prefix $adapter.ifIndex $state.TunnelGuid '0.0.0.0' $false
}
$tag = 'KABENEKO-Python:' + $state.SessionId
foreach ($suffix in @($state.Network.InternalSuffixes)) {
    if (@($state.Network.DnsServers).Count) {
        Add-DnsClientNrptRule -Namespace ('.' + $suffix) -NameServers $state.Network.DnsServers -DisplayName $tag -Comment $tag | Out-Null
    }
}
Add-DnsClientNrptRule -Namespace '.' -NameServers @('1.1.1.1','8.8.8.8') -DisplayName $tag -Comment $tag | Out-Null
Clear-DnsClientCache
$ready = $false
for ($attempt=0; $attempt -lt 20; $attempt++) {
    if ((Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $state.TunnelAddress).AddressState -eq 'Preferred') { $ready=$true; break }
    Start-Sleep -Milliseconds 250
}
if (-not $ready) { throw 'VPN 地址未就绪。' }
$state.Phase = 'Connected'
Save
'NETWORK_READY'
"""

CLEANUP_COMMAND = r"""
$path = $env:KABENEKO_NETWORK_STATE
$state = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
$tag = 'KABENEKO-Python:' + $state.SessionId
Get-DnsClientNrptRule | Where-Object Comment -eq $tag | Remove-DnsClientNrptRule -Force
foreach ($route in @($state.Routes)) {
    $gateway = if ($state.Gateway) { ([ipaddress]$state.Gateway).ToString() } else { '160.16.98.79' }
    if ($route.Prefix -notin @(($gateway + '/32'),'10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','0.0.0.0/1','128.0.0.0/1')) { throw '清理状态中包含未知路由，拒绝操作。' }
    $adapter = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue
    if ($adapter -and [string]$adapter.InterfaceGuid -eq [string]$route.InterfaceGuid) {
        Get-NetRoute -InterfaceIndex $route.InterfaceIndex -DestinationPrefix $route.Prefix -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.NextHop -eq $route.NextHop -and $_.RouteMetric -eq $state.RouteMetric } |
            Remove-NetRoute -Confirm:$false
    }
}
$state.Phase = 'Disconnected'
$state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath ($path + '.tmp') -Encoding UTF8
Move-Item -LiteralPath ($path + '.tmp') -Destination $path -Force
Clear-DnsClientCache
'NETWORK_RESTORED'
"""


def powershell(command, state_path=None):
    environment = dict(os.environ)
    environment.pop("PSExecutionPolicyPreference", None)
    if state_path:
        environment["KABENEKO_NETWORK_STATE"] = str(state_path)
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", PREFIX + command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=60,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Windows 网络命令失败 ({result.returncode})")
    return result.stdout.strip()


def process_identity(process_id):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.GetProcessTimes.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    ]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, process_id)
    if not handle:
        if ctypes.get_last_error() == 5:
            raise PermissionError("无法核对 VPN 控制进程身份。")
        return None
    try:
        creation, exit_time, kernel_time, user_time = (ctypes.c_ulonglong() for _ in range(4))
        if not kernel.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel_time), ctypes.byref(user_time)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if exit_time.value:
            return None
        return creation.value
    finally:
        kernel.CloseHandle(handle)


class Network:
    def __init__(self, state_path):
        self.path = Path(state_path).resolve()
        expected_root = RUNTIME.resolve()
        if self.path.parent.parent != expected_root or self.path.name != "state.json":
            raise ValueError("Invalid network session path")
        uuid.UUID(self.path.parent.name)

    @classmethod
    def create(cls):
        context = json.loads(powershell(CONTEXT_COMMAND))
        session_id = str(uuid.uuid4())
        directory = RUNTIME / session_id
        directory.mkdir(parents=True)
        instance = cls(directory / "state.json")
        instance.save({
            "SessionId": session_id, "Phase": "Connecting",
            "OwnerPid": os.getpid(), "OwnerStart": process_identity(os.getpid()),
            "Network": context, "Routes": [], "RouteMetric": random.randrange(3000, 8000),
            "TunnelAddress": "", "TunnelGuid": "", "TunnelIndex": 0,
        })
        return instance

    def read(self):
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if data["SessionId"] != self.path.parent.name:
            raise ValueError("Invalid session identity")
        return data

    def save(self, data):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @contextlib.contextmanager
    def lock(self):
        with self.path.with_suffix(".lock").open("a+b") as lock_file:
            lock_file.seek(0, 2)
            if not lock_file.tell():
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

    def configure(self, details):
        with self.lock():
            data = self.read()
            data["TunnelAddress"] = details["address"]
            data["Gateway"] = str(ipaddress.IPv4Address(details['gateway']))
            self.save(data)
            powershell(CONFIGURE_COMMAND, self.path)

    def cleanup(self):
        with self.lock():
            if self.read()["Phase"] != "Disconnected":
                powershell(CLEANUP_COMMAND, self.path)

    def start_watchdog(self):
        import sys

        process = subprocess.Popen(
            [sys.executable, str(ROOT / "route_broker.py"), "watchdog", str(self.path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        deadline = time.monotonic() + 8
        while not self.path.with_suffix(".ready").exists():
            if process.poll() is not None:
                raise RuntimeError("自动清理程序未启动，未连接 VPN。")
            if time.monotonic() > deadline:
                raise RuntimeError("自动清理程序没有就绪，未连接 VPN。")
            time.sleep(0.1)


def watchdog(state_path):
    network = Network(state_path)
    data = network.read()
    network.path.with_suffix(".ready").write_text("ready", encoding="ascii")
    try:
        while process_identity(data["OwnerPid"]) == data["OwnerStart"]:
            if network.read()["Phase"] == "Disconnected":
                return
            time.sleep(1)
        network.cleanup()
    except Exception as error:
        network.path.with_suffix(".error.txt").write_text(str(error), encoding="utf-8")


def recover_stale():
    if not RUNTIME.exists():
        return
    for state_path in RUNTIME.glob("*/state.json"):
        network = Network(state_path)
        data = network.read()
        if data["Phase"] == "Disconnected":
            continue
        if process_identity(data["OwnerPid"]) == data["OwnerStart"]:
            raise RuntimeError("VPN 开关已在另一个窗口运行，请使用已有窗口。")
        network.cleanup()
