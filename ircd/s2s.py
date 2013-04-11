from asyncore import dispatcher
from asynchat import async_chat
import user, util
import socket,threading

trace = util.trace

class link(async_chat):
    """
    generic link
    """

    def __init__(self,sock,addr,parent):
        self.addr = addr
        self.parent = parent
        self.server = parent.server
        async_chat.__init__(self,sock)
        self.set_terminator(b'\n')
        self.ibuff = []
        self.send_line = parent.send_line
        self._actions = {
            'privmsg':self.on_privmsg,
            'notice':self.on_notice,
            'join':self.on_join,
            'part':self.on_part,
            'topic':self.on_topic,
            'kick':self.on_kick
            }

    def collect_incoming_data(self,data):
        self.ibuff.append(data)

    def filter(self,nm):
        if '!' in nm and '@' in nm:
            p = nm.split('@')[0].split('!')
            return p[0] + '!remote@'+nm.split('@')[1]
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
        if str(dst).startswith('&'):
            src = 'nameless!nameless@irc.nameless.tld'
        self.action('notice',src,dst,msg)

    @trace
    def topic(self,chan,topic):
        self.send_line(':nameless!nameless@irc.nameless.tld TOPIC '+str(chan)+' :'+topic)
        
    @trace
    def join(self,user,chan,dst=None):
        if str(chan).startswith('&'):
            return
        self.send_line(':'+str(user)+' JOIN '+str(chan))
        
    @trace
    def part(self,user,chan,dst):
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
        chan = chan[:1]
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
        chan = dst[1:]
        if chan in self.server.chans:
            chan = self.server.chans[chan]
            if chan.is_anon or chan.is_invisible:
                return
            if chan.has_remote_user(user):
                chan.part_remote_user(user,reason)
            else:
                self.notice('chanserv!chanserv@'+self.server.name,user,'not in '+str(chan))
                
    @trace
    def on_notice(self,src,msg,dst):
        src = self.filter(src)
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
        for link in self.parent.links:
            if link == self:
                continue
            self.send_line(line)
        sparts = line[1:].split(' ')
        if len(sparts) > 2:
            src, action, dst = tuple(sparts[:3])
            action = action.lower()
            if action in self._actions:
                self._actions[action](src,(' '.join(line.split(' ')[3:]))[1:],dst=dst)
        

    def handle_error(self):
        self.parent.handle_error()
        self.handle_close()

    def handle_close(self):
        self.parent.on_link_closed(self)
        self.close()

class linkserv(dispatcher):
    """
    s2s manager
    """
    
    def __init__(self,parent,addr,ipv6=False):
        dispatcher.__init__(self)
        af = ipv6 and socket.AF_INET6 or socket.AF_INET
        self.create_socket(af,socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(addr)
        self.listen(5)
        self.server = parent
        self.links = []
    
    def privmsg(self,src,dst,msg):
        for link in self.links:
            link.privmsg(src,dst,msg)
    def notice(self,src,dst,msg):
        for link in self.links:
            link.notice(src,dst,msg)
    def join(self,src,dst):
        for link in self.links:
            link.join(src,dst)
    def part(self,user,chan,dst):
        for link in self.links:
            link.part(user,chan,dst)
    def topic(self,src,topic):
        for link in self.links:
            link.topic(src,topic)

    def on_link_closed(self,link):
        
    @trace
    def send_line(self,line):
        for c in line:
            o = ord(c)
            if o > 127 or o < 1:
                continue
            for l in self.links:
                l.push(c.encode('ascii',errors='replace'))
        for l in self.links:
            l.push(b'\n')

    def _link(self,connect,addr):
        def f():
            sock , err = connect()
            if sock is not None:
                self.links.append(link(sock,addr,self))
            else:
                self.server.nfo('link failed , '+str(err))
        threading.Thread(target=f,args=()).start()

    def i2p_link(self,host):
        self._link(lambda : util.i2p_connect(host), host)

    def tor_link(self,host,port):
        self._link(lambda : util.tor_connect(host,port), host+':'+str(port))

    def on_link_closed(self,link):
        if link in self.links:
            self.links.remove(link)
        if link.addr is None:
            return
        if link.addr.count(':') > 0:
            host,port = tuple( link.addr.split(':') )
            self.tor_link(host,int(port))
        else:
            self.i2p_link(link.host)
    def handle_error(self):
        self.server.handle_error()

    def handle_accept(self):
        pair = self.accept()
        if pair:
            sock, addr = pair
            self.links.append(link(sock,None,self))
