import copy
import json
import unittest
from pathlib import Path
from server.setup import setup, SetupError

class FakeAPI:
    def __init__(self):
        self.channels=[{'id':'10','name':'général','type':0,'permission_overwrites':[{'id':'private','deny':'1024'}]}, {'id':'11','name':'actualités-marchés','type':0}, {'id':'12','name':'Général','type':2}]
        self.messages={};self.writes=[];self.counter=100
        self.name='CAP Investissement'
    def call(self,method,path,data=None):
        parts=path.split('?')[0].strip('/').split('/')
        if method=='GET':
            if path=='/users/@me':return {'id':'bot','bot':True}
            if parts[0]=='guilds':return copy.deepcopy(self.channels) if len(parts)==3 else {'name':self.name}
            if len(parts)==3:return copy.deepcopy(list(self.messages.get(parts[1],{}).values()))
            return copy.deepcopy(self.messages[parts[1]][parts[3]])
        self.writes.append((method,path,data));self.counter+=1
        if parts[0]=='guilds':
            obj={**data,'id':str(self.counter)};self.channels.append(obj);return copy.deepcopy(obj)
        if len(parts)==2:
            obj=next(c for c in self.channels if c['id']==parts[1]);obj.update(data);return copy.deepcopy(obj)
        if method=='POST':
            obj={**data,'id':str(self.counter),'author':{'id':'bot'},'pinned':False}
            self.messages.setdefault(parts[1],{})[obj['id']]=obj;return copy.deepcopy(obj)
        if method=='PUT':self.messages[parts[1]][parts[-1]]['pinned']=True;return None
        self.messages[parts[1]][parts[-1]].update(data)

class ServerSetupTests(unittest.TestCase):
    def setUp(self):self.config=json.loads(Path('server/content.json').read_text());self.api=FakeAPI()
    def test_preview_has_no_writes(self):
        setup(self.api,'123',self.config)
        self.assertEqual(self.api.writes,[])
    def test_apply_is_repeatable_and_keeps_existing_ids_permissions(self):
        setup(self.api,'123',self.config,True)
        self.assertEqual(len(self.api.channels),10)
        self.assertEqual(len(self.api.messages),6)
        self.assertEqual(next(c for c in self.api.channels if c['id']=='11')['name'],'🌍・actualités-marchés')
        self.assertEqual(self.api.channels[0]['permission_overwrites'],[{'id':'private','deny':'1024'}])
        self.api.writes=[]
        setup(self.api,'123',self.config,True)
        self.assertEqual(self.api.writes,[])
    def test_wrong_server_stops_without_writing(self):
        self.api.name='Other'
        with self.assertRaises(SetupError):setup(self.api,'123',self.config,True)
        self.assertEqual(self.api.writes,[])
    def test_ambiguous_existing_channel_stops_before_writes(self):
        self.api.channels.append({'id':'13','name':'general','type':0})
        with self.assertRaises(SetupError):setup(self.api,'123',self.config,True)
        self.assertEqual(self.api.writes,[])
    def test_resume_after_failed_pin_does_not_duplicate_message(self):
        original=self.api.call
        def fail(method,path,data=None):
            if method=='PUT':raise SetupError('pin failed')
            return original(method,path,data)
        self.api.call=fail
        with self.assertRaises(SetupError):setup(self.api,'123',self.config,True)
        self.api.call=original
        setup(self.api,'123',self.config,True)
        self.assertTrue(all(len(messages)==1 for messages in self.api.messages.values()))
    def test_foreign_bot_message_is_not_edited(self):
        self.api.messages['10']={'foreign':{'id':'foreign','author':{'id':'someone-else'},'embeds':[{'footer':{'text':'CAP SETUP · chat'}}]}}
        setup(self.api,'123',self.config,True)
        self.assertNotIn('description',self.api.messages['10']['foreign']['embeds'][0])
        self.assertEqual(len(self.api.messages['10']),2)

    def test_legacy_footer_migrates_in_place(self):
        setup(self.api,'123',self.config,True)
        original_ids={cid:list(msgs) for cid,msgs in self.api.messages.items()}
        for spec in self.config['channels']:
            if not spec.get('message'):continue
            for msgs in self.api.messages.values():
                for msg in msgs.values():
                    if msg['embeds'][0]['title']==spec['title']:
                        msg['embeds'][0]['footer']['text']='CAP SETUP · '+spec['key']
        self.api.writes=[]
        setup(self.api,'123',self.config,True)
        self.assertEqual(original_ids,{cid:list(msgs) for cid,msgs in self.api.messages.items()})
        self.assertFalse(any(method=='POST' for method,_,_ in self.api.writes))
        self.assertTrue(all(m['embeds'][0]['footer']['text'].startswith('CAP Investissement') for ms in self.api.messages.values() for m in ms.values()))
