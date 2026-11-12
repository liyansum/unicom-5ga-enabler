"""Offline only: original package, native dispatch, ordering and fail-stop."""
import asyncio,importlib.util,json,sys,tempfile,unittest,ast
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
r=load('ipcc_restore_test',ROOT/'restore.py');i=load('original_installer_test',ROOT/'tools/install_original_ipcc.py')
r.DEVICE='offline-test-device'

class TestIPCCUpdate(unittest.TestCase):
 def test_original_package_and_device_family(self):
  p=ROOT/'payloads'/r.IPCC_NAME;meta=r.validate('full');info=i.validate_package(p,meta[r.IPCC_NAME]['sha384'])
  self.assertEqual(info['version'],'73.0');self.assertIn('D73',info['model'])
  self.assertEqual(info['sha256'],'54b8895eec8e815830d6587d6500fdd11a34c6ed4522b4490e74801435f845c6')
 def test_tampered_package_rejected(self):
  raw=bytearray((ROOT/'payloads'/r.IPCC_NAME).read_bytes());raw[-1]^=1
  with tempfile.TemporaryDirectory(dir=ROOT.parent) as tmp:
   p=Path(tmp)/'bad.ipcc';p.write_bytes(raw)
   with self.assertRaisesRegex(ValueError,'校验失败'):i.validate_package(p)
 def test_required_modes_validate_original_before_device_access(self):
  for mode in ('normal','full','debug_ipcc','debug_aux','debug_overlay','check'):
   with patch.object(i,'validate_package',side_effect=ValueError('invalid baseline')) as check:
    with patch.object(r.importlib.util,'module_from_spec',return_value=i),patch.object(r.importlib.util,'spec_from_file_location') as spec:
     spec.return_value.loader.exec_module=lambda module:None
     if mode in ('normal','debug_aux','debug_overlay'):r.validate(mode);check.assert_not_called()
     else:
      with self.assertRaisesRegex(ValueError,'invalid baseline'):r.validate(mode)
      check.assert_called_once()
 def test_mode_order_and_permissions(self):
  meta=r.validate('check')
  expected_full=['install_ipcc','bundle_pri','bundle_plist','bundle_signature','bundle_carrier','bundle_common_signature','bundle_info','overlay_7201','overlay_730','reload_commcenter','overlay_7201_after_reload','overlay_730_after_reload']
  for mode,count in [('normal',5),('full',12)]:
   seen=[]
   def one(key,cmd,env):seen.append((key,cmd,env));return True
   self.assertTrue(r.execute(mode,meta,'test',one));self.assertEqual(len(seen),count)
   if mode=='normal':self.assertEqual([x[0] for x in seen],['overlay_7201','overlay_730','reload_commcenter','overlay_7201_after_reload','overlay_730_after_reload'])
   else:
    self.assertEqual(seen[0][0],'install_ipcc');self.assertIn(str(ROOT/'payloads'/r.IPCC_NAME),seen[0][1])
    self.assertEqual([x[0] for x in seen],expected_full)
    self.assertEqual(seen[-1][1][-1],'overlay_730_after_reload')
   for key,_,env in seen:
    self.assertEqual(env['AIRLIFT_PAYLOAD_MODE'],'0555' if key.startswith('overlay') else '0600' if key in r.BUNDLE_600 else '0644')
 def test_0600_files_are_always_rewritten_and_match_writer_allowlist(self):
  w=load('mode_writer_test',ROOT/'tools/write_unicom.py')
  self.assertEqual(w.ALLOWED,{path:mode for name,path,mode in r.JOBS.values()})
  seen=[]
  self.assertTrue(r.execute('full',r.validate('full'),'test',lambda key,cmd,env:seen.append((key,cmd,env)) or True))
  for key in ('bundle_carrier','bundle_common_signature','bundle_info'):
   step=next(x for x in seen if x[0]==key)
   self.assertEqual(step[1][step[1].index('--mode')+1],'0600')
   self.assertEqual(step[2]['AIRLIFT_PAYLOAD_MODE'],'0600')
  air=w.load_engine('0600')
  for key in r.BUNDLE_600:
   name,path,mode=r.JOBS[key];w.validate_archive(air,path,(ROOT/'payloads'/name).read_bytes(),mode)
 def test_failure_in_0600_stage_stops_before_overlay_and_reload(self):
  seen=[]
  def one(key,cmd,env):seen.append(key);return key!='bundle_common_signature'
  self.assertFalse(r.execute('full',r.validate('full'),'test',one))
  self.assertEqual(seen[-1],'bundle_common_signature');self.assertNotIn('reload_commcenter',seen);self.assertNotIn('overlay_7201',seen)
 def test_install_or_directory_verification_failure_stops_all_writes(self):
  for mode in ('full',):
   seen=[]
   def fail_install(key,cmd,env):seen.append(key);return False
   self.assertFalse(r.execute(mode,r.validate(mode),'test',fail_install));self.assertEqual(seen,['install_ipcc'])
 def test_bundle_failure_after_install_stops_overlays(self):
  seen=[]
  def fail_plist(key,cmd,env):seen.append(key);return key!='bundle_plist'
  self.assertFalse(r.execute('full',r.validate('full'),'test',fail_plist));self.assertEqual(seen,['install_ipcc','bundle_pri','bundle_plist'])
 def test_reload_and_reapply_failures_stop_later_steps(self):
  for fail_key in ('reload_commcenter','overlay_7201_after_reload'):
   seen=[]
   def one(key,cmd,env):seen.append(key);return key!=fail_key
   self.assertFalse(r.execute('full',r.validate('full'),'test',one))
   self.assertEqual(seen[-1],fail_key)
   self.assertNotIn('overlay_730_after_reload',seen)
 def test_native_installer_command_and_cleanup(self):
  for failure in (False,True):
   events=[]
   class Proxy:
    async def upload_ipcc_from_path(self,p,remote,afc):events.append(('upload',p.name,remote))
    async def send_package(self,cmd,opts,handler,remote):
     events.append(('send',cmd,opts,remote))
     if failure:raise RuntimeError('native install rejected')
   class Writer:
    async def remove_media_tree(self,afc,path,root):events.append(('cleanup',path,root))
   task=i.install_via_proxy(Proxy(),object(),ROOT/'payloads'/r.IPCC_NAME,'/PublicStaging/UnicomFastIPCC_test.ipcc',Writer())
   if failure:
    with self.assertRaisesRegex(RuntimeError,'native install rejected'):asyncio.run(task)
   else:asyncio.run(task)
   self.assertEqual(events[1][1:3],('Install',{'PackageType':'CarrierBundle'}))
   self.assertEqual(events[-1],('cleanup','PublicStaging/UnicomFastIPCC_test.ipcc','PublicStaging/UnicomFastIPCC_test.ipcc'))
 def test_installer_never_uses_move_readback_or_restores_sqlite(self):
  tree=ast.parse((ROOT/'tools/install_original_ipcc.py').read_text(encoding='utf8'))
  calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
  self.assertFalse(set(calls)&{'_read_file','read_file','_replace_file','replace_file','_restore_books','_save_books'})
  text=(ROOT/'tools/install_original_ipcc.py').read_text(encoding='utf8')
  self.assertIn("info.get('st_ifmt')!='S_IFDIR'",text)
 def test_directory_metadata_guard_and_link_cleanup(self):
  for kind in ('S_IFDIR','S_IFLNK',None):
   events=[]
   class Afc:
    async def listdir(self,path):return ['Books','PublicStaging']
    async def get_file_contents(self,path):events.append(('read',path));return b'original profile'
    async def set_file_contents(self,path,data):events.append(('restore',path,data))
   class Writer:
    async def maybe_stat(self,afc,path):
     if path.startswith('Books/'):return {'st_ifmt':'S_IFREG'}
     return {'st_ifmt':kind} if kind else None
    async def remove_media_tree(self,afc,path,root):events.append(('cleanup',path,root))
   async def stage(*args):events.append(('stage',args[3]))
   air=SimpleNamespace(_stage=stage,_atc_sync=lambda *args:events.append(('sync',args[2])))
   task=i._verify_var_directories(air,None,Afc(),None,'mock-device',Writer())
   if kind=='S_IFDIR':self.assertEqual(len(asyncio.run(task)),2)
   else:
    with self.assertRaisesRegex(RuntimeError,'未继续写'):asyncio.run(task)
   self.assertEqual([x[1] for x in events if x[0]=='read'],['Books/Books.plist','Books/Sync/Books.plist'])
   self.assertEqual(len([x for x in events if x[0]=='cleanup']),2)
   self.assertEqual(len([x for x in events if x[0]=='restore']),2)
   ids=next(x[1] for x in events if x[0]=='stage')
   self.assertEqual(len(ids),1);self.assertTrue(ids[0].endswith('/link'))
 def test_expected_launchers(self):self.assertEqual({p.name for p in ROOT.glob('*.bat')},{'开启5GA.bat'})

if __name__=='__main__':unittest.main(verbosity=2)
