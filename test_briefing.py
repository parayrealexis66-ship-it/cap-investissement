import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from PIL import Image
import rss_to_discord as rss
from editorial import classify
from briefing import select, publish_briefing, execution_summary
from carousel import render

class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,11,12,tzinfo=timezone.utc)
        self.feed={'name':'Source test','url':'https://example.org/rss'}
        self.state={'version':2,'feeds':{}}
        self.watch=[('Entreprise Exemple','Example Inc')]
    def item(self,title,key='a'):
        return {'title':title,'id':key,'link':'https://example.org/'+key,'source':'Source test','published':self.now-timedelta(hours=1)}
    def test_company_is_selected_and_unrelated_items_are_rejected(self):
        self.assertEqual(classify(self.item('Example Inc annonce ses résultats'),self.watch)['kind'],'company')
        self.assertIsNone(classify(self.item('Les voitures électriques coûtent cher à assurer'),self.watch))
        self.assertIsNone(classify(self.item('Crise familiale dans une série télévisée'),self.watch))
        self.assertIsNone(classify(self.item('Les taux des assurances augmentent'),self.watch))
    def test_macro_risk_is_not_stated_as_confirmed_crash(self):
        self.assertEqual(classify(self.item('Une bulle sur les marchés ?'),[])['topic'],'RISQUE ÉVOQUÉ')
        self.assertEqual(classify(self.item('La BCE maintient ses taux directeurs'),[])['topic'],'TAUX DIRECTEURS')
    def test_company_priority_and_one_macro_per_brief(self):
        items=[self.item('Crise bancaire en vue','a'),self.item('La BCE baisse ses taux','b'),self.item('Example Inc publie ses résultats','c')]
        selected=select([(self.feed,items)],self.state,self.now,self.watch)
        self.assertEqual([x['id'] for x in selected],['c','b'])
    def test_no_update_of_delivered_queue_when_upload_fails(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(rss,'STATE_PATH',Path(tmp)/'state.json'),patch('briefing.watchlist_from_env',return_value=self.watch),patch('briefing.render',return_value=[]),patch.object(rss,'discord_post',side_effect=rss.PublishError('failed')):
            with self.assertRaises(rss.PublishError):publish_briefing([(self.feed,[self.item('Example Inc résultats')])],self.state,'endpoint',self.now)
            self.assertEqual(self.state['daily']['count'],0)
            self.assertNotIn('a',self.state['feeds'][self.feed['url']]['seen'])
    def test_pngs_and_daily_cap(self):
        item=self.item('Example Inc publie ses résultats');item['editorial']=classify(item,self.watch)
        cards=render([item],self.now)
        self.assertEqual(len(cards),2)
        for name,data,alt in cards:
            with Image.open(BytesIO(data)) as im:self.assertEqual(im.size,(1080,1350))
        self.state['daily']={'date':'2026-11-11','count':8}
        self.assertEqual(select([(self.feed,[item])],self.state,self.now,self.watch),[])
    def test_same_headline_across_sources_deduplicated(self):
        a=self.item('Example Inc annonce ses résultats','a');b=self.item(a['title'],'b')
        self.assertEqual(len(select([(self.feed,[a,b])],self.state,self.now,self.watch)),1)

    def test_summary_does_not_expose_private_watchlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary=Path(tmp)/'summary.md'
            with patch.dict('os.environ',{'GITHUB_STEP_SUMMARY':str(summary)}):
                execution_summary([(self.feed,[self.item('Example Inc')])],self.watch,self.state,'Publication confirmée.',1,2)
            text=summary.read_text()
            self.assertIn('Images confirmées pendant ce passage : 2',text)
            self.assertNotIn('Example Inc',text)
            self.assertNotIn('Entreprise Exemple',text)

    def test_daily_limit_is_distinguished_from_no_news(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary=Path(tmp)/'summary.md'
            with patch.dict('os.environ',{'GITHUB_STEP_SUMMARY':str(summary)}),patch.object(rss,'STATE_PATH',Path(tmp)/'state.json'),patch('briefing.watchlist_from_env',return_value=[]),patch.object(rss,'discord_post') as post:
                publish_briefing([(self.feed,[])],self.state,'endpoint',self.now)
                self.assertIn('Aucune nouvelle information ciblée éligible.',summary.read_text())
                self.state['daily']['count']=8
                publish_briefing([(self.feed,[])],self.state,'endpoint',self.now)
                self.assertIn('Plafond quotidien atteint.',summary.read_text())
                post.assert_not_called()

    def test_multipart_contains_image_and_disabled_mentions(self):
        import json
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{"id":"123","channel_id":"456"}'
        class Opener:
            def open(self,request,timeout):
                self.request=request
                return Response()
        opener=Opener()
        with patch.object(rss.urllib.request,'build_opener',return_value=opener):
            result=rss.discord_post('https://discord.com/api/webhooks/123/example?wait=true','Briefing',files=[('01.png',b'PNG-CONTENT','Description')])
        self.assertEqual(result['id'],'123')
        self.assertIn(b'name="files[0]"; filename="01.png"',opener.request.data)
        self.assertIn(b'PNG-CONTENT',opener.request.data)
        self.assertIn(b'"allowed_mentions": {"parse": []}',opener.request.data)
