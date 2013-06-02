# -*- coding: utf-8 -*-

from asynchat import async_chat
from asyncore import dispatcher
from time import time as now
from time import sleep
from random import randint as rand
from threading import Thread
import user
User = user.User
import socket,asyncore,base64,os,threading,traceback, json,sys
import services, util, channel, flood
from util import trace, locking_dict

BaseUser = user.BaseUser



class _user(async_chat):
    '''
    async_chat user object
    base class that implements sending for async_chat
    '''
    def __init__(self,sock):
        async_chat.__init__(self,sock)
        self.set_terminator(b'\r\n')
        self.buffer = []
        self.lines = []
        
    def _buffsize(self):
        ret = 0
        for part in self.buffer:
            ret += len(part)
        return ret
        
    def collect_incoming_data(self,data):
        self.buffer.append(data)
        # if too long close line
        if self._buffsize() > 1024: self.close_when_done()
    @trace
    def found_terminator(self):
        '''
        got line
        '''
        b = b''.join(self.buffer)
        b = b.decode('utf-8',errors='replace')
        self.buffer = []
        # flood control
        t = int(now())
        self.lines.append((b,t))
        # keep history limit 
        while len(self.lines) > self.server.flood_interval * 2:
            self.lines.pop()

        # check lines for flood
        if self.check_flood(self.lines):
            if self.server.flood_kill:
                if hasattr(self,'kill'):
                    self.kill('floodkill')
                else:
                    self.close()
        else:
            #inform got line
            self.handle_line(b)
            

    def send_msg(self,msg):
        '''
        send a message via backend
        '''
        # filter unicode
        msg = util.filter_unicode(msg)
        # screw unicode :p
        # or not
        self.send_bytes(msg.encode('utf-8',errors='replace'))

    @trace
    def send_bytes(self,msg):
        '''
        push a line to be sent
        '''
        if msg is not None:
            self.push(msg)
            self.push(b'\r\n')

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
        try:
            self.close_user()
        except:
            raise
        finally:
            self.close_when_done()

    def __str__(self):
        return self.get_full_name()
        

    def __unicode__(self):
        return unicode(self.get_full_name(),'utf-8')

class Server(dispatcher):
    '''
    main server object
    '''
    @trace
    def __init__(self,addr,name,ipv6=False,do_log=False,poni=None,configs={},link_auth=False):
        self._no_log = not do_log
        self.poniponi = poni
        self.flood = flood.flood()
        self.flood.choke = self.flood_choke
        self.flood.unchoke = self.flood_unchoke
        self.flooders = locking_dict()
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

        self.require_auth = link_auth

        limits = {
            'nick':5,
            'topic':5,
            'privmsg&':5,
            'privmsg#':5,
            'join':10,
            }
        self.limits = locking_dict(limits)
        self.flood_kill = False
        # flood interval in seconds
        self.flood_interval = 10
        # lines per interval
        self.flood_lpi = 20
        # bytes per interval
        self.flood_bpi = 1024
        # topic limit
        self.topic_limit = 60

        self.chans = locking_dict()
        self.users = locking_dict()
        self.pingtimeout = 60 * 5
        self.ping_retry = 2
        self._check_ping = True
        self.whitelist = []
        self._check_ping = True
        if util.use_3_3:
            self.handle_accepted = self._accepted_3_3
        else:
            self.handle_accept = self._accepted_2_7

        try:
            self.load_wl()
        except:
            self.handle_error()
        self.on =True
        
        for k in self.configs:
            self.on_new_user(services.services[k](self,config=self.configs[k]))

        def ping_loop():
            while self.on:
                try:
                    self.check_ping()
                except:
                    self.handle_error()
                sleep(1)
        def flood_loop():
            while self.on:
                try:
                    self.flood.tick()
                except:
                    self.handle_error()
                sleep(1)
        self.threads = []
        self.threads.append(Thread(target=ping_loop,args=()))
        self.threads.append(Thread(target=flood_loop,args=()))

    def flood_choke(self,src):
        self.nfo('floodchoke '+src)
        self.flooders[src] = int(now())
        
    def flood_unchoke(self,src):
        if src in self.flooders:
            self.nfo('floodunchoke '+src)
            del self.flooders[src]

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
        
        a = locking_dict()
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
        return False

    def nfo(self,msg):
        self._log('INFO',msg)

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
    def send_global(self,msg):
        '''
        send a global message to all users connected
        '''
        for user in self.handlers:
            user.notice('globalserv!service@'+self.name,msg)
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
        print ('['+str(int(now()))+'] '+type + ' ' + str([msg]))
        
        #with open('log/server.log','a') as f:
        #    f.write('[%s -- %s] %s\n'%(type,now(),msg))

    @trace
    def send_motd(self,user):
        '''
        send the message of the day to user
        '''
        user.send_num(375,'- %s Message of the day -'%self)
        for line in self.motd().split('\n'):
            user.send_num(372,'- %s'%line)

        user.send_num(376,'- End of MOTD command')
    
    def _send_user(self,user,data):
        data['src'] = self.name
        user.send_raw(data)

    @trace
    def send_welcome(self,user):
        '''
        welcome user to the server
        does not add user to users list
        '''
        # send intial 001 response
        if not user.is_torchat:
            user.send_num('001',self)
            user.send_num('002','Your host is %s, running nameless-ircd'%self)
            user.send_num('003','This server was created a while ago')
            user.send_num('004','%s nameless-ircd :x'%self)
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
        self._log('DEBUG',msg)
        
    @trace
    def err(self,msg):
        '''
        print error message
        '''
        self._log('ERROR',msg)
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
        for chan in self.chans:
            chan = self.chans[chan]
            for u in chan.users:
                if u.id == user.id:
                    chan.users.remove(user)
        if user in self.handlers:
            self.handlers.remove(user)
        if user.nick in self.users:
            self.users.pop(user.nick)
        if self.link is not None:
            self.link.quit(user,'user quit')
        user.close_when_done()

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
        chan = str(chan)
        if chan in self.chans and self.chans[chan].empty():
            self.chans.pop(chan)

    @trace
    def on_link_closed(self,link):
        pass
            

    @trace
    def change_nick(self,user,newnick):
        '''
        have user change nickname newnick
        '''
        self.dbg('server nick change '+user.nick+' -> '+newnick)
        if len(newnick) > 30 or newnick in self.users: # nickname too long
            newnick = user.do_nickname('')

        if user.nick not in self.users:
            self.users[user.nick] = user

        self.users[newnick] = self.users.pop(user.nick)

        def hook(u):
            u.nick_change(user,newnick)
        user.announce(hook)
        # commit change
        user.nick = newnick
        user.usr = newnick
        
        self.dbg('user is now %s'%user)

    @trace
    def stop(self,reason='stopping server'):
        reason = str(reason)
        self.nfo('stopping server: '+reason)
        self.send_global('server stoping: '+reason)
        self.on = False
        chans = list(self.chans.values())
        while len(self.handlers) > 0:
            self.handlers.pop().close_user()
        while len(self.threads) > 0:
            self.threads.pop().join()
        self.link.handle_close()
        self.handle_close()
        
    @trace
    def _accepted_3_3(self,sock,addr):
        if self.on:
            self.handlers.append(User(sock,self))
        else:
            sock.close()
    @trace
    def _accepted_2_7(self):
        if self.on:
            pair = self.accept()
            if pair is not None:
                sock, addr = pair
                self.handlers.append(User(sock,self))
        
    def __str__(self):
        return str(self.name)
    
