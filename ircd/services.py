import hashlib, hmac, base64, json, re, sys, threading, time
from util import tor_connect
from util import tripcode
from functools import wraps



def admin(f):
    @wraps(f)
    def func(server,user,msg):
        if user != server.admin:
            user.kill('service abuse ;3')
        else:
            f(sever,user,msg)
    return func

class Service:
    def __init__(self,server):
        self.server = server
        self._log = server._log
        self.last_ping_recv = -1

    def send_num(self,num,raw):
        pass
    
    def send_notice(self,s,m):
        pass

    def send_ping(self):
        pass

    def timeout(self):
        pass

    def serve(self,server,user,msg):
        raise NotImplemented()

    def dbg(self,msg):
        self._log('DBG',msg)

    def __str__(self):
        return self.__class__.__name__

class adminserv(Service):
    
    def __init__(self,server):
        Service.__init__(self,server)
        self.nick = self.__class__.__name__

    def serve(self,server,user,msg):
        msg = msg.strip()
        passwd = None
        try:
            with open('admin.hash','r') as r:
                passwd = r.read().strip()
        except:
            pass
        if passwd is not None and user.nick == passwd:
            self.handle_line(msg)
        elif passwd is None:
            user.privmsg(self,'could not read admin.hash')
        else:
            user.kill('service abuse :3')
            
    def handle_line(self,line):
        cmd = line.lower().split(' ')[0]
        args = line.split(' ')[1:]
        if cmd == 'die':
            self.server.send_admin('server will die in 5 seconds')
            def die():
                n = 5
                for i in range(n):
                    self.server.send_global('server death in '+str(n-i))
                    time.sleep(1)
                sys.exit(0)
            threading.Thread(target=die,args=()).start()
        if cmd == 'debug':
            self.server.toggle_debug()
            self.server.send_admin('DEBUG: %s' % self.server.debug())
        if cmd == 'nerf':
            if len(args) == 1:
                if args[0] == 'off':
                    self.server.poniponi = None
                    for user in self.server.handlers:
                        user.set_mode('-P')
                elif args[0] == 'on':
                    self.server.poniponi = 'blah'
                else:
                    self.server.poniponi = args[0]
            self.server.send_admin('PONY: %s'%self.server.poniponi or 'off')
        if cmd == 'ping':
            if len(args) == 1:
                try:
                    old = self.server.pingtimeout
                    self.server.pingtimeout = int(args[0])
                    if self.server.pingtimeout < 10:
                        self.server.pingtimeout = 10
                except:
                    self.server.send_admin('not a number')
            self.server.send_admin('PING: %s seconds'%self.server.pingtimeout)
        if cmd == 'global':
            msg = line[6:]
            self.server.send_global(msg)
            self.server.send_admin('GLOBAL: %s'%msg)
        if cmd == 'count':
            self.server.send_admin('%d Users connected'%len(self.server.users.items()))
        if cmd == 'list':
            self.server.send_admin('LIST COMMAND')
            for user in self.server.users.items():
                self.server.send_admin('USER: %s %s'%user)
        if cmd == 'kline':
            self.server.send_admin('KLINE')
            for user in args:
                if not self.server.has_user(user):
                    self.server.send_admin('NO USER: %s'%user)
                user = self.server.users[user]
                user.kill('killed')
                self.server.send_admin('KILLED %s'%user)


class tripserv(Service):

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
# from linkserv import linkserv
services = {
    # 'trip':tripserv, # tripserv deprecated
    'admin':adminserv,
    #'link':linkserv,
    #'tc':tcserv
}
