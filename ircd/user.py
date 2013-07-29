# -*- coding: utf-8 -*-
from time import time as now
from functools import wraps
from nameless import util, base
import base64, os

locking_dict = util.locking_dict

def registered(f):
    @wraps(f)
    def func(*args,**kwds):
        user = args[0]
        if user.welcomed:
            f(*args,**kwds)
        else:
            user.send_num(451,':You have not registered')
    return func

#@util.decorate
#def require_min_args(f,l):
#    @wraps(f)
#    def func(*args,**kwds):
#        user = args[0]
#        if len(args[1]) < l:
#            name = f.__name__.split('got_')[-1].upper()
#            user.send_num(461,name+' :Not Enough Parameters')
#        else:
#            f(*args,**kwds)
#    return func

class mode:
    def __init__(self,name,val):
        self.name = name
        self.set(val)


    def set(self,val):
        self.val = ( val is True and '+' ) or ( val is False and '-' ) or ( val in '+-' and val  ) or '-'

    def toggle(self):
        self.val = ( self.val == '-' and '+' ) or ( self.val == '+' and '-') or '-'

    def __str__(self):
        return self.val + self.name

class modes:
    '''
    channel mode object
    '''
    def __init__(self):
        self._modes = locking_dict()
        self._mode_lock = False

    def __getitem__(self,key):

        if key not in self._modes:
            self._modes[key] = mode(key,False)
        return self._modes[key]

    def __setitem__(self,key,val):
        if self._mode_lock:
            return
        if key in self._modes:
            if val == 'lock':
                self._modes[key].lock()
            elif val == 'unlock':
                self._modes[key].unlock()
            elif val == '-':
                del self._modes[key]
            else:
                self._modes[key].set(val)
        else:
            self._modes[key] = mode(key,val)

    def __delitem__(self,key):
        if self._mode_lock:
            return
        if key in self._modes:
            del self._modes[key]

    def __str__(self):
        m = []
        for k in self:
            if self[k] == '+':
                m.append(k)
        return '+' + ''.join(m)

    def __iter__(self):
        return self._modes.__iter__()

    def lock(self):
        self._mode_lock = True
    def unlock(self):
        self._mode_lock = False

class User(base.BaseObject):
    '''
    Abstract user object
    '''
    def __init__(self,server):
        base.BaseObject.__init__(self,server)
        self.link = server.link
        self.after_motd = None
        self.last_ping_recv = now()
        self.last_ping_send = 0
        self.usr = ''
        self.nick = ''
        self.id = self._rand_nick(6)
        self.last_ping = 0
        self.last_topic = 0
        self.chans = []
        self.modes = modes()
        self.welcomed = False
        self._allowed_chars = \
            'abcdefghijklmnopqrstuvwxyz' \
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ' \
            '0123456789_-\\[]{}`|'
        self.__str__ = self.get_full_name
        self.dbg = lambda msg: server.dbg(str(self)+' '+str(msg))
        self.notice = self.send_notice

    def handle_error(self):
        self.server.handle_error()
        self.close_when_done()

    def lock_modes(self):
        '''
        disable user from changing their modes
        '''
        self.modes.lock()
    def unlock_modes(self):
        '''
        enable user to change their modes
        '''
        self.modes.unlock()
    def send_notice(self,src,msg):
        '''
        send notice from source src with contents msg
        '''
        self.action(src,'notice',msg)

    def filter_message(self,msg):
        '''
        make filtered message for +P
        '''

        if 'P' not in self.modes:
            return msg
        out = ''
        action = False
        replacement = self.server.poniponi or 'blah'
        replacement += ' '
        wl = self.server.get_whitelist()
        if msg.startswith('\01ACTION') and msg.endswith('\01'):
            msg = msg[7:-1]
            action = True
        for word in msg.split(' '):
            if len(word) == 0:
                out += ' '
                continue
            out += util.filter_message(word,replacement,wl)
            out += ' '
        return action and '\01ACTION'+out+'\01' or out

    def privmsg(self,src,msg):
        '''
        recieve private message from source src with contents msg
        if dst is not None the destination is a channel
        '''
        src = str(src)
        self.send_raw({'src':src,'cmd':'PRIVMSG','target':self,'param':msg})

    def action(self,src,type,msg,dst=None):
        '''
        send an event from src with type type with contents msg from dst
        '''
        if dst is None:
            dst = self
        self.send_raw({'src':src,'cmd':type.upper(),'target':dst,'param':msg})


    def announce(self,msg):
        '''
        announce to all other users
        '''
        users = {self:None}
        for chan in self.chans:
            if chan in self.server.chans:
                for u in self.server.chans[chan].users:
                    if u not in users:
                        users[u] = None
        for u in users:
            if u.id == self.id:
                continue
            try:
                u.send_raw(msg)
            except:
                raise


    def close_user(self,reason='quit'):
        '''
        close user and expunge connection
        '''
        self.dbg(str(self)+' closing connection')
        reason = str(reason)
        self.announce({'src':self,'cmd':'QUIT','param':reason})
        self.server.on_user_closed(self)


    def event(self,src,type,msg):
        '''
        send event from src of type type with contents msg
        '''
        self.send_raw({'src':src,'cmd':type.upper(),'param':msg})

    def send_raw(self,data):
        '''
        send a raw line
        '''
        data = isinstance(data,str) and str(data) or util.dict_to_irc(data)
        if not 'u' in self.modes:
            data = util.filter_unicode(data)
        self.dbg(' [SEND] '+str(data))
        self.send_msg(data)

    def kill(self,reason):
        '''
        do not call directly
        use Server.kill(user,reason) instead
        '''
        self.notice('killserv!killserv@'+str(self.server.name),'Your connection was killed: '+str(reason))
        self.close_user('Killed: '+reason)

    def on_pong(self,pong):
        '''
        called when we recieve a pong
        '''
        self.last_ping_recv = now()

    def on_ping(self,param):
        '''
        called when we recieve a ping
        '''
        self.send_raw({'src':self.server.name,'cmd':'PONG','target':self.server.name,'param':param})
        self.last_ping_recv = now()

    def send_ping(self):
        '''
        send out a ping
        '''
        self.last_ping_send = now()
        self.send_raw({'cmd':'PING','param':self.server.name})

    def chanserv(self,msg):
        self.notice('chanserv!chanserv@'+str(self.server.name),msg)

    def join(self,chan,key=None):
        '''
        join a channel
        '''
        chan = chan.lower()
        if chan in self.chans:
            if chan[0] not in util.chan_prefixs or len(chan) > 1 and chan[1] == '.' and len(chan) < 3:
                self.chanserv('bad channel name: '+chan)
                return
            if chan in self.server.chans:
                chan = self.server.chans[chan]
                for u in chan.users:
                    if u.nick == self.nick:
                        self.send_num(443,'Already In Channel',target=chan)
        else:
            if chan[0] not in util.chan_prefixs or len(chan) > 1 and chan[1] == '.' and len(chan) < 3:
                self.chanserv('bad channel name: '+chan)
                return
            if chan not in self.server.chans:
                self.server.new_channel(chan)
                self.chanserv('new channel: '+chan)
            else:
                c = self.server.chans[chan]
                for u in c.users:
                    if u.nick == self.nick:
                        self.send_num(443,'Already In Channel',target=chan)
                        return
            self.server.chans[chan].joined(self)
            self.chans.append(chan)


    def part(self,chan):
        '''
        part a channel
        '''
        chan = chan.lower()
        if chan in self.chans:
            self.chans.remove(chan)
        if chan in self.server.chans:
            chan = self.server.chans[chan]
            if self in chan.users:
                chan.part_user(self)

    def topic(self,channame,msg):
        '''
        called when TOPIC is recieved
        '''
        channame = channame.lower()
        if channame not in self.server.chans or channame not in self.chans:
            return
        chan = self.server.chans[channame]
        chan.set_topic(self,msg)

    def you_poni_now(self):
        '''
        set mode +P
        inform user
        '''
        self.set_mode('+P')
        if 'P' in self.modes:
            self.notice('modserv!service@%s'%self.server.name,'you have been nerfed')

    @registered
    def set_mode(self,modestring):
        '''
        set mode given a modestring
        '''
        for ch in modestring.split(' '):
            for c in ch[1:]:
                self.modes[c].set(ch[0] is '+')
                self.send_raw({'cmd':'MODE','target':self.nick,'src':self,'param':str(self.modes[c])})

    def get_full_name(self):
        return self.nick+'!'+self.usr+'@'+self.server.name

    def timeout(self):
        '''
        call to time out the user and disconnect them
        '''
        self.dbg('timed out')
        self.close_user('timed out')

    def _rand_nick(self,l):
        while True:
            nick = base64.b32encode(os.urandom(7)).decode('utf-8').replace('=','')[l:]
            if nick not in self.server.users:
                break
        return nick

    def do_nickname(self,nick):
        '''
        do not call directly
        '''
        if nick.count('#') > 0:
            i = nick.index('#')
            nick = nick.encode('utf-8',errors='replace')
            return util.tripcode(nick[:i],nick[i+1:])
        return self.id

    def handle_line(self,inbuffer):
        '''
        called when the user recieves a line
        '''
        self.dbg(' [RECV] '+inbuffer)
        d = util.irc_to_dict(inbuffer)
        cmd = d['cmd']
        if cmd is not None:
            cmd = cmd.lower()
        target = d['target']
        param = d['param']
        self.dbg('COMMAND: '+str(d))
        if hasattr(self,'got_'+cmd):
            getattr(self,'got_'+cmd)(target,param)


    def got_quit(self,target,param):
        self.close_user(param or 'quit')

    def got_ping(self,target,param):
        self.on_ping(param)

    def got_who(self,target,param):
        if param in self.server.chans:
            self.server.chans[param].send_who(self)

    def got_pong(self,target,param):
        self.on_pong(param)

    def got_nick(self,target,param):
        param = str(param)
        self.dbg('got nick: %s'%param)
        if not self.welcomed and len(self.nick) == 0:
            nick = self.do_nickname(param)
            self.nick = nick
            self.usr = 'local'
        elif self.welcomed:
            self.send_raw({'cmd':'NICK','src':str(self),'param':self.nick})

    def got_user(self,target,param):
        if len(self.nick) == 0:
            self.nick = self.do_nickname(target)
            self.server.change_nick(self,self.nick)
        self.server.on_new_user(self)
        #self.server.change_nick(self,self.do_nickname(self.nick))

    @registered
    def got_mode(self,target,param):
        if param is not None and param[0] in util.chan_prefixs:
            self.send_num(324,'+0',target=param)
        elif target == self.nick:
            self.set_mode(param)

        else:
            return self.send_num(502,'Cannot Change mode for other users')

    @registered
    def got_part(self,target,param):
        if param is not None:
            for chan in param.split(','):
                self.part(chan)

    @registered
    def got_privmsg(self,target,param):
        if target in self.server.users:
            self.server.users[target].privmsg(self,param)
            return
        elif target[0] in util.chan_prefixs:
            if target in self.chans and target in self.server.chans:
                self.server.chans[target].privmsg(self,param)
            else:
                return # send no such nick/chan but meh

        self.link.privmsg(self,str(target),param)

    @registered
    def got_topic(self,target,param):
        msg = util.filter_unicode(param)
        chan = target
        self.topic(chan,msg)

    @registered
    def got_motd(self,target,param):
        self.server.send_motd(self)

    @registered
    def got_join(self,target,param):
        if target is not None:
            for chan in target.split(','):
                if chan[0] in util.chan_prefixs:
                    self.join(chan)
        elif param is not None:
            for chan in param.split(','):
                if chan[0] in util.chan_prefixs:
                    self.join(chan)


    @registered
    def got_names(self,target,param):
        if target is not None:
            for chan in target.split(','):
                if chan in self.chans:
                    self.server.chans[chan].send_who(self)

    @registered
    def got_list(self,target,param):
        self.server.send_list(self)

    def nick_change(self,user,newnick):
        '''
        called when user changes their nickname to newnick
        '''
        data = ':'+str(user)+' NICK '+newnick
        self.send_raw({'src':user,'cmd':'NICK','param':newnick})

    def send_msg(self,data):
        '''
        place holder for sending data
        '''
        pass


    def send_num(self,num,param,target=None):
        target = target and '%s %s'%(self.nick,str(target)) or self.nick
        self.send_raw({'cmd':num,'src':self.server,'param':param,'target':target})

BaseUser = User
