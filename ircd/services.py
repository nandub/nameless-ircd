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
        if user.nick in util.get_admin_hash_list():
            f(*args, **kwds)
        else:
            user.kill('service abuse ;3')
       
    return func


def deprecated(f):
    @wraps(f)
    def func(*args,**kwds):
        args[2]('deprecated function')
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
from adminserv import adminserv
services = {
    #'tripserv':tripserv, # tripserv deprecated
    'adminserv':adminserv,
    #'linkserv':linkserv,
    #'tcserv':tcserv
}
