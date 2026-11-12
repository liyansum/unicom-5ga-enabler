"""Write-only Airlift adapter. Never calls read_file/replace_file or reads old targets."""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib.util,inspect,io,json,os,posixpath,secrets,signal,stat,sys,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
def check_device(dev):
    spec=importlib.util.spec_from_file_location('writer_device_config',HERE/'device_config.py')
    config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)
    config.require_supported(dev['product'],dev['version'],dev['build'])
OV='/var/mobile/Library/Carrier Bundles/Overlay'
BUNDLE='/var/mobile/Library/Carrier Bundles/iPhone/Unicom_cn.bundle'
ALLOWED={OV+'/device+carrier+46001+D73+72.0.1.plist':'0555',OV+'/device+carrier+46001+D73+73.0.plist':'0555',
         BUNDLE+'/overrides_D73_D74_D27_D28.der.pri':'0644',BUNDLE+'/overrides_D73_D74_D27_D28.plist':'0644',BUNDLE+'/signatures/overrides_D73_D74_D27_D28.plist':'0644',
         BUNDLE+'/Info.plist':'0600',BUNDLE+'/carrier.plist':'0600',BUNDLE+'/signatures/common.plist':'0600'}

def load_engine(mode):
    if mode not in ('0555','0600','0644'):raise ValueError('只允许 0555 / 0600 / 0644')
    os.environ['AIRLIFT_PAYLOAD_MODE']=mode
    os.environ.pop('AIRLIFT_PAYLOAD_DIR',None)
    from pymobiledevice3.services.afc import AfcService
    for name in ('connect','get_file_contents','set_file_contents','listdir','makedirs','rm','rm_single','stat','rename','exists','isdir'):
        fn=getattr(AfcService,name,None)
        if not fn or getattr(fn,'_unicom_shim',False):continue
        def wrap(fn):
            async def wrapped(self,*a,**kw):
                r=fn(self,*a,**kw)
                while inspect.isawaitable(r):r=await r
                return r
            wrapped._unicom_shim=True
            return wrapped
        setattr(AfcService,name,wrap(fn))
    spec=importlib.util.spec_from_file_location('unicom_airlift_engine',HERE/'airlift_engine.py')
    air=importlib.util.module_from_spec(spec);spec.loader.exec_module(air)
    air._logging=True
    return air

def validate_archive(air,path,data,mode):
    archive=air._build_archive(posixpath.dirname(path),data)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        entry=z.getinfo('payload')
        actual=(entry.external_attr>>16)&0xffff
        if actual!=(stat.S_IFREG|int(mode,8)):raise ValueError('ZIP 载荷权限校验失败')
        if z.read('payload')!=data:raise ValueError('ZIP 载荷内容校验失败')
        extra=entry.extra
        if extra!=__import__('struct').pack('<HHH',air.SZ_EXTRA_ID,2,actual):raise ValueError('ZIP 权限扩展字段异常')

async def maybe_stat(afc,path):
    from pymobiledevice3.exceptions import AfcException
    try:return await afc.stat(path)
    except AfcException as exc:
        if exc.status in (4,8):return None
        raise

async def remove_media_tree(afc,path,root):
    """Unlink Media entries one at a time. NEVER recurse through a symlink."""
    for value in (path,root):
        if not value or value.startswith('/') or '\\' in value or any(p in ('','.','..') for p in value.split('/')):
            raise ValueError('清理路径必须位于 Media 的指定相对目录内')
    if path!=root and not path.startswith(root+'/'):raise ValueError('清理路径越界')
    # Also guard ancestors when the approved root is a nested backup directory.
    parts=path.split('/')
    for n in range(1,len(parts)):
        parent=await maybe_stat(afc,'/'.join(parts[:n]))
        if parent is None:return
        if parent.get('st_ifmt')!='S_IFDIR' or parent.get('LinkTarget'):
            raise ValueError('拒绝经过链接或非目录清理：'+'/'.join(parts[:n]))
    info=await maybe_stat(afc,path)
    if info is None:return
    kind=info.get('st_ifmt')
    if kind=='S_IFLNK' or info.get('LinkTarget'):
        await afc.rm_single(path)  # REMOVE_PATH only; no recursive rm.
    elif kind=='S_IFDIR':
        for name in await afc.listdir(path):
            if name in ('.','..'):continue
            if '/' in name or '\\' in name:raise ValueError('目录条目异常')
            await remove_media_tree(afc,path+'/'+name,root)
        await afc.rm_single(path)
    elif kind=='S_IFREG':await afc.rm_single(path)
    else:raise ValueError('未知条目类型，未删除：'+path)
    if await maybe_stat(afc,path) is not None:raise RuntimeError('删除后仍存在：'+path)

async def cleanup_files(afc,src,lnk,backup_dir,old,kept,success):
    errors=[]
    for path in (lnk,src):
        try:await remove_media_tree(afc,path,path)
        except Exception as exc:errors.append(path+': '+str(exc))
    if success:
        # The requested payload is local and has been dispatched. No automatic
        # backup is needed after success; retain old files only on failure.
        for path in (old,kept):
            try:await remove_media_tree(afc,path,backup_dir)
            except Exception as exc:errors.append(path+': '+str(exc))
    for directory in (backup_dir,'UnicomFastRestore'):
        try:
            info=await maybe_stat(afc,directory)
            if info and info.get('st_ifmt')=='S_IFDIR' and not info.get('LinkTarget'):
                if not [n for n in await afc.listdir(directory) if n not in ('.','..')]:
                    await afc.rm_single(directory)
        except Exception as exc:errors.append(directory+': '+str(exc))
    return errors

async def write_only(air,dev,apple,path,data,run_id,label):
    afc=air.AfcService(lockdown=dev['lockdown']);await afc.connect()
    token=secrets.token_hex(10)
    src,lnk=f'airlift-src-{token}',f'airlift-link-{token}'
    backup_dir='UnicomFastRestore/'+run_id
    old=backup_dir+'/'+label+'_'+posixpath.basename(path)
    kept=old+'.kept'
    target_id=posixpath.relpath(path,air.AIRLOCK_ROOT)
    ids=[target_id,f'../../{src}/p0/p1/p2/link',f'../../{src}/payload']
    dests=[old,lnk,posixpath.join(lnk,posixpath.basename(path))]
    saved,dirs=await air._save_books(afc)
    success=False;had_old=False;result={}
    try:
        for directory in ('UnicomFastRestore',backup_dir):
            if await maybe_stat(afc,directory) is None:await afc.makedirs(directory)
        await air._stage(dev['lockdown'],afc,src,ids,posixpath.dirname(path),data)
        stage=await maybe_stat(afc,src+'/payload')
        if not stage or stage.get('st_size')!=len(data):raise RuntimeError('暂存载荷大小不符，未开始替换')
        air._atc_sync(apple,dev['udid'],ids,dests)
        had_old=await maybe_stat(afc,old) is not None
        remaining=await maybe_stat(afc,src+'/payload')
        if remaining is not None:raise RuntimeError('暂存载荷未移入目标；恢复失败')
        success=True
        result.update({'ok':True,'wrote':path,'size':len(data),'payload_mode':f'{air.PAYLOAD_MODE:04o}',
                'verification':'staged payload moved; NO target readback; actual destination content and mode not measured',
                'old_copy_present':had_old})
        return result
    finally:
        # On failure keep any original copy outside its tracked asset name.
        # A future retry always uses the local payload, never a second move-back.
        if not success:
            try:
                if await maybe_stat(afc,old) is not None:await afc.rename(old,kept)
            except Exception as exc:print('隔离旧备份未完成：'+str(exc),file=sys.stderr,flush=True)
            print('如旧文件仍在，保留路径：/var/mobile/Media/'+kept+' 或 '+old,file=sys.stderr,flush=True)
        errors=await cleanup_files(afc,src,lnk,backup_dir,old,kept,success)
        try:
            await air._restore_books(afc,saved,dirs)
        except Exception as exc:errors.append('Books: '+str(exc))
        result['cleanup_ok']=not errors
        if errors:
            result.update(ok=False,error='写入/清理未全部完成：'+'; '.join(errors),cleanup_errors=errors)
            print('临时清理未完成：'+'; '.join(errors),file=sys.stderr,flush=True)

def check():
    import importlib.metadata
    for mode in ('0555','0600','0644'):
        air=load_engine(mode)
        path=next(p for p,m in ALLOWED.items() if m==mode)
        validate_archive(air,path,b'local-mode-check',mode)
    air.AppleCF()
    print('Python '+sys.version.split()[0]+' | pymobiledevice3 '+importlib.metadata.version('pymobiledevice3'),flush=True)
    print('Apple DLL 可加载；ZIP 主权限与扩展权限 0555 / 0600 / 0644 校验通过；未连接手机。',flush=True)
    print(json.dumps({'ok':True,'check':'local environment and ZIP modes','device_connected':False}))

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    for name in ('path','payload','mode','sha384','device','run-id','label'):parser.add_argument('--'+name)
    args=parser.parse_args(argv)
    try:
        if args.check:check();return 0
        if ALLOWED.get(args.path)!=args.mode:raise ValueError('路径/权限不在联通固定名单中')
        if not args.run_id or not all(c.isalnum() or c=='_' for c in args.run_id):raise ValueError('恢复编号异常')
        if not args.label or not all(c.isalnum() or c=='_' for c in args.label):raise ValueError('文件标识异常')
        data=Path(args.payload).read_bytes()
        if hashlib.sha384(data).hexdigest()!=args.sha384:raise ValueError('写入前载荷哈希校验失败')
        air=load_engine(args.mode);validate_archive(air,args.path,data,args.mode)
        async def go():
            apple,dev=await air._connect(args.device)
            check_device(dev)
            # Let an in-flight file operation finish its finally/rollback logic.
            signal.signal(signal.SIGINT,signal.SIG_IGN)
            return await write_only(air,dev,apple,args.path,data,args.run_id,args.label)
        print(json.dumps(asyncio.run(go()),ensure_ascii=False),flush=True);return 0
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
