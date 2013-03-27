# -*- coding: utf-8 -*-

from asynchat import async_chat
from asyncore import dispatcher
from time import time as now
from time import sleep
from random import randint as rand
from threading import Thread
import user
User = user.User
import socket,asyncore,base64,os,threading,traceback, json
import services, util, channel
from util import trace

BaseUser = user.BaseUser


class multiserver_dict:
    
    def __init__(self,attr):
        self.servs = []
        self.attr = attr

    def __iter__(self):
        l = []
        for serv in self.servs:
            for i in getattr(serv,self.attr):
                l.append(i)
        return iter(l)

    def add_serv(self,serv):
        if serv not in self.servs:
            self.servs.append(serv)

    def del_serv(self,serv):
        if serv in self.servs:
            self.servs.remove(serv)

class _user(async_chat):
    '''
    async_chat user object
    base class that implements sending for async_chat
    '''
    def __init__(self,sock):
        async_chat.__init__(self,sock)
        self.set_terminator('\r\n')
        self.buffer = ''
        self.lines = []
        self.hlimit = 20

    def collect_incoming_data(self,data):
        
        self.buffer += data
        # if too long close line
        if len(self.buffer) > 1024:
            self.close_when_done()
    @trace
    def found_terminator(self):
        '''
        got line
        '''
        b = self.buffer
        self.buffer = ''
        # flood control
        t = int(now())
        self.lines.append((b,t))
        # keep history limit 
        while len(self.lines) > self.hlimit:
            self.lines.pop()

        # check lines for flood
        if self.check_flood(self.lines):
            self.send_raw(':floodserv!service@'+self.server.name+' NOTICE '+str(self)+
                          " :You Have been ignored for flooding, plz don't kthx")
            if self.server.flood_kill:
                if hasattr(self,'kill'):
                    self.kill('floodkill')
                else:
                    self.close()
        else:
            # inform got line
            self.handle_line(b)
        

    def send_msg(self,msg):
        '''
        send a message via backend
        '''
        # filter unicode
        msg = util.filter_unicode(msg)
        # screw unicode :p
        self.ascii_send_msg(msg.encode('ascii'))
    @trace
    def ascii_send_msg(self,msg):
        '''
        push a line to be sent
        '''
        self.push(msg+'\r\n')


class User(_user,BaseUser):
    '''
    Local User object, a locally connected user
    Inherits async_chat user and the Abstract User
    '''
    def __init__(self,sock,server):
        BaseUser.__init__(self,server)
        _user.__init__(self,sock)
        self._check_counter = 0
        self._check_interval = 5
        #self.check_flood = lambda lines : self._inc_check_counter() or self._check_counter % self._check_interval == 0 and server.check_flood(lines)
        self.check_flood = server.check_flood

    def _inc_check_counter(self):
        self._check_counter += 1

    def handle_error(self):
        self.server.handle_error()
        self.handle_close()
    
    def handle_close(self):
        self.close_user()
        self.close()


class Server(dispatcher):
    '''
    main server object
    '''
    @trace
    def __init__(self,addr,name,ipv6=False,do_log=False,poni=None,configs={}):
        self._no_log = not do_log
        self.poniponi = poni
        dispatcher.__init__(self)
        af = ( not ipv6 and socket.AF_INET ) or socket.AF_INET6 
        self.create_socket(af,socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(addr)
        self.listen(5)
        self.configs = configs
        self.admin_backlog = []
        self.handlers = []
        self.admin = None
        self.name = name

        self.limits = {
            'nick':5,
            'topic':5,
            'privmsg&':5,
            'privmsg#':5,
            'join':10,
            }

        self.flood_kill = False
        
        # flood interval in seconds
        self.flood_interval = 10
        # lines per interval
        self.flood_lpi = 20
        # bytes per interval
        self.flood_bpi = 1024
        # topic limit
        self.topic_limit = 60

        self.chans = dict()
        self.users = dict()
        self.pingtimeout = 60 * 5
        self.ping_retry = 2
        self._check_ping = True
        self.whitelist = []
        self._check_ping = True
        try:
            self.load_wl()
        except:
            self.handle_error()
        self.on =True
        
        for k in self.configs:
            self.on_new_user(services.services[k](self,config=self.configs[k]))


        def ping_loop():
            while self.on:
                self.check_ping()
                sleep(5)
                
        t = Thread(target=ping_loop,args=())
        self.threads = [t]
    @trace
    def load_wl(self):
        '''
        load whitelist for mode +P
        '''
        with open('whitelist.txt') as f:
            self.whitelist = json.load(f)
    @trace
    def check_ping(self):
        '''
        check for ping timeouts
        '''
        tnow = int(now())
        for user in self.handlers:
            if tnow - user.last_ping_recv > self.pingtimeout:
                self.nfo('timeout '+str(user))
                if user in self.handlers:
                    self.handlers.remove(user)
                user.timeout()
                
            elif tnow - user.last_ping_send > self.pingtimeout / 2:
                user.send_ping()
        
    @trace
    def toggle_debug(self):
        '''
        toggle debug mode
        '''
        self._no_log = not self._no_log
    @trace
    def debug(self):
        '''
        check for debug mode
        '''
        return not self._no_log
    @trace
    def inform_links(self,data):
        if 'linkserv' in self.users:
            self.users['linkserv'].inform_links(data)
        else:
            self.dbg('no linkserv')
    @trace
    def check_flood(self,lines):
        '''
        given a list of (data, timestamp) tuples
        check for "flooding"
        '''
        a = {}
        for line , tstamp in lines:
            tstamp /= self.flood_interval
            if tstamp not in a:
                d = dict(self.limits)
                d['bytes'] = 0
                d['lines'] = 0
                a[tstamp] = d
                
            d = a[tstamp]
            d['bytes'] += len(line)
            d['lines'] += 1
            # check for flooding bytes wise
            if d['bytes'] >= self.flood_bpi:
                return True
            # check for flooding line wise
            elif d['lines'] >= self.flood_lpi:
                return True
            # check for flooding command wise
            for k in self.limits:
                line =  line.lower().replace(':',' ').replace(' ','')
                if line.startswith(k):
                    d[k] -= 1
                    if d[k] <= 0:
                        return True
        del a
        return False

    def nfo(self,msg):
        self._log('NFO',msg)

    @util.deprecate
    def _fork(self,func):
        '''
        DEPRECATED
        '''
        def f():
            try:
                func()
            except:
                self.err(traceback.format_exc())
            
        return threading.Thread(target=f,args=())
    @trace
    def motd(self):
        '''
        load message of the day
        '''
        d = ''
        with open('motd','r') as f:
            d += f.read()
        return d
    @trace
    def kill(self,user,reason):
        '''
        kill a user with a reason
        '''
        user.kill(user)
        self.close_user(user)

    @trace
    def infom_links(self,type,src,dst,msg):
        pass

    @util.deprecate
    def privmsg(self,user,dest,msg):
        '''
        tell the server to send a private message from user to destination
        dest with the contents of the message being msg
        
        dest can be a channel or nickname
        '''
        self.inform_links('privmsg',user,dest,msg)
        onion = user.nick.endswith('.onion')
        # someone is complaining about this
        # not really needed regardless
        #self.dbg('privmsg %s -> %s -- %s'%(user.nick,dest,
        #                                   util.filter_unicode(msg)))
        if (dest[0] in ['&','#'] and not self._has_channel(dest)) or (dest[0] not in ['&','#'] and dest not in self.users):
            user.send_num(401,'%s :No such nick/channel'%dest)
            return
        if dest[0] in ['#','&']: # is a channel ?
            dest =  dest.lower()
            dest in user.chans and self.chans[dest].privmsg(user,msg)
        else: # not a channel, is a user
            dest in self.users and self.users[dest].privmsg(user,msg)

    @util.deprecate
    def set_admin(self,user):
        '''
        set server admin to be user
        '''
        if self.admin is not None:
            self.admin.privmsg(self.service['admin'],'no longer oper')
        self.admin = user
        self.admin.privmsg(self.service['admin'],'you are now oper ;3')
    @trace
    def send_global(self,msg):
        '''
        send a global message to all users connected
        '''
        for user in self.handlers:
            user.send_notice('globalserv!service@nameless',msg)
    @trace
    def has_service(self,serv):
        '''
        check if a service exists
        '''
        return serv.lower() in self.service.keys()

    # we don't really need this right now
    #def has_nick(self,nick):
    #    return nick.split('!')[0] in self.users.keys()
    

    def _log(self,type,msg):
        if self._no_log and type.lower() not in ['nfo','err','ftl']:
            return
        print type, msg
        
        #with open('log/server.log','a') as f:
        #    f.write('[%s -- %s] %s\n'%(type,now(),msg))

    @trace
    def send_motd(self,user):
        '''
        send the message of the day to user
        '''
        user.send_num(375,':- %s Message of the day -'%self.name)
        for line in self.motd().split('\n'):
            user.send_num(372, ':- %s '%line)
        user.send_num(376, ':- End of MOTD command')
    @trace
    def send_welcome(self,user):
        '''
        welcome user to the server
        does not add user to users list
        '''
        # send intial 001 response
        if not user.is_torchat:
            user.send_num('001','Welcome to the Internet Relay Network %s'%str(user))
            user.send_num('002','Your host is %s, running version :nameless-ircd'%self.name)
            user.send_num('003','This server was created a while ago')
            user.send_num('004','%s nameless-ircd Pu x'%self.name)
        # send the motd
        self.send_motd(user)
        # if there is an after_motd hook function to call , call it
        if hasattr(user,'after_motd') and user.after_motd is not None:
            user.after_motd()
        if user.nick.endswith('.onion'):
            return
        # user has been welcomed
        user.welcomed = True
        # set +P as needed
        if self.poniponi is not None:
            user.you_poni_now()

    def dbg(self,msg):
        '''
        print debug message
        '''
        self._log('DBG',msg)
        
    @util.deprecate
    def _iter(self,f_iter,f_cycle,timesleep):
        while self.on:
            f_cycle()
            for nick,user in self.users.items():
                try:
                    f_iter(user)
                except:
                    self.handle_error()
            sleep(timesleep)
    
    @trace
    def err(self,msg):
        '''
        print error message
        '''
        self._log('ERR',msg)
        try:
            with open('errors.log','a') as a:
                a.write('incodent at %d'%now())
                a.write('\n')
                a.write(msg)
                a.write('\n')
        except:
             traceback.print_exc()

    @trace
    def handle_error(self):
        '''
        handle error
        '''
        #traceback.print_exc()
        self.err(traceback.format_exc())
    @trace
    def on_user_closed(self,user):
        '''
        called when a user closes their connection
        '''
        if user.nick.endswith('serv'):
            return
        if user in self.handlers:
            self.handlers.remove(user)
        if user.nick in self.users:
            self.users.pop(user.nick)

    @util.deprecate
    def close_user(self,user):
        '''
        DO NOT USE
        '''
        # services do not close
        if user.nick.endswith('serv'):
            return
        # close user
        try:
            user.close_user()
            if user in self.handlers:
                self.handlers.remove(user)
            del user
        except:
            self.err(traceback.format_exc())

    @trace
    def new_channel(self,chan):
        '''
        make a new channel
        '''
        assert chan[0] in ['&','#'] and len(chan) > 1
        if chan[1] == '.':
            assert len(chan) > 2
        if chan in self.chans:
            return
        self.chans[chan] = channel.Channel(chan,self)
        

    @util.deprecate
    def pongloop(self):
        def check_ping(user):
            if now() - user.last_ping_recv > self.pingtimeout:
                self.dbg('ping timeout %s'%user)
                user.timeout()
        def nop():
            pass
        self._iter(check_ping,nop,self.pingtimeout)

    @util.deprecate
    def send_admin(self,msg):
        '''
        send a message to the server admin
        '''
        for line in str(msg).split('\n'):
            if self.admin is None:
                # send to backlog
                self.admin_backlog.append(msg)
            else:
                # privmsg the admin
                while len(self.admin_backlog) > 0:
                    self.admin.privmsg('adminserv!service@%s'%self.name,self.admin_backlog.pop(0))
                self.admin.privmsg('adminserv!service@%s'%self.name,line)
            # save to admin.log file
            with open('log/admin.log','a') as a:
                a.write('%s -- %s'%(now(),msg))
                a.write('\n')
                
    @util.deprecate
    def adminloop(self):
        # wont work on windows
        if not hasattr(socket,'AF_UNIX'):
            return
        adminsock = socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        sock = 'admin.sock'
        if os.path.exists(sock):
            os.unlink(sock)
        adminsock.bind(sock)

        while self.on:
            try:
                data = adminsock.recv(1024)
                for line in data.split('\n'):
                    self.service['admin'].handle_line(line)
            except:
                self.send_admin(traceback.format_exc())
        adminsock.close()

    @util.deprecate
    def pingloop(self):
        def ping(user):
            self.dbg('ping %s'%user)
            user.send_ping()
                
        def debug():
            self.dbg('sending pings')
        self._iter(ping,debug,self.pingtimeout/self.ping_retry)
            
    @trace
    def _has_channel(self,chan):
        '''
        check if a channel exists
        '''
        return chan in self.chans.keys()
    @trace
    def on_new_user(self,user):
        '''
        called when a new user is registered
        '''
        self.dbg('New User: '+str(user))
        self.users[user.nick] = user
        if user.is_service:
            return
        self.send_welcome(user)

    @util.deprecate
    def add_user(self,user):
        '''
        add a user to the users list
        '''
        self.dbg('Adding User: %s'%user.nick)
        if user.nick in self.users:
            self.err('user %s already in users'%user)
            return
        self.users[user.nick] = user
        if user.nick.endswith('serv'):
            return
        self.send_welcome(user)

    @util.deprecate
    def has_user(self,nick):
        return nick in self.users.keys()
    @trace
    def send_list(self,user):
        '''
        send server channel list to user
        '''
        user.send_num(321,'Channel :Users  Name')
        for chan in self.chans:
            chan = self.chans[chan]
            if chan.is_invisible:
                continue
            user.send_num(322,'%s %d :%s'%(chan.name,len(chan),chan.topic or ''))
        user.send_num(323 ,':End of LIST')
    @trace
    def _add_channel(self,chan):
        '''
        make a new channel
        '''
        chan = chan.lower()
        self.dbg('New Channel %s'%chan)
        self.chans[chan] = Channel(chan,self)

    @util.deprecate
    def join_channel(self,user,chan):
        '''
        have a user join a channel
        '''
        # check for non existant channel
        if chan in user.chans:
            return
        chan = chan.lower()
        if chan[0] in ['&','#']: # is a valid name
            if not self._has_channel(chan): # new channel
                self._add_channel(chan)
                user.send_notice('chanserv!service@%s'%self.name,'new channel %s'%chan)
            # add user to lists
            self.chans[chan].joined(user)
            user.chans.append(chan)
        else: # invalid name
            user.send_notice('chanserv!service@%s'%self.name,'bad channel name: %s'%chan)
    @trace
    def reload(self):
        '''
        reload server's state
        '''
        self.load_wl()
    @trace
    def get_whitelist(self):
        '''
        get whitelist for +P
        '''
        return self.whitelist
    @trace
    def remove_channel(self,chan):
        '''
        remove channel
        '''
        chan = chan.lower()
        if chan in self.chans:
            chan = self.chans[chan]
            for user in chan.users: # inform part
                self.part_channel(user,chan.name)
            
                
                
            
    @trace
    def part_channel(self,user,chan):
        '''
        have a user part a channel with name chan
        '''
        chan = chan.lower()
        if chan in self.chans:
            self.chans[chan].user_quit(user) # send part
        self.inform_links({'src':str(user),'dst':chan,'event':'part'})
    @trace
    def change_nick(self,user,newnick):
        '''
        have user change nickname newnick
        '''
        self.dbg('server nick change %s -> %s' % (user.nick,newnick))
        if len(newnick) > 30 or newnick in self.users: # nickname too long
            newnick = user.do_nickname('')

        if user.nick not in self.users:
            self.users[user.nick] = user

        self.users[newnick] = self.users.pop(user.nick)

        # users to inform
        users = {user:None}
        for chan in user.chans:
            if chan in self.chans:
                for u in self.chans[chan].users:
                    if u not in users:
                        users[u] = None
                        
        for u in users:
            u.nick_change(user,newnick)
        self.inform_links({'src':str(user),'dst':newnick,'event':'nick'})

        # commit change
        user.nick = newnick
        user.usr = newnick
        
        self.dbg('user is now %s'%user)

    @trace
    def stop(self):
        self.on = False
    @trace
    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            sock, addr = pair
            self.handlers.append(User(sock,self))
        
    def __str__(self):
        return str(self.name)
