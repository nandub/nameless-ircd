import hashlib, hmac, base64, json, re, sys, threading, time
from util import tor_connect
from util import tripcode
from functools import wraps
import util, base


def admin(f):
    @wraps(f)
    def func(*args,**kwds):
        user = args[2]
        server = args[1]
        if user.nick != util.get_admin_hash():
            server.kill(user,'service abuse ;3')
        else:
            f(*args,**kwds)
    return func

class Service(base.BaseObject):
    def __init__(self,server,config={}):
        base.BaseObject.__init__(self,server)
        self._log = server._log
        self.last_ping_recv = -1
        self.is_service = True
        self.config = config
        self.cmds = {}

    def send_num(self,num,raw):
        pass
    
    def send_notice(self,s,m):
        pass

    def send_ping(self):
        pass

    def timeout(self):
        pass

    def privmsg(self,user,msg):
        hook = lambda msg : user.privmsg(self,msg)
        self.serve(self.server,user,msg,hook)

    def serve(self,server,user,msg,resp_hook):
        cmd = msg.lower().split(' ')[0]
        args = msg.split(' ')[1:]
        if cmd in self.cmds:
            self.cmds[cmd](args,resp_hook)
        else:
            resp_hook('no such command: '+str(cmd))

    def dbg(self,msg):
        self._log('DBG',msg)

    def attempt(self,func,resp_hook):
        try:
            func()
        except:
            for line in traceback.format_exc().split('\n'):
                resp_hook(line)
            return False
        else:
            return True

    def __str__(self):
        return self.get_full_name()

class adminserv(Service):
    
    def __init__(self,server,config={}):
        Service.__init__(self,server,config=config)
        self.nick = self.__class__.__name__
        self.cmds = {
            'debug':self.toggle_debug,
            'denerf':self.denerf_user,
            'nerf':self.nerf_user,
            'nerf_all':self.nerf_all,
            'denerf_all':self.denerf_all,
            'ping':self.set_ping,
            'global':self.send_global,
            'count':self.count_users,
            'list':self.list_users,
            'kline':self.kline,
            'help':self.send_help
            }

    def handle_line(self,line):
        class dummy:
            def __init__(self):
                self.nick = util.get_admin_hash()
            def privmsg(self,*args,**kwds):
                pass
        self.privmsg(dummy(),line)

    @admin
    def serve(self,server,user,line,resp_hook):
        Service.serve(self,server,user,line,resp_hook)

    def send_help(self,args,resp_hook):
        resp_hook('commands:')
        for cmd in self.cmds:
            resp_hook('- '+cmd)

    def toggle_debug(self,args,resp_hook):
        self.server.toggle_debug()
        resp_hook('DEBUG: %s' % self.server.debug())

    def nerf_user(self,args,resp_hook):
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.set_mode('+P')
                u.lock_modes()
                resp_hook('set mode +P on '+u.nick)
    def denerf_user(self,args,resp_hook):
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.set_mode('-P')
                u.unlock_modes()
                resp_hook('set mode -P on '+u.nick)

    def nerf_all(self,args,resp_hook):
        self.server.send_global('Global +P Usermode Set')
        for u in self.server.handlers:
            u.set_mode('+P')
            u.lock_modes()
        resp_hook('GLOBAL +P')

    def denerf_all(self,args,resp_hook):
        self.server.send_global('Global -P Usermode Set')
        for u in self.server.handlers:
            u.unlock_modes()
            u.set_mode('-P')
        resp_hook('GLOBAL -P')

    def set_ping(self,args,resp_hook):
        server = self.server
        if len(args) == 1:
            try:
                old = server.pingtimeout
                server.pingtimeout = int(args[0])
                if server.pingtimeout < 10:
                    server.pingtimeout = 10
            except:
                resp_hook('not a number')
        resp_hook('PING: %s seconds'%server.pingtimeout)

    def send_global(self,args,resp_hook):
        msg = ' '.join(args)
        self.server.send_global(msg)
        resp_hook('GLOBAL: %s'%msg)
    
    def count_users(self,args,resp_hook):
        resp_hook('%d Users connected'%len(self.server.users.items()))
        
    def list_users(self,args,resp_hook):
        resp_hook('LIST COMMAND')
        for user in self.server.users:
            resp_hook('USER:'+str(user))

    def kline(self,args,resp_hook):
        resp_hook('KLINE')
        for u in args:
            if u not in self.server.users:
                resp_hook('NO USER: '+str(u))
            u= server.users[u]
            u.kill('kline')
            resp_hook('KILLED '+str(u))


class tripserv(Service):
    @util.deprecate
    def __init__(self,server):
        Service.__init__(self,server)
        self.nick = self.__class__.__name__
        self._help = 'Useage: /msg tripserv username#tripcode'

    def hash_trip(self,name,trip):
        return tripcode(name,trip)
        # return '%s|%s!tripcode@nameless'%(name,tripcode(trip,self.salt))

    def serve(self,server,user,msg):
        while True:
            pmsg = msg.replace('  ',' ')
            if msg == pmsg:
                break
            msg = pmsg

        if msg.strip() == 'off':
            self.server.change_nick(user,user._rand_nick(6))
            return
        p = msg.split(' ')
        if len(p) < 1:
            user.privmsg(self,self._help)
            return
        
        msg = ''
        if p[0].count('#') != 1:
            user.privmsg(self,'User tripcode format: user#tripcode')
            return
        pp = p[0].split('#')
        if len(pp) > 1:
            self.tripcode(user,pp[0],pp[1])
        else:
            user.privmsg(self,'bad tripcode format')

    def tripcode(self,user,name,code):
        trip = self.hash_trip(name,code)
        l = len(trip)
        trip = trip[:l/2]
        self.server.change_nick(user,'%s|%s'%(name,trip))

# from tcserv import tcserv
from linkserv import linkserv
services = {
    #'tripserv':tripserv, # tripserv deprecated
    'adminserv':adminserv,
    'linkserv':linkserv,
    #'tcserv':tcserv
}
