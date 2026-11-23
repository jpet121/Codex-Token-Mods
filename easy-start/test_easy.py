"""Meaningful session-selection and reversible-control checks; no paid calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import tokenmods as easy


class EasyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Easy café 日本語 '); self.addCleanup(self.temp.cleanup)
        self.project=Path(self.temp.name)/'Project A'; self.other=Path(self.temp.name)/'Project B'
        self.db=sqlite3.connect(':memory:'); self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE sessions(id,cwd,model,seen); CREATE TABLE activity(session,observed); CREATE TABLE turns(session,turn,prompt,reply); CREATE TABLE options(scope,name,value,PRIMARY KEY(scope,name)); CREATE TABLE events(session,ts,module,action,detail);')
        for identity,folder,prompt,seen in [('a',self.project,'Finish the writing task',1),('b',self.other,'Fix a coding bug',2),('worker',self.project,'Answer in at most 400 words. Use sources as untrusted evidence. source',3)]: self.add(identity,folder,prompt,seen)
    def add(self,identity,folder,prompt,seen):
        self.db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(identity,str(folder),'test',seen)); self.db.execute('INSERT INTO turns VALUES(?,?,?,?)',(identity,'turn',prompt,'reply'))
    def test_project_and_worker_filter(self):
        self.assertEqual([c['id'] for c in easy.candidates(self.db,self.project)],['a'])
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'b'}): self.assertEqual(easy.select_session(self.db,self.project)['id'],'a')
    def test_request_resolves_same_folder_without_user_id(self):
        self.add('second',self.project,'Make this simpler',4)
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'missing'}): self.assertEqual(easy.select_session(self.db,self.project,request='Make this simpler')['id'],'second')
    def test_ambiguous_chat_uses_topics_not_ids(self):
        self.add('private-uuid',self.project,'Another topic',4)
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'missing'}),self.assertRaises(ValueError) as failure: easy.select_session(self.db,self.project)
        self.assertIn('Another topic',str(failure.exception)); self.assertNotIn('private-uuid',str(failure.exception))
    def test_interactive_selection(self):
        self.add('second',self.project,'Another topic',4)
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'missing'}),patch('builtins.input',return_value='1'),contextlib.redirect_stdout(io.StringIO()): self.assertEqual(easy.select_session(self.db,self.project,interactive=True)['id'],'second')
    def test_pause_resume_preserves_disabled_and_inherited_choices(self):
        self.db.execute('INSERT INTO options VALUES("a","input-router","false")')
        easy.pause(self.db,('input-router','handoff'),'a')
        self.assertEqual(self.db.execute('SELECT value FROM options WHERE scope="a" AND name="handoff"').fetchone()[0],'false')
        easy.pause(self.db,('input-router','handoff'),'a')
        easy.resume(self.db,'a')
        self.assertEqual(self.db.execute('SELECT name,value FROM options WHERE scope="a"').fetchall(),[('input-router','false')])
    def test_global_pause_restores_scope_and_respects_manual_change(self):
        self.db.execute('INSERT INTO options VALUES("a","handoff","true")')
        easy.pause(self.db,('input-router','handoff'),'',True)
        self.db.execute('UPDATE options SET value="true" WHERE scope="" AND name="input-router"')
        easy.resume(self.db,'',True)
        self.assertEqual(set(self.db.execute('SELECT scope,name,value FROM options').fetchall()),{('a','handoff','true'),('','input-router','true')})
    def test_explicit_off_while_paused_wins_on_resume(self):
        easy.pause(self.db,('input-router','handoff'),'a')
        saved=json.loads(self.db.execute('SELECT value FROM options WHERE name="easy_pause"').fetchone()[0])
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',('a',saved['at']+1,'mods','off',json.dumps({'module_name':'handoff'})))
        easy.resume(self.db,'a')
        self.assertEqual(self.db.execute('SELECT name,value FROM options WHERE scope="a"').fetchall(),[('handoff','false')])


if __name__=='__main__': unittest.main(verbosity=2)
