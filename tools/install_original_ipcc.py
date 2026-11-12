"""Install the fixed D73 Unicom 73.0 original through installation_proxy."""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib.util,json,plistlib,secrets,signal,sys,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
async def check_device(lockdown):
    spec=importlib.util.spec_from_file_location('installer_device_config',HERE/'device_config.py')
    config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)
    await config.check_lockdown(lockdown)
ORIGINAL_SHA256='54b8895eec8e815830d6587d6500fdd11a34c6ed4522b4490e74801435f845c6'
PREFIX='Payload/Unicom_cn.bundle/'
EXPECTED_FILES={'carrier.plist','Info.plist','overrides_D73_D74_D27_D28.der.pri','overrides_D73_D74_D27_D28.plist','signatures/common.plist','signatures/overrides_D73_D74_D27_D28.plist'}

def validate_package(path,expected_sha384=None):
    path=Path(path);raw=path.read_bytes()
    if path.suffix.lower()!='.ipcc':raise ValueError('原包必须为 .ipcc')
    if hashlib.sha256(raw).hexdigest()!=ORIGINAL_SHA256:raise ValueError('联通 14 Pro 原版 73.0 IPCC 校验失败')
    if expected_sha384 and hashlib.sha384(raw).hexdigest()!=expected_sha384:raise ValueError('原版 IPCC 与载荷清单不匹配')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError('IPCC 压缩包损坏')
        files={n[len(PREFIX):] for n in z.namelist() if n.startswith(PREFIX) and not n.endswith('/')}
        if files!=EXPECTED_FILES:raise ValueError('原包文件结构不符')
        if any(not n.startswith(PREFIX) and n!='Payload/' for n in z.namelist()):raise ValueError('IPCC 含联通包之外的内容')
        info=plistlib.loads(z.read(PREFIX+'Info.plist'))
        over=plistlib.loads(z.read(PREFIX+'overrides_D73_D74_D27_D28.plist'))
        if info.get('CFBundleIdentifier')!='com.apple.Unicom_cn' or info.get('CFBundleVersion')!='73.0':raise ValueError('运营商或版本不符')
        if over.get('DerPriFileVersion')!='5.0.161' or 'DataIndicatorOverrideForNRMmwave' in over:raise ValueError('IPCC 不是预期原版')
        if len(z.read(PREFIX+'overrides_D73_D74_D27_D28.der.pri'))!=13970:raise ValueError('原版 PRI 大小不符')
    return {'sha256':ORIGINAL_SHA256,'size':len(raw),'version':'73.0','model':'iPhone15,2 / D73','carrier':'com.apple.Unicom_cn'}

def load_writer():
    spec=importlib.util.spec_from_file_location('ipcc_writer_utils',HERE/'write_unicom.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

async def install_via_proxy(proxy,afc,package,remote,writer):
    """Use the SDK's IPCC uploader and native CarrierBundle install command."""
    install_error=None;cleanup_error=None
    try:
        await proxy.upload_ipcc_from_path(Path(package),remote,afc)
        await proxy.send_package('Install',{'PackageType':'CarrierBundle'},None,remote)
    except Exception as exc:install_error=exc
    finally:
        try:await writer.remove_media_tree(afc,remote.lstrip('/'),remote.lstrip('/'))
        except Exception as exc:cleanup_error=exc
    if install_error:raise RuntimeError('原版 IPCC 安装失败：'+str(install_error)) from install_error
    if cleanup_error:raise RuntimeError('IPCC 已安装，但上传暂存清理失败：'+str(cleanup_error)) from cleanup_error

async def verify_var_bundle(lockdown,udid,writer):
    """Check directory metadata only; never move/read the installed files."""
    air=writer.load_engine('0644');apple=air.AppleCF()
    async with air.AfcService(lockdown=lockdown) as afc:
        return await _verify_var_directories(air,apple,afc,lockdown,udid,writer)

async def _verify_var_directories(air,apple,afc,lockdown,udid,writer):
    active=[n for n in await afc.listdir('/') if n.startswith(('airlift-src-','airlift-link-'))]
    if active:raise RuntimeError('存在其他 Airlift 暂存操作，已停止后续写入')
    profiles={}
    for p in ('Books/Books.plist','Books/Sync/Books.plist'):
        profiles[p]=await afc.get_file_contents(p) if await writer.maybe_stat(afc,p) is not None else None
    token=secrets.token_hex(10);src='airlift-src-'+token;lnk='airlift-link-'+token
    checks={};cleanup_errors=[]
    try:
        ids=[f'../../{src}/p0/p1/p2/link']
        await air._stage(lockdown,afc,src,ids,'/var/mobile/Library/Carrier Bundles',b'')
        air._atc_sync(apple,udid,ids,[lnk])
        for rel in ('iPhone/Unicom_cn.bundle','iPhone/Unicom_cn.bundle/signatures'):
            info=await writer.maybe_stat(afc,lnk+'/'+rel)
            if not info or info.get('st_ifmt')!='S_IFDIR' or info.get('LinkTarget'):
                raise RuntimeError('安装后仍未确认联通目录存在：'+rel+'；未继续写 overlay/bundle')
            checks[rel]={'exists':True,'type':info['st_ifmt']}
    finally:
        for p in (lnk,src):
            try:await writer.remove_media_tree(afc,p,p)
            except Exception as exc:cleanup_errors.append(p+': '+str(exc))
        # Restore only these profiles. Never restore SQLite/WAL/SHM snapshots.
        for p,data in profiles.items():
            try:
                if data is not None:await afc.set_file_contents(p,data)
                elif await writer.maybe_stat(afc,p) is not None:await afc.rm_single(p)
            except Exception as exc:cleanup_errors.append(p+': '+str(exc))
        if cleanup_errors:raise RuntimeError('安装后的临时清理未完成：'+'; '.join(cleanup_errors))
    return checks

async def run_install(package,device,expected_sha384):
    validate_package(package,expected_sha384)
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    writer=load_writer();ld=await create_using_usbmux(serial=device)
    try:
        await check_device(ld)
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        remote='/PublicStaging/UnicomFastIPCC_'+secrets.token_hex(12)+'.ipcc'
        async with AfcService(lockdown=ld) as afc,InstallationProxyService(lockdown=ld) as proxy:
            info=await writer.maybe_stat(afc,'PublicStaging')
            if info and (info.get('st_ifmt')!='S_IFDIR' or info.get('LinkTarget')):raise RuntimeError('PublicStaging 路径类型异常，未安装')
            await install_via_proxy(proxy,afc,package,remote,writer)
        checked=await verify_var_bundle(ld,device,writer)
        return {'ok':True,'ipcc_installed':True,'version':'73.0','carrier':'com.apple.Unicom_cn','var_directories_verified':checked,'operator_files_readback':False,'staging_cleaned':True}
    finally:await ld.close()

async def run_verify_only(device):
    from pymobiledevice3.lockdown import create_using_usbmux
    writer=load_writer();ld=await create_using_usbmux(serial=device)
    try:
        await check_device(ld)
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        checked=await verify_var_bundle(ld,device,writer)
        return {'ok':True,'var_directories_verified':checked,'ipcc_installed':False,'operator_files_readback':False,'staging_cleaned':True}
    finally:await ld.close()

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--package')
    parser.add_argument('--device')
    parser.add_argument('--sha384')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--check',action='store_true')
    group.add_argument('--verify-only',action='store_true')
    args=parser.parse_args(argv)
    try:
        if not args.verify_only and not args.package:raise ValueError('缺少原版 IPCC 路径')
        if args.check:
            result={'ok':True,'package':validate_package(args.package,args.sha384),'device_connected':False}
        else:
            if not args.device:raise ValueError('缺少绑定设备标识')
            result=asyncio.run(run_verify_only(args.device) if args.verify_only else run_install(args.package,args.device,args.sha384))
        print(json.dumps(result,ensure_ascii=False),flush=True);return 0
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
