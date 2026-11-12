"""Offline checks for merged menus and five independent debug actions."""
import importlib.util,io,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock,patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
r=load('merged_restore_tests',ROOT/'restore.py')
r.DEVICE='offline-test-device'
i=load('installer_tests',ROOT/'tools/install_original_ipcc.py')

class TestDebug(unittest.TestCase):
 def setUp(self):self.meta=r.validate('check')
 def dispatch(self,mode,fail=None):
  self.seen=[]
  def one(key,cmd,env):self.seen.append((key,cmd,env));return key!=fail
  return r.execute(mode,self.meta,'offline_test',one)
 def test_debug_reload_has_no_writes_or_ipcc_install(self):
  self.assertTrue(self.dispatch('debug_reload'))
  self.assertEqual([x[0] for x in self.seen],['reload_commcenter'])
 def test_debug_bundle_only_checks_directory_and_writes_three_0644_files(self):
  self.assertTrue(self.dispatch('debug_bundle'))
  self.assertEqual([x[0] for x in self.seen],['check_bundle_directory','bundle_pri','bundle_plist','bundle_signature'])
  self.assertIn('--verify-only',self.seen[0][1]);self.assertNotIn('--package',self.seen[0][1])
  self.check_writes('0644')
 def test_debug_aux_only_checks_directory_and_rewrites_three_0600_files(self):
  self.assertTrue(self.dispatch('debug_aux'))
  self.assertEqual([x[0] for x in self.seen],['check_bundle_directory','bundle_carrier','bundle_common_signature','bundle_info'])
  self.check_writes('0600')
 def check_writes(self,mode):
  for key,cmd,env in self.seen[1:]:
   self.assertEqual(env['AIRLIFT_PAYLOAD_MODE'],mode);self.assertEqual(cmd[cmd.index('--mode')+1],mode)
   self.assertTrue(cmd[cmd.index('--path')+1].startswith(r.BUNDLE+'/'))
 def test_missing_bundle_directory_stops_without_installing_or_writing(self):
  for mode in ('debug_bundle','debug_aux'):
   self.assertFalse(self.dispatch(mode,'check_bundle_directory'))
   self.assertEqual([x[0] for x in self.seen],['check_bundle_directory'])
 def test_debug_overlay_writes_only_two_overlays_0555(self):
  self.assertTrue(self.dispatch('debug_overlay'))
  self.assertEqual([x[0] for x in self.seen],['overlay_7201','overlay_730'])
  for key,cmd,env in self.seen:
   self.assertEqual(env['AIRLIFT_PAYLOAD_MODE'],'0555');self.assertEqual(cmd[cmd.index('--mode')+1],'0555')
 def test_debug_ipcc_installs_original_without_config_writes_or_reload(self):
  self.assertTrue(self.dispatch('debug_ipcc'))
  self.assertEqual([x[0] for x in self.seen],['install_ipcc'])
  self.assertIn(str(ROOT/'payloads/Unicom_cn_73.0_original.ipcc'),self.seen[0][1])
 def test_normal_writes_reload_rewrites_and_stops_on_failure(self):
  self.assertTrue(self.dispatch('normal'))
  self.assertEqual([x[0] for x in self.seen],['overlay_7201','overlay_730','reload_commcenter','overlay_7201_after_reload','overlay_730_after_reload'])
  self.assertFalse(self.dispatch('normal','overlay_730'))
  self.assertNotIn('reload_commcenter',[x[0] for x in self.seen])
  self.assertFalse(self.dispatch('normal','overlay_7201_after_reload'))
  self.assertNotIn('overlay_730_after_reload',[x[0] for x in self.seen])
 def test_verify_only_does_not_dispatch_install(self):
  with patch.object(i,'run_verify_only',new_callable=AsyncMock,return_value={'ok':True}) as verify,patch.object(i,'run_install',new_callable=AsyncMock) as install:
   with redirect_stdout(io.StringIO()):self.assertEqual(i.main(['--verify-only','--device','mock-device']),0)
   verify.assert_awaited_once_with('mock-device');install.assert_not_called()
 def test_mode_and_debug_menu_numbers_dispatch_separately(self):
  inputs=['3','1','2','3','4','5','0','1','2','0']
  with patch('builtins.input',side_effect=inputs),patch.object(r,'run_mode',return_value=0) as run:
   with redirect_stdout(io.StringIO()):self.assertEqual(r.main([]),0)
  self.assertEqual([call.args[0] for call in run.call_args_list],['debug_ipcc','debug_bundle','debug_aux','debug_overlay','debug_reload','full','normal'])

if __name__=='__main__':unittest.main(verbosity=2)
