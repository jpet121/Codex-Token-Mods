"""Behavior checks for the implementation gaps closed in 1.1; no paid calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

scratch=tempfile.TemporaryDirectory(prefix='completion 日本語 ')
os.environ['TOKEN_MODS_DIR']=scratch.name
sys.path.insert(0,str(Path(__file__).parent/'plugins/token-mods'))
from store import database,get,put,report
from input_policy import read_plan,remember,trim_json
from mods import hook
from tools_api import call
import research


class Completion(unittest.TestCase):
    def setUp(self):
        self.session=self.id()
    def event(self,event,**p):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            return hook(db,dict(hook_event_name=event,session_id=self.session,turn_id='turn',**p))
    def test_pipeline_and_instruction_guards(self):
        self.assertTrue(read_plan("Get-Content -LiteralPath 'a file.txt' | Select-Object -Skip 100 -First 120"))
        plan=read_plan("Get-Content -LiteralPath 'a file.txt' | Select-Object -Skip 100 -First 120")
        self.assertEqual((plan['source'],plan['start'],plan['limit']),('a file.txt',101,120))
        for text in ('cat AGENTS.md | head -n 4','cat x | python tests.py','cat x; rm x','rg --pre execute x','cat x > y','rg --files .'):
            self.assertIsNone(read_plan(text),text)
        self.assertIsNotNone(read_plan("cat 'file;withsemicolon.txt' | head -n 8"))
    def test_interval_union_and_edit_escape(self):
        with database() as db:
            remember(db,self.session,'x',1,60,100)
            r=remember(db,self.session,'x',30,50,100)
            self.assertEqual(r['lines_seen'],79)
            self.assertEqual(r['previous_share'],.6)
        text='short line\n'*120
        source=str(Path.cwd()/'source.txt')
        from store import save_original
        with database() as db: remember(db,self.session,source,1,600,1000,save_original('Whole observed source notes.','txt'))
        e=dict(tool_name='Read',tool_input={'path':'source.txt','offset':601,'limit':120},tool_response={'file':{'content':text,'totalLines':1000}})
        self.assertEqual(self.event('PostToolUse',**e)['decision'],'block')
        e['tool_input']['limit']=30; e['tool_response']['file']['content']='short\n'*30
        self.assertEqual(self.event('PostToolUse',**e),{})
    def test_trim_preserves_paging_and_long_text(self):
        value={'avatar_url':'data:'+'x'*20000,'body':'body'*5000,'next_cursor':'opaque==','total':5,'nested':{'rich_text':'dupe','id':'keep'}}
        result=trim_json(value)
        self.assertNotIn('avatar_url',result); self.assertEqual(result['body'],value['body'])
        self.assertEqual((result['next_cursor'],result['total'],result['nested']['id']),('opaque==',5,'keep'))
    def test_parts_scope_and_full(self):
        call('mods',dict(action='off',module='input-router',part='connector',session=self.session))
        e=dict(tool_name='mcp__records__get_rows',tool_input={},tool_response={'content':[{'type':'text','text':'body '*5000}]})
        self.assertEqual(self.event('PostToolUse',**e),{})
        call('mods',dict(action='on',module='input-router',part='connector',session=self.session))
        self.assertEqual(self.event('PostToolUse',**e)['decision'],'block')
    def test_semantic_failure_retains_original(self):
        call('mods',dict(action='set',name='auto_workers',value=True,session=self.session))
        with patch('runner.run_worker',return_value=dict(accepted=False,status='timeout')):
            r=self.event('PostToolUse',tool_name='Bash',tool_input={'command':'cat data.txt'},tool_response='Data\n'*3000)
        self.assertEqual(r,{})
    def test_price_estimates_and_compactions(self):
        call('mods',dict(action='set',name='prices',value={'test':{'input':1,'cached':.1,'output':2}},session=self.session))
        self.event('PostModelRequest',model='test',status='completed',token_usage={'input_tokens':100,'cached_input_tokens':20,'output_tokens':10})
        self.event('PreCompact',trigger='manual'); self.event('PostCompact',trigger='manual')
        r=call('savings_proof',dict(session=self.session))
        self.assertAlmostEqual(r['list_price_estimate']['usd'],.000102)
        self.assertIsNone(r['billed_cost'])
        self.assertEqual(r['modules']['savings-proof']['actions'],2)
    def test_redaction_and_workspace(self):
        from insights import redact,workspace
        s=redact('Bearer '+('x'*30)+'\nPASSWORD="verysecretstring"\nsk-'+('y'*30))
        self.assertNotIn('verysecretstring',s); self.assertNotIn('x'*30,s); self.assertNotIn('y'*30,s)
        r=workspace(scratch.name); self.assertFalse(r['git']); self.assertTrue(r['errors'])
    def test_handoff_tool_evidence(self):
        self.event('SessionStart',cwd=scratch.name,model='test')
        self.event('UserPromptSubmit',prompt='Finish verification. PASSWORD="verysecretstring"')
        self.event('PostToolUse',tool_name='Bash',tool_input={'command':'py check.py'},tool_response='CHECK_PASSED')
        self.event('Stop',last_assistant_message='Tests passed')
        r=call('handoff',dict(session=self.session))
        text=Path(r['source']).read_text(encoding='utf-8')
        self.assertIn('CHECK_PASSED',text); self.assertIn('py check.py',text); self.assertIn('workspace',text)
        self.assertNotIn('verysecretstring',text); self.assertNotIn('verysecretstring',Path(r['path']).read_text(encoding='utf-8'))
    def test_deep_parallel_pipeline_and_failed_part(self):
        def worker(question,module,session,**kwargs):
            if 'Plan research' in question: brief=json.dumps({'mode':'deep','parts':['one','two'],'official_urls':['https://docs.python.org/3/howto/sorting.html']})
            elif 'judge relevance' in question: brief='{"keep":[1]}'
            elif 'research brief' in question: brief='Sorting is stable [1].'
            elif question.endswith('two'): return dict(accepted=False,status='timeout',brief='',sources=[],usage=None)
            else: brief='Read the primary page.'
            return dict(accepted=True,status='completed',brief=brief,sources=[],usage={'input_tokens':1,'cached_input_tokens':0,'output_tokens':1})
        page=dict(url='https://docs.python.org/3/howto/sorting.html',text='Sorting is stable.',outside_window=False,relevance_overlap=1,date_status='unknown',via='fixture')
        with patch('research.run_worker',side_effect=worker),patch('research.fetch',return_value=page):
            r=research.research(dict(question='sorting',mode='deep',session=self.session))
        self.assertTrue(r['accepted']); self.assertTrue(r['partial']); self.assertEqual(r['worker_count'],5)
        self.assertTrue(Path(r['evidence']).is_file()); self.assertEqual(r['sources'][0]['number'],1)
    def test_invalid_citation_not_accepted(self):
        def worker(question,*a,**kw):
            brief='{"official_urls":["https://docs.python.org/3/howto/sorting.html"]}' if 'Plan research' in question else 'Unsupported fact [99].'
            return dict(accepted=True,brief=brief,status='completed',sources=[],usage=None)
        page=dict(url='https://docs.python.org/3/howto/sorting.html',text='sorting',outside_window=False,relevance_overlap=1,date_status='unknown')
        with patch('research.run_worker',side_effect=worker),patch('research.fetch',return_value=page):
            r=research.research(dict(question='sorting',mode='quick',session=self.session))
        self.assertFalse(r['accepted']); self.assertTrue(r['gaps'])
    def test_missing_fallback_and_private_source(self):
        with patch('research.shutil.which',return_value=None): self.assertFalse(research.fallback('query',self.session)['available'])
        with self.assertRaises(ValueError): research.public_url('file:///C:/secret')
        with self.assertRaises(ValueError): research.public_url('http://127.0.0.1/data')
    def test_readonly_status_and_judge_failure(self):
        with self.assertRaises(ValueError): call('mods_status',dict(action='off',module='handoff'))
        with patch('research.run_worker',return_value=dict(accepted=False,brief='invalid',usage=None)):
            r=research.judge('Task',self.session,'judge-model')
        self.assertIsNone(r['confidence']); self.assertFalse(r['applied'])
    def test_chunked_source_notes_cover_each_part(self):
        import reading
        path=Path(scratch.name)/'long.txt'; path.write_text('A'*120000+'B'*80000,encoding='utf-8')
        def fake(*a,**p):
            data=Path(p['file']).read_text(encoding='utf-8')
            return dict(accepted=True,brief='A part' if 'A'*10 in data else 'B part',usage={'input_tokens':3})
        with patch('reading.run_worker',side_effect=fake) as worker:
            r=reading.source_notes(dict(path=str(path),question='Cover both',session=self.session))
        self.assertEqual(worker.call_count,2); self.assertFalse(r['partial']); self.assertIn('B part',r['brief'])
        self.assertEqual(r['coverage']['characters'],200000)
    def test_unicode_worker_source_is_supplied_without_shell(self):
        import runner
        path=Path(scratch.name)/'unicode.txt'
        source='資料'*59000+'\nFINAL DECISION: Zoë 18400 USD.'
        path.write_text(source,encoding='utf-8')
        received=[]
        class Process:
            returncode=0
            def __init__(self,cmd,**kwargs):
                self.output=kwargs['stdout']
            def communicate(self,prompt,timeout):
                received.append(prompt.decode('utf-8'))
                for event in (dict(type='turn.started'),dict(type='item.completed',item=dict(type='agent_message',text='Zoë 18400 USD.')),dict(type='turn.completed',usage=dict(input_tokens=10,cached_input_tokens=0,output_tokens=4))):
                    self.output.write((json.dumps(event)+'\n').encode())
        with patch('runner.subprocess.Popen',Process):
            r=runner.run_worker('Extract final decision','input-router',self.session,file=path)
        self.assertTrue(r['accepted']); self.assertTrue(source in received[0].replace('\r\n','\n'),'Complete Unicode source must be embedded')
    def test_owned_session_timeout_interrupts_active_turn(self):
        import companion
        client=object.__new__(companion.Client)
        client.q=__import__('queue').Queue(); calls=[]
        def request(method,params):
            calls.append((method,params)); return {'turn':{'id':'active-turn'}}
        client.request=request
        with self.assertRaises(TimeoutError): client.turn('owned-session','question',timeout=.01)
        self.assertEqual(calls[-1],('turn/interrupt',{'threadId':'owned-session','turnId':'active-turn'}))
    def test_auto_note_rate_and_total_cap(self):
        call('mods',dict(action='set',name='auto_workers',value=True,session=self.session))
        with patch('runner.run_worker',return_value=dict(accepted=True,brief='Semantic result.')) as worker:
            for i in range(6):
                with database() as db: put(db,'auto_last',0,self.session)
                self.event('PostToolUse',tool_name='Bash',tool_input={'command':'cat file'+str(i)+'.txt'},tool_response='Evidence\n'*3000)
        self.assertEqual(worker.call_count,4)
        with database() as db: self.assertEqual(get(db,'auto_count',self.session),4)
    def test_model_judge_risk_and_validation(self):
        with patch('research.run_worker',return_value=dict(accepted=True,brief='{"tier":"quick","confidence":0.1,"risk":0.95,"effort":"high"}')):
            r=research.judge('Irreversible deployment',self.session,'judge-model')
        self.assertEqual(r['tier'],'deep')
        with self.assertRaises(ValueError): call('mods',dict(action='set',name='prices',value={'bad':{'input':float('inf'),'cached':0,'output':1}},session=self.session))


if __name__=='__main__': unittest.main(verbosity=2)
