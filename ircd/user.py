# -*- coding: utf-8 -*-
from time import time as now
from functools import wraps
import util, base
import base64, os

def registered(f):
    @wraps(f)
    def func(*args,**kwds):
        user = args[0]
        if user.welcomed:
            f(*args,**kwds)
        else:
            user.send_num(451,':You have not registered')
    return func

@util.decorate
def require_min_args(f,l):
    @wraps(f)
    def func(*args,**kwds):
        user = args[0]
        if len(args[1]) < l:
            name = f.func_name.split('got_')[-1].upper()
            user.send_num(461,name+' :Not Enough Parameters')
        else:
            f(*args,**kwds)
    return func

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
        self._modes = {}
        self._mode_lock = False
        
    def __getitem__(self,key):
        if key in self._modes:
            return self._modes[key]
        return '-'+key
    
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
        self.after_motd = None
        self.last_ping_recv = now()
        self.last_ping_send = 0
        self.usr = ''
        self.name = ''
        self.last_ping = 0
        self.last_topic = 0
        self.chans = []
        self.modes = modes()
        self.welcomed = False
        self._allowed_chars = [
            'abcdefghijklmnopqrstuvwxyz' \
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ' \
            '0123456789_-\\[]{}`'
            ]
        self.__str__ = self.get_full_name
        self.dbg = lambda msg: server.dbg(str(self)+' '+str(util.filter_unicode(msg)))
        self.handle_close = self.close_user

    def handle_error(self):
        self.server.handle_error()
        self.handle_close()

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
        out = ''
        action = False
        replacement = self.server.poniponi or 'blah'
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

    def privmsg(self,src,msg,dst=None):
        '''
        recieve private message from source src with contents msg
        if dst is not None the destination is a channel
        '''
        if 'P' in self.modes and dst is not None:
            msg = self.filter_message(msg)
        self.action(src,'privmsg',msg,dst=dst)

    def action(self,src,type,msg,dst=None):
        '''
        send an event from src with type type with contents msg from dst
        '''
        if dst is None:
            dst = self
        self.send_raw(':%s %s %s :'%(src, type.upper(),dst)+msg)

    def close_user(self):
        '''
        do not call directly
        use Server.close_user(user) instead
        '''
        self.dbg('%s closing connection'%self)
        for chan in self.chans:
            self.part(chan)
        self.server.on_user_closed(self)
        self.close()

    def event(self,src,type,msg):
        '''
        send event from src of type type with contents msg
        '''
        self.send_raw(':%s %s :'%(src,type.upper())+msg)

    def send_raw(self,data):
        '''
        send a raw line
        '''
        if not 'u' in self.modes:
            data = util.filter_unicode(data)
        self.dbg('--> '+str(data))
        self.send_msg(data)

    def kill(self,reason):
        '''
        do not call directly
        use Server.kill(user,reason) instead
        '''
        self.send_notice('killserv!killserv@'+str(self.server.name),'Your connection was killed: '+str(reason))
        self.handle_close()

    def on_pong(self,pong):
        '''
        called when we recieve a pong
        '''
        self.last_ping_recv = now()

    def on_ping(self,ping):
        '''
        called when we recieve a ping
        '''
        ping = ping.split(' ')[0]
        if ping[0] == ':':
            ping = ping[1:]
        self.send_raw(':'+self.server.name+' PONG '+self.server.name+' :'+ping)
        self.last_ping_recv = now()

    def send_ping(self):
        '''
        send out a ping
        '''
        self.last_ping_send = now()
        self.send_raw('PING '+self.server.name)

    def chanserv(self,msg):
        self.send_notice('chanserv!chanserv@'+str(self.server.name),msg)


    def join(self,chan):
        '''
        join a channel
        '''
        chan = chan.lower()
        if chan in self.chans:
            self.chanserv('already in channel: '+chan)
            return
        if chan[0] not in ['&','#'] or len(chan) > 1 and chan[1] == '.' and len(chan) < 3:
            self.chanserv('bad channel name: '+chan)
        else:
            if chan not in self.server.chans:
                self.server.new_channel(chan)
                self.chanserv('new channel: '+chan)
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
            self.server.chans[chan].user_quit(self)


    def check_topic_ratelimit(self):
        ret = now() - self.last_topic > self.server.topic_limit
        self.last_topic = now()
        return ret
        


    def topic(self,channame,msg):
        '''
        called when TOPIC is recieved
        '''
        channame = channame.lower()
        if channame not in self.server.chans:
            return
        chan = self.server.chans[channame]
        if msg:
            if self.check_topic_ratelimit():
                chan.set_topic(self,msg)
            else:
                self.kill('topic flood')
        else:
            chan.send_topic_to_user(self)

    def you_poni_now(self):
        '''
        set mode +P
        inform user
        '''
        self.set_mode('+P')
        if 'P' in self.modes:
            self.send_notice('modserv!service@%s'%self.server.name,'you have been nerfed')

    @util.deprecate
    def _set_single_mode(self,*args,**kwds):
        pass

    @registered
    def set_mode(self,modestring):
        '''
        set mode given a modestring
        '''
        for ch in modestring.split(' '):
            for c in ch[1:]:
                self.modes[c] = ch[0] in '+-' and ch[0] or '-'
                self.send_raw(':%s MODE %s :%s'%(self.nick,self.nick,self.modes[c]))

    def timeout(self):
        '''
        call to time out the user and disconnect them
        '''
        self.dbg('timed out')
        self.close_user()

    def _rand_nick(self,l):
        nick =  base64.b32encode(os.urandom(l)).replace('=','')
        while nick in self.server.users:
            nick = base64.b32encode(os.urandom(l)).replace('=','')
        return nick

    def send_num(self,num,data):
        '''
        send a response that contains a status number
        '''
        self.send_raw(':%s %s %s %s'%(self.server.name,num,self.nick,data))

    def do_nickname(self,nick):
        '''
        do not call directly
        '''
        if '#' in nick:
            nick = nick.strip()
            i = nick.index('#')
            trip = util.tripcode(nick[:i],nick[i+1:])
            nick = util.filter_unicode(nick[:i]).replace('?','|')
            for c in nick:
                if c not in self._allowed_chars:
                    self.dbg('bad char '+c)
                    return self._rand_nick(6)
            nick += '|' 
            return nick + trip[:len(trip)/2]        
        return self._rand_nick(6)

    def handle_line(self,inbuffer):
        '''
        called when the user recieves a line
        '''
        self.dbg('got line '+inbuffer)
        p = inbuffer.split(' ')
        if ':' in inbuffer:
            i = inbuffer.index(':')
            p = inbuffer[:i].split(' ')
            p.append(inbuffer[i+1:])
        
        data = inbuffer.lower()
        cmd = p[0].lower()
        param = []
        for part in p:
            if part == '':
                continue
            param.append(part)
        self.dbg('COMMAND: '+str(cmd)+' '+str(param))
        if hasattr(self,'got_'+cmd):
            # element -1 is what is after the first :
            getattr(self,'got_'+cmd)(param[1:])

    
    def got_quit(self,args):
        self.close_when_done()
    
    @require_min_args(1)
    def got_ping(self,args):
        self.on_ping(args[-1])

    @require_min_args(1)
    def got_pong(self,args):
        self.on_pong(args[-1])

    @require_min_args(1)
    def got_nick(self,args):
        self.dbg('got nick: %s'%args[0])
        nick = self.do_nickname(args[0])
        if not self.welcomed and len(self.nick) == 0:
            self.nick = args[0]
            self.usr = args[0]
        else:
            self.server.change_nick(self,nick)

    @require_min_args(4)
    def got_user(self,args):
        self.server.on_new_user(self)
        self.server.change_nick(self,self.do_nickname(self.nick))

    @registered
    @require_min_args(1)
    def got_mode(self,args):        
        if args[0][0] in ['&','#']: #channel mode
            if args[0] in self.chans:
                self.send_num(324,args[0]+' +')
        elif len(args) == 2: #user mode
            if args[0] == self.nick:
                self.set_mode(args[1])
            else:
                self.send_num(502, ':Cannot change mode for other users')
        elif len(args) == 1: #user get mode
            if args[0] == self.nick:
                self.send_num(221, str(self.modes))
    
    @registered
    @require_min_args(1)
    def got_part(self,args):
        for chan in args[0].split(','):
            self.part(chan)

    @registered
    @require_min_args(2)
    def got_privmsg(self,args): 
        msg = args[-1]
        target = args[0]
        dest = None
        if target[0] in ['&','#']:
            if target in self.chans or target in self.server.chans:
                dest = self.server.chans[target]
        elif target in self.server.users:
                dest = self.server.users[target]
        if dest is None:
            self.send_num(401,target+' :No such nick/channel')
        else:
            dest.privmsg(self,msg)
            
    @registered
    @require_min_args(1)
    def got_topic(self,args):
        if len(args) > 1:
            msg = util.filter_unicode(args[-1])
        else:
            msg = None
        chan = args[0]
        self.topic(chan,msg)

    @registered
    def got_motd(self,args):
        self.server.send_motd(self)

    @registered
    @require_min_args(1)
    def got_join(self,args):
        for chan in args[0].split(','):
            self.join(chan)
    
    @registered
    @require_min_args(1)
    def got_names(self,args):
        for chan in args[0].split(','):
            if chan in self.chans:
                self.server.chans[chan].send_who(self)
                
    @registered
    def got_list(self,args):
        self.server.send_list(self)

    def nick_change(self,user,newnick):
        '''
        called when user changes their nickname to newnick
        '''
        data = ':'+str(user)+' NICK '+str(newnick)
        self.send_raw(data)

    def send_msg(self,data):
        '''
        place holder for sending data
        '''
        pass


BaseUser = User
