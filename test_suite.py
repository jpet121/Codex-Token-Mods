"""Reproducible native shell/MCP integration and edge-case acceptance tests (no paid requests)."""
import base64
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import setup_port

PLUGIN=setup_port.PLUGIN


class Suite(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='Token Mods 日本語 ')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.env={**os.environ,'TOKEN_MODS_DIR':str(self.root/'state'),'PYTHONUTF8':'1'}
        setup_port.prepare()
        self.handlers=json.loads((PLUGIN/'hooks/hooks.json').read_text(encoding='utf-8'))['hooks']

    def control(self,*args):
        r=subprocess.run([sys.executable,str(PLUGIN/'mods.py'),*args],env=self.env,capture_output=True,encoding='utf-8',check=True)
        return json.loads(r.stdout)

    def event(self,kind,session='live-like',**fields):
        command=self.handlers[kind][0]['hooks'][0]['command']
        r=subprocess.run(command,shell=True,input=json.dumps(dict(session_id=session,turn_id='turn',hook_event_name=kind,**fields),ensure_ascii=False),
                         env=self.env,capture_output=True,encoding='utf-8',check=True)
        self.assertFalse(r.stderr.strip(),r.stderr)
        return json.loads(r.stdout)

    def tool(self,tool_name,**args):
        req=[dict(jsonrpc='2.0',id=1,method='initialize',params={}),dict(jsonrpc='2.0',method='notifications/initialized'),
             dict(jsonrpc='2.0',id=2,method='tools/call',params={'name':tool_name,'arguments':args})]
        r=subprocess.run([sys.executable,str(PLUGIN/'server.py')],input='\n'.join(map(json.dumps,req))+'\n',env=self.env,capture_output=True,encoding='utf-8',check=True)
        result=json.loads(r.stdout.splitlines()[-1])['result']
        if result['isError']: raise ValueError(result['content'][0]['text'])
        return json.loads(result['content'][0]['text'])

    def test_capture_unicode_usage_and_unknown_cache(self):
        self.event('SessionStart',cwd=str(self.root),model='actual-model')
        self.event('UserPromptSubmit',prompt='Summarize café 日本語')
        self.event('Stop',last_assistant_message='Café complete 日本語')
        draft=self.control('handoff','live-like')
        self.assertIn('Café complete 日本語',Path(draft['path']).read_text(encoding='utf-8'))
        self.event('PostModelRequest',status='completed',token_usage={'input_tokens':10,'cached_input_tokens':4,'output_tokens':2})
        self.event('PostModelRequest',status='failed',token_usage=None)
        report=self.control('usage','--session','live-like')
        self.assertEqual(report['measured_tokens']['cached_input_tokens'],4)
        self.assertEqual(report['attempts_without_counts'],1)
        self.assertEqual(self.control('clock','live-like')['cache_expiry'],'unknown')

    def test_switch_restart_and_scope(self):
        self.control('off','input-router')
        self.assertFalse(self.tool('mods',action='list')['modules']['input-router']['enabled'])
        self.control('on','input-router','--session','override')
        self.assertTrue(self.control('list','--session','override')['modules']['input-router']['enabled'])
        self.control('on','input-router')
        self.control('off','handoff','--session','a')
        self.assertTrue(self.control('list','--session','b')['modules']['handoff']['enabled'])
        self.control('set','worker_timeout','35')
        self.assertEqual(self.control('list')['settings']['worker_timeout'],35)
        self.control('reset','worker_timeout')
        self.assertEqual(self.control('list')['settings']['worker_timeout'],90)

    def test_large_read_and_original(self):
        text='irrelevant background\n'*1000+'DECISION: delivery date 2026-12-03 café\n'+'other text\n'*1000
        self.event('UserPromptSubmit',prompt='Find delivery date')
        r=self.event('PostToolUse',tool_name='Bash',tool_input={'command':'Get-Content report.txt'},tool_response=text)
        self.assertEqual(r['decision'],'block'); self.assertIn('2026-12-03',r['reason'])
        events=self.control('events')
        path=next(x['detail']['source'] for x in events if x['action']=='extracted')
        self.assertEqual(json.loads(Path(path).read_text(encoding='utf-8')),text)

    def test_full_only_consumes_eligible(self):
        self.control('full','input-router','--session','live-like')
        args=dict(tool_name='Bash',tool_input={'command':'Get-Content data.txt'})
        self.assertEqual(self.event('PostToolUse',tool_response='tiny',**args),{})
        self.assertEqual(self.event('PostToolUse',tool_response='hello\n'*3000,**args),{})
        self.assertEqual(self.event('PostToolUse',tool_response='hello\n'*3000,**args)['decision'],'block')

    def test_precision_instructions_errors_and_images_pass(self):
        for command in ('Get-Content AGENTS.md','rg --files .','python tests.py','Get-Content a.txt | Set-Content b.txt'):
            self.assertEqual(self.event('PostToolUse',tool_name='Bash',tool_input={'command':command},tool_response='abc\n'*6000),{})
        self.assertEqual(self.event('PostToolUse',tool_name='Bash',tool_input={'command':'cat a.txt'},tool_response={'exit_code':1,'output':'bad'*6000}),{})
        self.assertEqual(self.event('PostToolUse',tool_name='mcp__drive__get_file',tool_input={},tool_response={'content':[{'type':'image','data':'x'*20000}]}),{})

    def test_connector_pagination_and_control_exclusion(self):
        value={'content':[{'type':'text','text':json.dumps({'next_cursor':'opaque==','has_more':True,'data':[{'text':'body'*1000}]*20})}]}
        r=self.event('PostToolUse',tool_name='mcp__codex_apps__google_drive_search',tool_input={},tool_response=value)
        self.assertIn('opaque==',r['reason']); self.assertIn('has_more',r['reason'])
        for tool in ('mcp__browser__read_page','mcp__drive__update_file','mcp__token_mods__input_router'):
            self.assertEqual(self.event('PostToolUse',tool_name=tool,tool_input={},tool_response=value),{})

    def test_explicit_bytes_and_partial_unicode(self):
        source=self.root/'réport 日本語.txt'; data='Résumé 日本語\n'*2000
        source.write_text(data,encoding='utf-8')
        result=self.tool('input_router',action='range',path=str(source),offset=3,limit=101)
        self.assertEqual(base64.b64decode(result['exact_bytes_base64']),source.read_bytes()[3:104])
        self.assertTrue(result['truncated'])
        self.assertIn('extracts',self.tool('input_router',action='brief',path=str(source),question='Résumé'))

    def test_models_manual_and_effort_are_advice(self):
        self.control('set','model_quick','account-model')
        r=self.tool('model_router',action='plan',question='List colors',model='manual-model')
        self.assertEqual(r['selected_model'],'manual-model'); self.assertFalse(r['applied'])
        r=self.event('PreToolUse',tool_name='spawn_agent',tool_input={'message':'List colors','fork_turns':'none'})
        self.assertNotIn('permissionDecision',json.dumps(r)); self.assertIn('account-model',json.dumps(r))
        self.assertEqual(self.event('PreToolUse',tool_name='spawn_agent',tool_input={'message':'List colors','fork_turns':'all'}),{})
        self.assertEqual(self.event('PreToolUse',tool_name='spawn_agent',tool_input={'message':'List colors','fork_turns':'none','model':'explicit'}),{})

    def test_concurrent_sessions_and_missing_data(self):
        def run(i): return self.event('PostModelRequest',session=str(i),status='completed',token_usage=None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: list(pool.map(run,range(10)))
        self.assertEqual(self.control('usage')['attempts_without_counts'],10)
        self.assertIsNone(self.control('usage')['measured_tokens'])

    def test_preview_coordinate_map_and_original(self):
        from PIL import Image
        source=self.root/'original.png'; target=self.root/'preview.png'
        Image.new('RGB',(1600,1000),'white').save(source)
        data=source.read_bytes()
        r=self.tool('efficient_browser_use',path=str(source),target=str(target))
        self.assertEqual(r['preview'],[800,500]); self.assertEqual(r['point_to_original'],[2,2])
        self.assertEqual(source.read_bytes(),data); self.assertIsNone(r['measured_token_savings'])
        with self.assertRaises(ValueError): self.tool('efficient_browser_use',path=str(source),target=str(target))

    def test_disabled_worker_missing_cli_and_no_paid_background(self):
        self.control('off','research-router')
        with self.assertRaisesRegex(ValueError,'is off'): self.tool('research_router',action='run',question='Read primary docs')
        self.env['TOKEN_MODS_CODEX']='nonexistent-codex-executable'
        with self.assertRaisesRegex(ValueError,'not found'): self.tool('model_router',action='run',question='List colors')
        self.assertFalse(self.tool('mods_status')['settings']['auto_workers'])
        self.assertTrue(self.tool('mods',action='set',name='auto_workers',value=True)['settings']['auto_workers'])
        with self.assertRaisesRegex(ValueError,'boolean'): self.tool('mods',action='set',name='auto_workers',value='yes')

    def test_malformed_hook_fails_open(self):
        command=self.handlers['PostToolUse'][0]['hooks'][0]['command']
        r=subprocess.run(command,shell=True,input='{bad',capture_output=True,encoding='utf-8',env=self.env,check=True)
        self.assertEqual(json.loads(r.stdout),{})

    def test_handoff_offer_threshold_and_hidden_advice(self):
        self.control('set','handoff_threshold','20')
        self.event('PostModelRequest',status='completed',token_usage={'input_tokens':30,'cached_input_tokens':0,'output_tokens':1})
        r=self.event('UserPromptSubmit',prompt='Continue work')
        self.assertIn('handoff threshold',str(r))
        self.assertNotIn('handoff threshold',str(self.event('UserPromptSubmit',prompt='Continue work')))
        self.tool('mods',action='hide',module='effort-optimizer')
        self.assertEqual(self.event('UserPromptSubmit',prompt='List names'),{})

    def test_worker_note_cache_is_keyed_by_source_and_policy(self):
        # A saved accepted result is a fixture, not live worker acceptance.
        source=self.root/'input.txt'; source.write_text('Evidence',encoding='utf-8')
        script='''import sys,json
sys.path.insert(0,sys.argv[1])
from unittest.mock import patch
import tools_api
result=dict(accepted=True,usage={'input_tokens':5},evidence='fixture',brief='Evidence')
with patch('runner.run_worker',return_value=result) as worker:
 a=tools_api.call('input_router',dict(action='worker',path=sys.argv[2],question='Extract evidence'))
 b=tools_api.call('input_router',dict(action='worker',path=sys.argv[2],question='Extract evidence'))
 assert worker.call_count==1 and b['cached_result'] and b['usage'] is None
 open(sys.argv[2],'w').write('Changed evidence')
 tools_api.call('input_router',dict(action='worker',path=sys.argv[2],question='Extract evidence'))
 assert worker.call_count==2
print('cache verified')'''
        r=subprocess.run([sys.executable,'-c',script,str(PLUGIN),str(source)],env=self.env,capture_output=True,encoding='utf-8')
        self.assertEqual(r.returncode,0,r.stderr)

    def test_pdf_page_ranges_and_no_text_layer(self):
        try:
            from reportlab.pdfgen import canvas
            import pypdf
        except ImportError:
            self.skipTest('Optional PDF fixture needs reportlab and pypdf')
        path=self.root/'Six pages.pdf'
        c=canvas.Canvas(str(path))
        for i in range(6):
            c.drawString(72,700,f'PAGE {i+1}: approved budget is 18400 USD'); c.showPage()
        c.save()
        r=self.tool('input_router',action='brief',path=str(path),page=3,pages=2)
        self.assertEqual(r['pages'],6); self.assertIn('Page 3:',r['selected']); self.assertIn('Page 4:',r['selected']); self.assertNotIn('Page 5:',r['selected'])
        self.assertTrue(r['truncated'])

    def test_full_concurrent_consumed_once(self):
        self.control('full','input-router','--session','live-like')
        def run(_): return self.event('PostToolUse',tool_name='Bash',tool_input={'command':'cat source.txt'},tool_response='Evidence\n'*2000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(run,range(3)))
        self.assertEqual(sum(x=={} for x in results),1)


if __name__=='__main__': unittest.main(verbosity=2)
