import hashlib, hmac, base64, json, re, sys, threading, time
from util import tor_connect
from util import tripcode
from functools import wraps
import util, base, user
User = user.User
locking_dict = util.locking_dict

def admin(f):
    @wraps(f)
    def func(*args,**kwds):
        user = args[2]
        server = args[1]
        l = util.get_admin_hash_list()
        if isinstance(user,User) and user.trip in l or str(user) in l:
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
        self.cmds = locking_dict()

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
        if isinstance(user,str):
            for u in self.server.users.values():
                if u.trip == user:
                    user = u
                    break
        if cmd in self.cmds:
            self.cmds[cmd](user,args,resp_hook)
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
    
    def __init__(self,server,config=None):
        Service.__init__(self,server)
        self.nick = self.__class__.__name__
        self.cmds = locking_dict({
            '?':self._help,
            'help':self._help,
            'trip':self._set_trip,
            'on':self._trip_on,
            'off':self._trip_off
            })
        self.mapping = locking_dict()

    def _help(self,user,args,hook):
        '''
        print help statement
        '''
        if len(args) == 0:
            hook('help items: '+' '.join(self.cmds.keys()))
        else:
            for arg in args:
                if arg in self.cmds:
                    hook(arg)
                    for line in self.cmds[arg].__doc__.split('\n'):
                        hook(line)
    def _set_trip(self,user,args,hook):
        '''
        set tripcode in format user#trip
        '''
        if len(args) == 0:
            hook('current tripcode: '+str(user.trip))
        else:
            self.trip_off(user)
            name , trip = tuple(args[0].split('#'))
            user.trip = self.do_trip(bytes(name+'#'+trip,'utf-8'))

    def _trip_on(self,user,args,hook):
        '''
        toggle tripcode on globally
        '''
        if user.trip is None:
            hook('please set tripcode first')
            return
        self.trip_on(user)


    def do_trip(self,nick):
        i = nick.index(b'#')
        return util.tripcode(nick[:i],nick[i+1:])


    def trip_on(self,user):
        for chan in user.chans:
            if chan in self.server.chans:
                chan = self.server.chans[chan]
                if chan.is_anon:
                    continue
                chan.add_trip(user)    
    
    def _trip_off(self,user,args,hook):
        '''
        turn tripcode off globally
        '''
        self.trip_off(user)

    def trip_off(self,user):
        for chan in user.chans:
            if chan in self.server.chans:
                chan = self.server.chans[chan]
                if chan.is_anon:
                    continue
                chan.remove_trip(user)    
        

    def hash_trip(self,name,trip):
        return tripcode(name,trip)
        # return '%s|%s!tripcode@nameless'%(name,tripcode(trip,self.salt))

# from tcserv import tcserv
from adminserv import adminserv
services = locking_dict({
    #'tripserv':tripserv,
    'adminserv':adminserv,
    #'linkserv':linkserv,
    #'tcserv':tcserv
})
