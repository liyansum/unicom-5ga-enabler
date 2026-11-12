"""Merged Unicom recovery and independent debug actions. No target readback."""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib.util,json,msvcrt,os,plistlib,subprocess,sys
from datetime import datetime
from pathlib import Path

HERE=Path(__file__).resolve().parent
DEVICE=None  # Selected for the current operation; never saved to configuration.
OV='/var/mobile/Library/Carrier Bundles/Overlay'
BUNDLE='/var/mobile/Library/Carrier Bundles/iPhone/Unicom_cn.bundle'
IPCC_NAME='Unicom_cn_73.0_original.ipcc'
TRAVERSAL='../'*6+'var/mobile/Library/Carrier Bundles/iPhone/Unicom_cn.bundle/overrides_D73_D74_D27_D28.der.pri'
JOBS={
    'bundle_pri':('unicom.der.pri',BUNDLE+'/overrides_D73_D74_D27_D28.der.pri','0644'),
    'bundle_plist':('unicom_overrides.plist',BUNDLE+'/overrides_D73_D74_D27_D28.plist','0644'),
    'bundle_signature':('unicom_signature.plist',BUNDLE+'/signatures/overrides_D73_D74_D27_D28.plist','0644'),
    'bundle_carrier':('unicom_carrier.plist',BUNDLE+'/carrier.plist','0600'),
    'bundle_common_signature':('unicom_common_signature.plist',BUNDLE+'/signatures/common.plist','0600'),
    'bundle_info':('unicom_Info.plist',BUNDLE+'/Info.plist','0600'),
    'overlay_7201':('unicom_72.0.1.plist',OV+'/device+carrier+46001+D73+72.0.1.plist','0555'),
    'overlay_730':('unicom_73.0.plist',OV+'/device+carrier+46001+D73+73.0.plist','0555'),
}
BUNDLE_644=['bundle_pri','bundle_plist','bundle_signature']
BUNDLE_600=['bundle_carrier','bundle_common_signature','bundle_info']
OVERLAYS=['overlay_7201','overlay_730']
AFTER_RELOAD={'overlay_7201_after_reload':'overlay_7201','overlay_730_after_reload':'overlay_730'}
PLANS={
    'full':['install_ipcc',*BUNDLE_644,*BUNDLE_600,*OVERLAYS,'reload_commcenter',*AFTER_RELOAD],
    'normal':[*OVERLAYS,'reload_commcenter',*AFTER_RELOAD],
    'debug_ipcc':['install_ipcc'],
    'debug_bundle':['check_bundle_directory',*BUNDLE_644],
    'debug_aux':['check_bundle_directory',*BUNDLE_600],
    'debug_overlay':list(OVERLAYS),
    'debug_reload':['reload_commcenter'],
}
MODE_LABELS={
    'full':'完整模式','normal':'普通模式','debug_ipcc':'调试：加载原版 73.0 IPCC',
    'debug_bundle':'调试：三件套写入 0644','debug_aux':'调试：其他 bundle 文件写入 0600',
    'debug_overlay':'调试：修改后的 overlay 写入 0555','debug_reload':'调试：重载 CommCenter',
    'check':'本地环境检查',
}
STEP_LABELS={
    'install_ipcc':'加载联通 14 Pro 原版 73.0 IPCC，并确认 /var 目录',
    'check_bundle_directory':'检查 /var 联通目录（不安装 IPCC，不回读目标文件）',
    'bundle_pri':'写入 PRI（0644）','bundle_plist':'写入 overrides（0644）',
    'bundle_signature':'写入 PRI 签名（0644）','bundle_carrier':'重新写入 carrier.plist（0600）',
    'bundle_common_signature':'重新写入 signatures/common.plist（0600）',
    'bundle_info':'重新写入 Info.plist（0600）','overlay_7201':'写入 72.0.1 overlay（0555）',
    'overlay_730':'写入 73.0 overlay（0555）',
    'reload_commcenter':'重载 CommCenter（先等 5 秒，新进程持续运行 15 秒）',
    'overlay_7201_after_reload':'重载后补写 72.0.1 overlay（0555）',
    'overlay_730_after_reload':'重载后补写 73.0 overlay（0555）',
}

def selected(mode):
    if mode not in PLANS:raise ValueError('未知模式或调试操作')
    return list(PLANS[mode])

def needs_ipcc(mode):return mode!='check' and 'install_ipcc' in selected(mode)

def validate(mode='check'):
    meta=json.loads((HERE/'payloads.json').read_text(encoding='utf8'))
    steps=selected(mode) if mode!='check' else list(JOBS)
    keys=list(dict.fromkeys(AFTER_RELOAD.get(step,step) for step in steps if step in JOBS or step in AFTER_RELOAD))
    for key in keys:
        name,_,payload_mode=JOBS[key];raw=(HERE/'payloads'/name).read_bytes();entry=meta[name]
        if len(raw)!=entry['size'] or hashlib.sha384(raw).hexdigest()!=entry['sha384']:raise ValueError('载荷校验失败：'+name)
        if payload_mode not in ('0555','0600','0644'):raise ValueError('权限配置异常')
    expected={'DataIndicatorOverrideForNRMmwave':'NRCA','DerPriFileName':TRAVERSAL,'DerPriFileVersion':'6.0.161','Show5GStandaloneSwitch':True,'ShowVoNRSwitch':True}
    for key in OVERLAYS:
        if key not in keys:continue
        name=JOBS[key][0];data=plistlib.loads((HERE/'payloads'/name).read_bytes())
        for field,value in expected.items():
            if data.get(field)!=value or type(data.get(field)) is not type(value):raise ValueError(name+' 参数异常：'+field)
        if 'DataIndicatorOverrideForLTE' in data:raise ValueError(name+' 仍保留 LTE 映射')
    if 'bundle_pri' in keys:
        pri=(HERE/'payloads/unicom.der.pri').read_bytes()
        if len(pri)!=14801 or hashlib.sha384(pri).hexdigest()!='6bec2675e57b65327b396c0306f80e60e434552c4de52aed79174b0cd58ecdc8199a223b726e90610b3a7383ec4d7524':raise ValueError('联通官方目标 PRI 不匹配')
    if keys or needs_ipcc(mode) or mode=='check':
        if hashlib.sha384((HERE/'tools/airlift_engine.py').read_bytes()).hexdigest()!=(HERE/'tools/engine.sha384').read_text().strip():raise ValueError('Airlift 引擎校验失败')
    if needs_ipcc(mode) or mode=='check':
        package=HERE/'payloads'/IPCC_NAME;entry=meta[IPCC_NAME]
        if package.stat().st_size!=entry['size']:raise ValueError('原版 IPCC 大小不符')
        spec=importlib.util.spec_from_file_location('ipcc_validation',HERE/'tools/install_original_ipcc.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        installer.validate_package(package,entry['sha384'])
    return meta

def helper_args(name,*args):
    return [sys.executable,'-I','-X','utf8','-u',str(HERE/'tools'/name),*args]

def current_device():
    if not DEVICE:raise RuntimeError('尚未选择设备，未开始手机操作。')
    return DEVICE

def select_device():
    spec=importlib.util.spec_from_file_location('public_device_config',HERE/'tools/device_config.py')
    config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)
    return asyncio.run(config.choose_device())

def install_args(meta):
    return helper_args('install_original_ipcc.py','--package',str(HERE/'payloads'/IPCC_NAME),'--sha384',meta[IPCC_NAME]['sha384'],'--device',current_device())

def reload_args():return helper_args('reload_commcenter.py','--device',current_device())

def worker_args(key,meta,run_id,label=None):
    name,path,mode=JOBS[key]
    return helper_args('write_unicom.py','--path',path,'--payload',str(HERE/'payloads'/name),'--mode',mode,
                       '--sha384',meta[name]['sha384'],'--device',current_device(),'--run-id',run_id,'--label',label or key)

def worker_env(mode):
    env=dict(os.environ);env['AIRLIFT_PAYLOAD_MODE']=mode;env.pop('AIRLIFT_PAYLOAD_DIR',None);env['MSYS_NO_PATHCONV']='1'
    return env

def invoke(args,env,log):
    interrupted=False;last=None
    with subprocess.Popen(args,cwd=HERE,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace') as proc:
        while True:
            try:
                line=proc.stdout.readline()
                if not line:break
                if DEVICE:line=line.replace(DEVICE,'<device>')
                log.write(line);log.flush()
                try:
                    last=json.loads(line)
                    if isinstance(last,dict) and isinstance(last.get('progress'),str):print(last['progress'],flush=True)
                except ValueError:pass
            except KeyboardInterrupt:
                interrupted=True;print('\n收到中断。等待当前步骤收尾，不再执行后续步骤。',flush=True)
        code=proc.wait()
    if interrupted:return False
    ok=code==0 and isinstance(last,dict) and last.get('ok') is True
    if not ok:print('失败：'+(str(last.get('error')) if isinstance(last,dict) and last.get('error') else '详情见本次日志。'),flush=True)
    return ok

def execute(mode,meta,run_id,run_one):
    for step in selected(mode):
        if step=='install_ipcc':cmd=install_args(meta);env=worker_env('0644')
        elif step=='reload_commcenter':cmd=reload_args();env=worker_env('0644')
        elif step=='check_bundle_directory':
            cmd=helper_args('install_original_ipcc.py','--verify-only','--device',current_device());env=worker_env('0644')
        else:
            key=AFTER_RELOAD.get(step,step)
            # Every file is written even when its bytes match an existing version.
            # This is necessary to establish the requested 0600 permission.
            cmd=worker_args(key,meta,run_id,step);env=worker_env(JOBS[key][2])
        if not run_one(step,cmd,env):return False
    return True

def preflight(mode,log):
    steps=selected(mode) if mode!='check' else [*JOBS,'install_ipcc','reload_commcenter']
    if any(step!='reload_commcenter' for step in steps):
        if not invoke(helper_args('write_unicom.py','--check'),worker_env('0555'),log):raise RuntimeError('写入组件本地检查失败；尚未开始手机操作。')
    if 'reload_commcenter' in steps:
        if not invoke(helper_args('reload_commcenter.py','--check'),worker_env('0644'),log):raise RuntimeError('进程控制组件本地检查失败；尚未开始手机操作。')

def run_mode(mode):
    global DEVICE
    (HERE/'logs').mkdir(exist_ok=True);lock=None;locked=False
    try:
        if mode!='check':
            lock=(HERE/'logs/.restore.lock').open('a+b')
            if lock.tell()==0:lock.write(b'0');lock.flush()
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);locked=True
            except OSError:print('已有恢复或调试操作在运行，请等待结束。',flush=True);return 1
        run_id=datetime.now().strftime('%Y%m%d_%H%M%S_%f');log_path=HERE/'logs'/(run_id+'_'+mode+'.log')
        with log_path.open('w',encoding='utf8') as log:
            def say(message):print(message,flush=True);log.write(message+'\n');log.flush()
            try:
                say('开启5GA | '+MODE_LABELS[mode]);say('不回读目标文件，不处理移动文件。')
                meta=validate(mode);preflight(mode,log)
                if mode=='check':say('环境和载荷检查通过，未连接手机。');return 0
                DEVICE=select_device()
                say('已选择符合配置的 USB 设备；设备标识仅用于本次操作。')
                if mode=='full':say('三件套：0644；其他 bundle 三个文件：0600；两个 overlay：0555。')
                elif mode=='normal':say('普通模式：写两个 overlay（0555），重载一次 CommCenter，再补写两个 overlay（0555）。')
                elif mode.startswith('debug_'):say('仅执行本项调试操作，不自动串联其他项目。')
                count=0;total=len(selected(mode))
                def run_one(step,cmd,env):
                    nonlocal count
                    count+=1;say(f'[{count}/{total}] '+STEP_LABELS[step]);return invoke(cmd,env,log)
                if not execute(mode,meta,run_id,run_one):raise RuntimeError('本次操作未全部完成，已停止后续步骤。')
                say('本次操作步骤已结束。')
                if mode=='full':say('已完成 0644 / 0600 / 0555 写入、重载，以及重载后的两个 overlay 补写。')
                elif mode=='normal':say('已写入两个 overlay、完成 CommCenter 重载，并补写两个 overlay。')
                if any(step in JOBS or step in AFTER_RELOAD for step in selected(mode)):
                    say('写入按本地载荷与 ZIP 权限执行；未回读核实目标内容、实际权限或网络效果。')
                return 0
            except Exception as exc:say('失败：'+str(exc));return 1
            except KeyboardInterrupt:say('已中断，不再执行后续步骤。');return 130
            finally:say('日志：'+str(log_path))
    finally:
        DEVICE=None
        if locked:
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
        if lock:lock.close()

def interactive():
    debugging=False
    main_choices={'1':'full','2':'normal'}
    debug_choices={'1':'debug_ipcc','2':'debug_bundle','3':'debug_aux','4':'debug_overlay','5':'debug_reload'}
    while True:
        if debugging:
            print('\n开启5GA - 调试模式\n\n1. 加载原版 73.0 IPCC（iPhone 14 Pro）\n2. 以 0644 写入 bundle 三件套\n3. 以 0600 写入 bundle 其他三个文件\n4. 以 0555 写入修改后的两个 overlay\n5. 重载 CommCenter\n0. 返回模式选择\n\n备注：每次只执行所选调试操作，不自动串联其他项目。\n')
            choice=input('请选择 [1/2/3/4/5/0]：').strip()
            if choice=='0':debugging=False;continue
            mode=debug_choices.get(choice)
        else:
            print('\n开启5GA\n\n模式选择\n1. 完整模式（首次打开执行一次即可）\n2. 普通模式（手机重启后需要执行一次保持效果）\n3. 调试模式\n0. 退出\n\n备注：首次使用仅需执行一次完整模式；以后每次手机重启后，执行一次普通模式即可保持效果。如需恢复原版，请在调试模式中加载原版 73.0 IPCC，然后手动重启手机。本工具仅适用于 iPhone 14 Pro / iOS 27.0.1 / 中国联通，其他机型、系统版本或运营商请勿直接混用；如需适配，请按实际机型、系统版本和运营商修改配置。\n')
            choice=input('请选择 [1/2/3/0]：').strip()
            if choice=='0':return 0
            if choice=='3':debugging=True;continue
            mode=main_choices.get(choice)
        if mode:run_mode(mode)
        else:print('请输入菜单中列出的选项。')

def main(argv=None):
    parser=argparse.ArgumentParser(description='开启5GA：完整模式、普通模式和五项独立调试')
    parser.add_argument('mode',nargs='?',choices=(*PLANS,'check'))
    args=parser.parse_args(argv)
    if args.mode:return run_mode(args.mode)
    try:return interactive()
    except (KeyboardInterrupt,EOFError):return 0

if __name__=='__main__':raise SystemExit(main())
