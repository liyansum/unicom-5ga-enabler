"""Signal only the exact CommCenter executable, then wait for a stable new PID."""
from __future__ import annotations
import argparse,asyncio,importlib.util,json,signal,time
from pathlib import Path
from urllib.parse import unquote,urlsplit

COMM_CENTER='/System/Library/Frameworks/CoreTelephony.framework/Support/CommCenter'
PRE_KILL_SECONDS=5
STABLE_SECONDS=15
RELOAD_TIMEOUT=90
POLL_SECONDS=1
CALL_TIMEOUT=10

def progress(message):
    print(json.dumps({'progress':message},ensure_ascii=False),flush=True)

def commcenter_pid(processes):
    matches=[]
    for proc in processes:
        raw=proc.get('executableURL')
        if isinstance(raw,dict):raw=raw.get('relative')
        if not isinstance(raw,str):continue
        url=urlsplit(raw)
        if url.scheme not in ('','file') or url.netloc not in ('','localhost') or url.query or url.fragment:continue
        if unquote(url.path)!=COMM_CENTER:continue
        pid=proc.get('processIdentifier')
        if isinstance(pid,bool) or not isinstance(pid,int) or pid<=1:raise RuntimeError('CommCenter 进程号异常，停止操作')
        matches.append(pid)
    if len(matches)>1:raise RuntimeError('CommCenter 匹配不唯一，停止操作')
    return matches[0] if matches else None

async def query_pid(service):
    return commcenter_pid(await asyncio.wait_for(service.list_processes(),CALL_TIMEOUT))

async def reload_only(service,*,sleep=asyncio.sleep,monotonic=time.monotonic):
    if await query_pid(service) is None:raise RuntimeError('未找到 CommCenter，未结束任何进程')
    progress(f'等待 {PRE_KILL_SECONDS} 秒后重载 CommCenter。')
    await sleep(PRE_KILL_SECONDS)
    old_pid=await query_pid(service)
    if old_pid is None:raise RuntimeError('CommCenter 状态变化，未结束任何进程')
    progress(f'仅结束 CommCenter（PID {old_pid}），等待系统重新拉起。')
    # One request only. Never retry a signal against either the old or a new PID.
    await asyncio.wait_for(service.send_signal_to_process(old_pid,9),CALL_TIMEOUT)
    started=monotonic();deadline=started+RELOAD_TIMEOUT
    new_pid=None;stable_since=None
    while monotonic()<deadline:
        current=await query_pid(service);now=monotonic()
        if current is None or current==old_pid:
            new_pid=None;stable_since=None
        elif current!=new_pid:
            new_pid=current;stable_since=now
            progress(f'CommCenter 已重新出现（PID {new_pid}），继续观察 {STABLE_SECONDS} 秒。')
        elif now-stable_since>=STABLE_SECONDS and now<deadline:
            progress('CommCenter 新进程已持续运行，重载步骤结束。')
            return {'ok':True,'process':'CommCenter','signal':9,'old_pid':old_pid,'new_pid':new_pid,
                    'pre_kill_wait_seconds':PRE_KILL_SECONDS,'stable_seconds':STABLE_SECONDS,
                    'elapsed_after_signal_seconds':round(now-started,2),'kill_requests':1}
        remaining=deadline-monotonic()
        if remaining>0:await sleep(min(POLL_SECONDS,remaining))
    raise RuntimeError(f'{RELOAD_TIMEOUT} 秒内未确认 CommCenter 新进程持续运行 {STABLE_SECONDS} 秒；停止后续步骤，不再次结束进程')

def check():
    from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel
    from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
    from pymobiledevice3.remote.core_device.app_service import AppServiceService
    return {'ok':True,'check':'CommCenter CoreDevice signal and userspace transport imports','device_connected':False}

async def run_reload(device):
    from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel
    from pymobiledevice3.remote.core_device.app_service import AppServiceService
    progress('正在连接 CommCenter 进程控制接口。')
    async with PreferredRsdTunnel(serial=device,autopair=False) as rsd:
        if rsd.udid!=device:raise RuntimeError('设备不匹配，未结束任何进程')
        spec=importlib.util.spec_from_file_location('reload_device_config',Path(__file__).parent/'device_config.py')
        config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)
        config.require_supported(rsd.product_type,rsd.product_version,rsd.product_build_version)
        async with AppServiceService(rsd) as service:
            # Finish this one in-flight step if the parent receives Ctrl+C.
            signal.signal(signal.SIGINT,signal.SIG_IGN)
            return await reload_only(service)

async def bounded_reload(device):
    async with asyncio.timeout(180):return await run_reload(device)

def main(argv=None):
    parser=argparse.ArgumentParser(description='Only kill CommCenter once and wait for its new PID')
    parser.add_argument('--device')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.check:result=check()
        else:
            if not args.device:raise ValueError('缺少绑定设备标识')
            result=asyncio.run(bounded_reload(args.device))
        print(json.dumps(result,ensure_ascii=False),flush=True);return 0
    except Exception as exc:
        detail=str(exc) or type(exc).__name__
        print(json.dumps({'ok':False,'error':'CommCenter 重载未确认完成，已停止后续步骤：'+detail},ensure_ascii=False),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
