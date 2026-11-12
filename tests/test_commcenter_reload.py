"""Offline tests: exact process, one signal, timing, PID transition and fail-stop."""
import asyncio,importlib.util,io,sys,unittest
from contextlib import redirect_stdout
from pathlib import Path

spec=importlib.util.spec_from_file_location('reload_test',Path(__file__).resolve().parents[1]/'tools/reload_commcenter.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def token(pid,path=m.COMM_CENTER):
 return {'processIdentifier':pid,'executableURL':{'relative':'file://'+path}}

class Clock:
 def __init__(self):self.now=0;self.waits=[]
 def monotonic(self):return self.now
 async def sleep(self,seconds):self.waits.append(seconds);self.now+=seconds

class CoreService:
 def __init__(self,clock,schedule=None,signal_error=None):
  self.clock=clock;self.schedule=schedule or (lambda now:952);self.signal_error=signal_error;self.signals=[]
 async def list_processes(self):
  pid=596 if not self.signals else self.schedule(self.clock.now)
  procs=[token(88,m.COMM_CENTER+'MobileHelper'),token(99,'/usr/local/bin/CommCenter')]
  if pid is not None:procs.append(token(pid))
  return procs
 async def send_signal_to_process(self,pid,signal):
  self.signals.append((pid,signal,self.clock.now))
  if self.signal_error:raise self.signal_error
  return {}

class TestReload(unittest.TestCase):
 def run_reload(self,service,clock):
  with redirect_stdout(io.StringIO()):return asyncio.run(m.reload_only(service,sleep=clock.sleep,monotonic=clock.monotonic))
 def test_only_exact_executable_can_be_selected(self):
  self.assertEqual(m.commcenter_pid([token(12,m.COMM_CENTER+'Classic'),token(13,'/tmp/CommCenter'),token(596)]),596)
  self.assertIsNone(m.commcenter_pid([token(12,m.COMM_CENTER+'MobileHelper')]))
  self.assertIsNone(m.commcenter_pid([{'processIdentifier':596,'executableURL':{'relative':'file://elsewhere'+m.COMM_CENTER}}]))
 def test_ambiguous_and_invalid_pid_refused(self):
  for entries in ([token(596),token(952)],[token(1)],[token(-1)],[token(True)]):
   with self.assertRaises(RuntimeError):m.commcenter_pid(entries)
 def test_single_signal_after_wait_then_stable_new_pid(self):
  clock=Clock();service=CoreService(clock,lambda now:None if now<7 else 952)
  result=self.run_reload(service,clock)
  self.assertTrue(result['ok']);self.assertEqual(service.signals,[(596,9,5)])
  self.assertEqual(result['new_pid'],952);self.assertGreaterEqual(clock.now,22)
  self.assertEqual(result['kill_requests'],1)
 def test_same_pid_never_counts_as_reload_and_is_not_killed_twice(self):
  clock=Clock();service=CoreService(clock,lambda now:596)
  with self.assertRaisesRegex(RuntimeError,'停止后续'):self.run_reload(service,clock)
  self.assertEqual(service.signals,[(596,9,5)])
 def test_stability_wait_restarts_if_new_process_changes(self):
  clock=Clock();service=CoreService(clock,lambda now:952 if now<12 else 953)
  result=self.run_reload(service,clock)
  self.assertEqual(result['new_pid'],953);self.assertGreaterEqual(clock.now,27)
  self.assertEqual(len(service.signals),1)
 def test_permission_failure_is_not_retried(self):
  clock=Clock();service=CoreService(clock,signal_error=RuntimeError('signal denied'))
  with self.assertRaisesRegex(RuntimeError,'signal denied'):self.run_reload(service,clock)
  self.assertEqual(service.signals,[(596,9,5)])
 def test_missing_process_does_not_signal_anyone(self):
  clock=Clock();service=CoreService(clock)
  async def no_process():return [token(88,m.COMM_CENTER+'MobileHelper')]
  service.list_processes=no_process
  with self.assertRaisesRegex(RuntimeError,'未找到'):self.run_reload(service,clock)
  self.assertEqual(service.signals,[]);self.assertEqual(clock.now,0)

if __name__=='__main__':unittest.main(verbosity=2)
