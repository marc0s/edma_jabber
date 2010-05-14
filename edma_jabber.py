# -*- coding: utf-8 -*-
##############################################################################
#
#    edma_jabber.py - (c) 2009 Marcos De Vera Piquero <marc0s@fsfe.org>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import fields, osv
import pooler

from threading import Thread
import netsvc
import tools

from jabberbot import JabberBot
import datetime

class EDMABotSessions():
    """Here we store the authenticated sessions with the Bot.
    The _sessions dict will have as keys the jids of the authenticated users.
    The content of each position of the dict will be another dict with the
    following structure:
        { 'logintime': datetime , 'uid': int , 'password': str }
    """

    _sessions = {}

    def login(self, jid, logintime, uid, password):
        self._sessions[jid] = { 'logintime': logintime, 'uid': uid, 'password': password }

    def logout(self, jid):
        try:
            del self._sessions[jid]
        except KeyError:
            pass
    
    def sessions(self):
        return self._sessions
  
    def get_session(self, jid):
        return self._sessions[jid]

class EDMABot(JabberBot):
    logger = netsvc.Logger()
    _logged_in = False
    _sessions = EDMABotSessions()
    _commonService = netsvc.LocalService('common')
    _objectService = netsvc.LocalService('object')

    def log(self, s):
        """Overloads JabberBot.log to use the OpenERP logging service.
        """
        self.logger.notifyChannel("jabber", netsvc.LOG_INFO, s)

    def elog(self, s):
        self.logger.notifyChannel("jabber", netsvc.LOG_ERROR, s)

    def set_db(self, dbname):
        """Sets de database to use.
        """
        self._dbname = dbname

    def set_startuptime(self, time):
        """Sets the server startup time.
        """
        self.startup = time
 
    def secure(fn):
        """Defines a decorator to be used by the methods that need
        a valid authentication.
        """
        def _check(*args, **kwargs):
            # check if the From: of the message has been authenticated
            # args[0] is self
            if args[0]._sessions.sessions().has_key(args[1].getFrom()):
                return fn(*args, **kwargs)
            else:
                args[0].log("Not logged in.")
                return "This action requires you to be logged in."
        return _check

    def bot_login(self, mess, args):
        """Executes the login process.
        It expects only two parameters: user and password
        """
        (user, password) = args.split()[0:2]
        uid = self._commonService.login(self._dbname, user, password)
        if uid:
            self._sessions.login(mess.getFrom(), datetime.datetime.now(), uid, password)
            if self._sessions.sessions().has_key(mess.getFrom()):
                self.log("Login successful for user %s" % (mess.getFrom(),))
                return "You're now logged in."
            else:
                self.elog("Somethin nasty occured with the login process of %s." % (mess.getFrom(),))
                return "Something nasty occured with your login process. Try again."
        else:
            self.elog("Failed login for user %s." % (mess.getFrom(),))
            return "The supplied credentials were not valid."

    def o_execute(self, jid, module, action, params):
        """Executes 'action' on 'module' via the objectService
        """
        w = self._sessions.get_session(jid)
        if params:
            return self._objectService.execute(self._dbname, w['uid'], w['password'], module, action, params)
        return self._objectService.execute(self._dbname, w['uid'], w['password'], module, action)

    def bot_logout(self, mess, args):
        """Executes the logout process.
        """
        self._sessions.logout(mess.getFrom())
        self.log("User %s logged out." % (mess.getFrom(),))
        return "You've been logged out."

       
    def bot_time(self, mess, args):
        """Returns the current server time.
        """
        self.log("time called")
        return str(datetime.datetime.now())

    @secure
    def bot_serverinfo(self, mess, args):
        """Returns the server version.
        """
        import release
        return ("Server version: %s\nUptime: %s " % (release.version,datetime.datetime.now() - self.startup))

    @secure
    def bot_search(self, mess, args):
        """Does a search. The message format is:
        search module search_args
        where search_args is like
        [('field','operator','value'), ... ]
        """
        (module, search_args) = args.split()[0:2]
        self.log("bot_search:%s:%s" % (module,search_args))
        try:
            res = self.o_execute(mess.getFrom(), module, 'search', eval(search_args))
            if len(res):
                return self.o_execute(mess.getFrom(), module, 'read', res)
            return "No results found."
        except Exception, e:
            print e
            self.elog("The server failed to parse your query, check it.")
            return "The server failed to parse your query, check it."

    @secure
    def bot_execute(self, mess, args):
        """Calls the execute method.
        """
        (module, method, m_args) = args.split()[0:3]
        self.log("bot_execute:%s:%s:%s" % (module,method,m_args))
        try:
            res = self.o_execute(mess.getFrom(), module, method, eval(m_args))
            if len(res):
                return res
            return "No results"
        except Exception, e:
            print e
            self.elog("The server failed to parse your query, check it.")
            return "The server failed to parse your query, check it."

    @secure
    def bot_update_modules_list(self, mess, args):
        """Updates the modules list.
        """
        self.log("bot_update_modules_list")
        try:
            (updated, _new) = self.o_execute(mess.getFrom(), 'ir.module.module','update_list', None)
            return "%s modules updated and %s new modules." % (updated, _new)
        except Exception, e:
            print e
            self.elog("update_modules_list:%s" % (e,))
            return "The server failed to parse your query, check it."

    @secure
    def bot_install_module(self, mess, args):
        """Installs a module.
        """
        self.log("bot_install_module")
        modules = args.split(',')
        mod_obj = self.pool.get('ir.module.module')
        try:
            for m in modules:
                mod_obj
        except:
            pass

    def unknown_command(self, mess, cmd, args):
        """Returns an error message.
        """
        self.elog("Unknown command requested: %s" % (cmd,))
        return "Command not found."

class edma_jabber(osv.osv):
    _name = "edma.jabber"
    _description = "EDMA Jabber"
    _columns = {
        'name': fields.char('JID',size=255),
        'password': fields.char('Password',size=255),
        'server': fields.char('Server', size=255),
        'port': fields.integer('Port'),
        'secure': fields.boolean('Secure'),
        'resource': fields.char('Resource', size=255),
    }

    _defaults = {
      'port': lambda *a: 5222,
      'secure': lambda *a: False,
    }
    
edma_jabber()

class JabberBot(Thread):
    def __init__(self):
        Thread.__init__(self)

    def set_startuptime(self, time):
        self.startup = time

    def run(self):
        pool = osv.pooler.get_pool(tools.config['db_name'])
        cr = osv.pooler.get_db(tools.config['db_name']).cursor()
        # dirty hack while we discover the problem here ...
        import time
        time.sleep(1)
        gjobj = pool.get('edma.jabber')
        # TODO stop using a hardcoded uid. 
        ids = gjobj.search(cr, 1, [])
        if len(ids):
            gj = gjobj.browse(cr, 1, ids[0])
            bot = EDMABot(gj.name, gj.password, res=gj.resource, server=gj.server, port=gj.port, secure=gj.secure)
            bot.set_db(tools.config['db_name'])
            bot.set_startuptime(self.startup)
            bot.serve_forever()
        else:
            print("No configuration found in the database!")

tools.config['jabber'] = True
if tools.config['jabber']:
    jabber = JabberBot()
    jabber.set_startuptime(datetime.datetime.now())
    jabber.start()

