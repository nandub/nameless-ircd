from asyncore import dispatcher
from asynchat import async_chat
import user, util
import socket,threading

trace = util.trace

class link(async_chat):
    """
    generic link
    """

    def __init__(self,sock,addr,parent,reconnect=None):
        self.addr = addr and str(addr) or None
        self.flood = parent.server.flood
        self.parent = parent
        self.server = parent.server
        self.dbg = self.server.dbg
        async_chat.__init__(self,sock)
        self.set_terminator(b'\n')
        self.relay = True
        self.reconnect = reconnect
        self.ibuff = []
        self._actions = {
            'privmsg':self.on_privmsg,
            'notice':self.on_notice,
            'join':self.on_join,
            'part':self.on_part,
            'topic':self.on_topic,
            'kick':self.on_kick,
            'quit':self.on_quit
            }
    def collect_incoming_data(self,data):
        self.ibuff.append(data)

    def filter(self,nm):
        #if '!' in nm and '@' in nm:
        #    p = nm.split('@')[0].split('!')
        #    return p[0] + '!remote@'+nm.split('@')[1]
        return nm

    @trace
    def found_terminator(self):
        buff = self.ibuff
        self.ibuff = []
        buff = map(lambda b : b.decode('utf-8',errors='replace'),buff)
        line = ''.join(buff)
        self.on_line(line)

    @trace
    def action(self,action,src,dst,msg):
        self.send_line(':'+str(src)+' '+action.upper()+' '+str(dst)+' :'+str(msg))
        
    @trace
    def privmsg(self,src,dst,msg):
        if str(dst).startswith('&'):
            src = 'nameless!nameless@irc.nameless.tld'
        self.action('privmsg',src,dst,msg)

    @trace
    def notice(self,src,dst,msg):
        if str(dst)[1] == '.':
            return
        if str(dst).startswith('&'):
            src = 'nameless!nameless@irc.nameless.tld'
        self.action('notice',src,dst,msg)

    @trace
    def topic(self,chan,topic):
        self.send_line(':nameless!nameless@irc.nameless.tld TOPIC '+str(chan)+' :'+topic)
        
    @trace
    def join(self,user,chan,dst=None):
        #return
        if str(chan)[1] == '.':
            return
        if str(chan).startswith('&'):
            return
        self.send_line(':'+str(user)+' JOIN :'+str(chan))
        
    @trace
    def part(self,user,chan,dst):
        #return
        if str(chan)[1] == '.':
            return
        if str(chan).startswith('&'):
            return
        self.action('part',user,chan,str(dst))

    @trace
    def on_kick(self,bully,victum,dst=None):
        reason = str(dst)
        self.notice('kickserv!kickserv@'+self.server.name,bully,'yur a $insult for kicking '+victum)
        
    @trace
    def on_join(self,user,chan,dst=None):
        user = self.filter(str(user))
        chan = str(dst)
        chan = chan[1:]
        self.dbg('link '+user+' joined '+chan)
        if chan[1] == '.':
            return
        if chan in self.server.chans:
            chan = self.server.chans[chan]
            if chan.is_anon or chan.is_invisible:
                return
            if not chan.has_remote_user(user):
                chan.join_remote_user(user)
            else:
                self.notice('chanserv!chanserv@'+self.server.name,user,'already joined '+str(chan))
                    
    @trace
    def on_part(self,user,reason,dst=None):
        
        user = self.filter(str(user))
        chan = dst
        self.dbg(user+' part '+chan+' because '+reason)
        if chan in self.server.chans:
            chan = self.server.chans[chan]
            if chan.is_anon or chan.is_invisible:
                return
            if chan.has_remote_user(user):
                chan.part_remote_user(user,reason)
            else:
                self.notice('chanserv!chanserv@'+self.server.name,user,'not in '+str(chan))

    @trace
    def on_quit(self,src,reason,dst=None):
        for chan in list(self.server.chans.values()):
            if chan.has_remote_user(src):
                chan.part_remote_user(src,'quit')
    @trace
    def on_notice(self,src,msg,dst):
        for user in self.server.users.values():
            if dst in [user.nick,user.trip]:
                user.notice(src,msg,str(user))
                return True
        src = self.filter(src)
        obj = None
        if dst in self.server.users:
            obj = self.server.users[dst]
        if dst in self.server.chans:
            obj = self.server.chans[dst]
            if obj.is_invisible:
                return
            if obj.is_anon:
                src = 'nameless!nameless@irc.nameless.tld'
        if obj is not None:
            obj.send_raw(':'+src+' NOTICE '+dst+' :'+msg)
            
    @trace
    def on_topic(self,durr,topic,dst=None):
        
        chan = dst
        if chan in self.server.chans:
            chan = self.server.chans[chan]
            if chan.is_invisible:
                return
            chan.topic = topic
            chan.send_topic()

    @trace
    def on_privmsg(self,src,msg,dst):
        # hate me later
        self.dbg('on_privmsg '+str(src)+' -> '+dst+' msg='+str(msg))
        for user in self.server.users.values():
            if hasattr(user,'trip'):
                if dst in [user.nick,user.trip]:
                    user.privmsg(src,msg,str(user))
                    return True
        if dst in self.server.chans:
            chan = self.server.chans[dst]
            if chan.is_invisible:
                return
            if chan.is_anon:
                chan.privmsg('nameless!nameless@irc.nameless.tld',msg)
                return
            src = self.filter(src)
            if not chan.has_remote_user(src):
                chan.join_remote_user(src)
            chan.privmsg(src,msg)
                

    @trace
    def on_line(self,line):
        self.dbg(str(self)+' link recv <-- '+str(line))
        self.flood.on_line(line)
        if line.split(':')[1].split(' ')[0].split('@')[1] == self.server.name:
            self.dbg('dropping repeat line: '+line)
            return
        
        parts = line[1:].split(' ')
        if self.flood.line_is_flooding(line):
            self.dbg('dropping flood from '+parts[0])
            return
        self.dbg('link line '+str(parts))
        if len(parts) > 2:
            src, action, dst = tuple(parts[:3])
            action = action.lower()
            self.dbg('action='+str(action))
            if action in self._actions:
                if not self._actions[action](src,(' '.join(line.split(' ')[3:]))[1:],dst=dst):
                    for link in self.parent.links:
                        if link == self:
                            continue
                        link.send_line(line)

    def handle_error(self):
        self.parent.handle_error()
        self.handle_close()

    def handle_close(self):
        self.parent.on_link_closed(self)
        self.close()

    @trace
    def send_line(self,line):
        self.dbg(str(self)+' link send--> '+str(line))
        for c in line:
            o = ord(c)
            if o > 127 or o < 1:
                continue
            self.push(c.encode('ascii',errors='replace'))
            
        self.push(b'\n')


class linkserv(dispatcher):
    """
    s2s manager
    """
    
    def __init__(self,parent,addr,ipv6=False,allow_link=True):
        af = ipv6 and socket.AF_INET6 or socket.AF_INET
        dispatcher.__init__(self)
        if allow_link:
            self.create_socket(af,socket.SOCK_STREAM)
            self.set_reuse_addr()
            self.bind(addr)
            self.listen(5)
        else:
            self.readable = lambda: False
            self.writeable = lambda: False
            self.handle_accepted = lambda a,b: None
        self.server = parent
        self.links = []
        self.dbg = parent.dbg
        self.nfo = parent.nfo
    
    def privmsg(self,src,dst,msg):
        for link in self.links:
            if link.relay:
                link.privmsg(src,dst,msg)
    def notice(self,src,dst,msg):
        for link in self.links:
            if link.relay:
                link.notice(src,dst,msg)
    def join(self,src,dst):
        for link in self.links:
            if link.relay:
                link.join(src,dst)
    def part(self,user,chan,dst):
        for link in self.links:
            if link.relay:
                link.part(user,chan,dst)
    def topic(self,src,topic):
        for link in self.links:
            if link.relay:
                link.topic(src,topic)


    def _link(self,connect,link_addr):
        def f(addr):
            if addr is None:
                return
            self.dbg('connect link addr='+str(addr))
            sock = None
            err = None
            try:
                sock , err = connect()
            except:
                self.nfo('link failed , '+str(err))
                if '127.0' in addr:
                    self.local_link(int(addr.split(':')[1]))
                elif 'b32.i2p' in addr or 'AAAA' in addr:
                    self.i2p_link(addr)
                else:
                    host, port = tuple(addr.split(':'))
                    self.tor_link(host,port)
            else:
                if isinstance(addr,tuple):
                    host,port = addr
                    addr = str(host)+':'+str(port)
                self.dbg('new link '+str(addr))
                l = link(sock,addr,self)
                l.reconnect = addr
                self.links.append(l)
        threading.Thread(target=f,args=(link_addr,)).start()
    def local_link(self,port):
        sock = socket.socket()
        self._link(lambda : (sock.connect(('127.0.0.1',int(port))) or sock , None),'127.0.0.1:'+str(port))
        
    def i2p_link(self,host):
        self._link(lambda : util.i2p_connect(host), host)

    def tor_link(self,host,port):
        self._link(lambda : util.tor_connect(host,int(port)), host+':'+str(port))

    def on_link_closed(self,link):
        self.dbg('link '+str(link)+' closed addr='+str(link.reconnect))
        if link in self.links:
            self.links.remove(link)
        if link.reconnect is None:
            return
        if isinstance(link.reconnect,tuple):
            host,port = link.reconnect
            addr = str(host)+':'+str(port)
        else:
            addr = str(link.reconnect)
        if addr.count(':') > 0:
            host,port = tuple( addr.split(':') )
            if '127.0' in addr:
                self.local_link(port)
            else:
                self.tor_link(host,int(port))
        elif addr.count('.b32.i2p') > 0 or addr.count('AAAA') > 0:
            self.i2p_link(addr)
        else:
            self.nfo('relink failed for addr='+addr)

    def handle_close(self):
        for link in self.links:
            link.reconnect = None
            link.close()
    def handle_error(self):
        self.server.handle_error()

    def handle_accepted(self,sock,addr):
        self.nfo('new link from '+str(addr))
        self.links.append(link(sock,None,self))
