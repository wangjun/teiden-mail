#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys, os
root_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(root_dir, 'lib'))

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp.util import run_wsgi_app 
from google.appengine.ext import db
from google.appengine.api import urlfetch
from google.appengine.api import mail
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler

import atom
import gdata.service
import gdata.alt.appengine
import gdata.calendar
import gdata.calendar.service
from dateutil.parser import parse
from dateutil.tz import *

import simplejson
import logging
import urllib,urllib2
import email.utils
from datetime import datetime,timedelta

TEIDEN = {'tokyo01':'creco.net_j54hnj1scpsa0oasqma0v0n4h0%40group.calendar.google.com',
          'tokyo02':'creco.net_r95i3r66pe00a0al0ebcgiovno%40group.calendar.google.com',
          'tokyo03':'creco.net_q9gq2bnptmpaq30f9brd90stms%40group.calendar.google.com',
          'tokyo04':'creco.net_eigugc9emgdjj3vaphue418d74%40group.calendar.google.com',
          'tokyo05':'creco.net_h5elta8oltnk8gev750mubpbok%40group.calendar.google.com',
          'tohoku01':'creco.net_9uuvoinoa1tlp4nr6er4ucf5bk%40group.calendar.google.com',
          'tohoku02':'creco.net_4fsitgneubdkl1r29qq2lvarb4%40group.calendar.google.com',
          'tohoku03':'creco.net_4ke1v2eg3ahupfv1ttlcpkuf7c%40group.calendar.google.com',
          'tohoku04':'creco.net_f6b4fse1t81dkfcsjhodg4qc38%40group.calendar.google.com',
          'tohoku05':'creco.net_stn1svt8kuh981gvaimjfrut2o%40group.calendar.google.com',
          'tohoku06':'creco.net_l0q9vrkie28pmn54vbspf9qpcg%40group.calendar.google.com',
          'tohoku07':'creco.net_gs9b2qbth537rttjl8v8tp8l2o%40group.calendar.google.com',
          'tohoku08':'creco.net_tblrqleja7sidltk4v41u8jpfk%40group.calendar.google.com'}

GROUP = TEIDEN.keys()
GROUPNAME = {'tokyo01':'東京電力第１グループ',
              'tokyo02':'東京電力第２グループ',
              'tokyo03':'東京電力第３グループ',
              'tokyo04':'東京電力第４グループ',
              'tokyo05':'東京電力第５グループ',
              'tohoku01':'東北電力第１グループ',
              'tohoku02':'東北電力第２グループ',
              'tohoku03':'東北電力第３グループ',
              'tohoku04':'東北電力第４グループ',
              'tohoku05':'東北電力第５グループ',
              'tohoku06':'東北電力第６グループ',
              'tohoku07':'東北電力第７グループ',
              'tohoku08':'東北電力第８グループ'}


# model
class User(db.Model):
    email = db.StringProperty(required=True)
    group = db.StringProperty(required=True,choices=GROUP)
    created_at = db.DateTimeProperty(auto_now_add=True)
    updated_at = db.DateTimeProperty(auto_now=True)

class Event(db.Model):
    title = db.StringProperty(required=True)
    content = db.TextProperty()
    group = db.StringProperty(required=True)
    start_time = db.DateTimeProperty(required=True)
    end_time = db.DateTimeProperty(required=True)
    status = db.StringProperty(default='Waiting',choices=['Waiting','Working','Completed'])
    cancel = db.BooleanProperty(default=False)

# view
class MainHandler(webapp.RequestHandler):
    def get(self):
        template_values = {}
        path = os.path.join(os.path.dirname(__file__), 'index.html')
        self.response.out.write(template.render(path, template_values))

# mail
class MailHandler(InboundMailHandler):
    def receive(self, mail_message):
        logging.info("Received a message from: %s to: %s" % (mail_message.sender,mail_message.to))
        sender = email.utils.parseaddr(mail_message.sender)[1]
        to = email.utils.parseaddr(mail_message.to)[1]
        group = to.split('@')[0]

        user = User.get_by_key_name("%s:%s" % (group,sender))
        if user:
            user.delete()
            mail.send_mail(sender='teidenmail@gmail.com',
                           to=sender,
                           subject="[停電メール] %s(%s)は削除されました" % (sender,GROUPNAME[group]),
                           body="""
%s(%s)を削除しました。

%sに空メールを送信すれば再登録できますので、また気になったらどうぞ。

停電メール
http://teiden-mail.appspot.com/

""" % (sender,GROUPNAME[group],to))

        else:
            user = User.get_or_insert(key_name=("%s:%s" % (group,sender)),email=sender,group=group)
            mail.send_mail(sender='teidenmail@gmail.com',
                           to=sender,
                           subject="[停電メール] %sは%sとして登録されました" % (sender,GROUPNAME[group]),
                           body="""
%sは%sとして登録されました。
今後、停電開始と停電終了の３０分ぐらい前にメールでお知らせすると思いますが、あまり信用しないで気楽にご利用ください。

登録を解除する場合は、%sに空メールを送信してください。

停電メール
http://teiden-mail.appspot.com/

""" % (sender,GROUPNAME[group],to))

# cron
class NotifyStartingCron(webapp.RequestHandler):
    def get(self):

        cutoff = datetime.now()+timedelta(minutes=30)
        query = Event.all().filter('start_time <', cutoff).filter('status =','Waiting')
        events = query.order('start_time').fetch(10)

        if events:
            logging.info('notify_starting(events): '+str(len(events)))

        for ev in events:
            logging.info('notify_starting(event): '+ev.group)
            if ev.start_time <= datetime.now():
                ev.status = 'Working'
                ev.put()
                continue

            query = User.all().filter('updated_at <=', (ev.start_time-timedelta(minutes=30))).filter('group =',ev.group)
            users = query.fetch(1000)
            logging.info('notify_starting(users): '+str(len(users)))

            start_time = (ev.start_time + timedelta(hours=9)).strftime("%H時%M分")
            end_time = (ev.end_time + timedelta(hours=9)).strftime("%H時%M分")

            if ev.cancel:
                ev.status = 'Completed'
                subject = "[停電メール] %sでの%sからの計画停電は中止されました" % (GROUPNAME[ev.group],start_time)
                body = """
%sでの%sからの計画停電は中止されました。

登録を解除する場合は、%sに空メールを送信してください。

停電メール
http://teiden-mail.appspot.com/

""" % (GROUPNAME[ev.group],start_time,ev.group.encode('utf-8')+'@teiden-mail.appspotmail.com')

            else:
                ev.status = 'Working'
                subject = "[停電メール] %sにおいて%sより計画停電を開始します" % (GROUPNAME[ev.group],start_time)
                body = """
%sにおいて%sより計画停電を開始します。
終了時刻は%sごろです。終了前にまた連絡します。

登録を解除する場合は、%sに空メールを送信してください。

停電メール
http://teiden-mail.appspot.com/

""" % (GROUPNAME[ev.group],start_time,end_time,ev.group.encode('utf-8')+'@teiden-mail.appspotmail.com')

            logging.info('subject: '+subject)
            logging.info('body: '+body)

            for lst in [users[i:i+50] for i in range(0, len(users), 50)]:
                db.put(users)
                logging.info('notify_starting(users_each): '+str(len(lst)))
                mail.send_mail(sender='teidenmail@gmail.com',
                               to='teidenmail@gmail.com',
                               bcc=[user.email for user in lst],
                               subject=subject,
                               body=body)

            ev.put()


class NotifyEndingCron(webapp.RequestHandler):
    def get(self):
        cutoff = datetime.now()+timedelta(minutes=30)
        query = Event.all().filter('end_time <', cutoff).filter('status =','Working')
        events = query.order('end_time').fetch(10)

        if events:
            logging.info('notify_ending(events): '+str(len(events)))

        for ev in events:
            logging.info('notify_ending(event): '+ev.group)
            if ev.end_time <= datetime.now():
                ev.status = 'Completed'
                ev.put()
                continue

            query = User.all().filter('updated_at <=', (ev.end_time-timedelta(minutes=30))).filter('group =',ev.group)
            users = query.fetch(1000)

            logging.info('notify_ending(users): '+str(len(users)))

            end_time = (ev.end_time + timedelta(hours=9)).strftime("%H時%M分")
            next_event = Event.all().filter('start_time >',ev.start_time).filter('group =',ev.group).order('start_time').fetch(1)
            next_time = None
            if next_event:
                next_time = (next_event[0].start_time + timedelta(hours=9)).strftime("%m月%d日%H時%M分")
            for lst in [users[i:i+50] for i in range(0, len(users), 50)]:
                db.put(lst)
                logging.info('notify_ending(users_each): '+str(len(lst)))
                mail.send_mail(sender='teidenmail@gmail.com',
                               to='teidenmail@gmail.com',
                               bcc=[user.email for user in lst],
                               subject="[停電メール] %sにおいて%sに計画停電が終了します" % (GROUPNAME[ev.group],end_time),
                               body="""
%sにおいて%sに計画停電を終了します。
次回の計画停電は%sです。また連絡します。

登録を解除する場合は、%sに空メールを送信してください。

停電メール
http://teiden-mail.appspot.com/

""" % (GROUPNAME[ev.group],end_time,(next_time or '未定'),ev.group.encode('utf-8')+'@teiden-mail.appspotmail.com'))

            ev.status = 'Completed'
            ev.put()


class UpdateScheduleCron(webapp.RequestHandler):
    def get(self):

        calendar_service = gdata.calendar.service.CalendarService()
        for group,user in TEIDEN.iteritems():
            uri = "/calendar/feeds/%s/public/full" % user
            feed = calendar_service.GetCalendarEventFeed(uri=uri)
            logging.info('update_schedule(feeds): %s(%d)' % (group,len(feed.entry)))
            for an_event in feed.entry:
                start_time = parse(an_event.when[0].start_time)
                end_time = parse(an_event.when[0].end_time)
                if start_time < (datetime.now(tzoffset(None, 32400)) + timedelta(minutes=60)):
                    continue
                event = Event(key_name=an_event.id.text,
                              title=unicode(an_event.title.text,'utf-8'),
                              content=unicode((an_event.content.text or ' '),'utf-8'),
                              group=group,
                              cancel=(True if an_event.title.text.startswith('※中止') else False),
                              start_time=start_time,
                              end_time=end_time)
                event.put()


application = webapp.WSGIApplication([('/', MainHandler),
                                      ('/worker/notify_starting', NotifyStartingCron),
                                      ('/worker/notify_ending', NotifyEndingCron),
                                      ('/worker/update_schedule', UpdateScheduleCron),
                                      MailHandler.mapping()],debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()
