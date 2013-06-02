from asyncore import dispatcher
from asynchat import async_chat
import user, util
import socket,threading,time

trace = util.trace

class link(async_chat):
    """
    generic link
    """

    is_authed = False



    def __init__(self,sock,parent,reconnect=None):
        self.name = None
        self.flood = parent.server.flood
        self.parent = parent
        self.server = parent.server
        self.dbg = self.server.dbg
        self.nfo = self.server.nfo
        self.err = self.server.err
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
            'quit':self.on_quit,
            'server':self.on_server
            }

        self.children = []
        self.send_initial_servers()

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
        if str(dst)[1] == '.':
            return # hacky fix
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
        self.send_line(':nameless!nameless@irc.nameless.tld TOPIC '+str(chan)+' :'+str(topic))
        
    @trace
    def join(self,user,chan,dst=None):
        if str(chan)[1] == '.':
            return
        if str(chan).startswith('&'):
            return
        self.send_line(':'+str(user)+' JOIN :'+str(chan))

    def quit(self,user,reason='quit'):
        self.send_line(':'+str(user)+' QUIT :'+str(reason))
        
    @trace
    def part(self,user,chan,dst):
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
                    
    @trace
    def on_part(self,user,reason,dst=None):
        user = self.filter(str(user))
        #nick = self.filter(str(user))
        chan = dst
        self.dbg(user+' part '+chan+' because '+reason)
        if chan in self.server.chans:
            chan = self.server.chans[chan]
            if chan.is_anon or chan.is_invisible:
                return
            if chan.has_remote_user(user):
                chan.part_remote_user(user,reason)
            
    @trace
    def on_quit(self,src,reason,dst=None):
        for chan in list(self.server.chans.values()):
            src = self.filter(src)
            chan.part_remote_user(src,'quit')
    @trace
    def on_notice(self,src,msg,dst):
        for user in self.server.users.values():
            if dst in [user.nick,user.trip]:
                user.notice(src,msg,str(user))
                return True
        #nick = self.filter(src)
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
            chan.set_topic(None,topic)

    @trace
    def on_privmsg(self,src,msg,dst):
        # hate me later
        self.dbg('on_privmsg '+str(src)+' -> '+dst+' msg='+str(msg))
        for user in self.server.users.values():
            if hasattr(user,'nick'):
                if dst == user.nick:
                    user.privmsg(src,msg,str(user))
                    return True
        if dst in self.server.chans:
            chan = self.server.chans[dst]
            if chan.is_invisible:
                return
            if chan.is_anon:
                chan.privmsg('nameless!nameless@irc.nameless.tld',msg)
                return
            nick = self.filter(src)
            for u in chan.users:
                if u.nick == nick:
                    return
            if not chan.has_remote_user(src):
                chan.join_remote_user(src)
            chan.privmsg(src,msg)

    def _should_drop_line(self,line):
        return False
    
    def send_initial_servers(self):
        pass

    @trace
    def on_line(self,line):
        self.dbg(str(self)+' link recv <-- '+str(line))
        self.flood.on_line(line)
        if self.flood.line_is_flooding(line):
            self.dbg('drop flood')
            return
        if line.startswith('SERVER'):
            self._handle_server_register(line)
        elif 'SERVER' in line and line.startswith(':'):
            return

        if self._should_drop_line(line):
            return

        for c in [':','@',' ']:
            if c not in line:
                self.nfo('invalid s2s line: '+line)
                return
        try:
            if line.split(':')[1].split(' ')[0].split('@')[1] == self.server.name:
                self.dbg('dropping repeat line: '+line)
                return
        except:
            self.nfo('invalid s2s line: '+line)
            return
        parts = line[1:].split(' ')
        self.dbg('link line '+str(parts))
        if len(parts) > 2:
            src, action, dst = tuple(parts[:3])
            action = action.lower()
            self.dbg('action='+str(action))
            if not ( action in self._actions and self._actions[action](src,(' '.join(line.split(' ')[3:]))[1:],dst=dst) ):
                for link in self.parent.links:
                    if link == self:
                        continue
                    link.send_line(line)
                        
    def handle_error(self):
        self.parent.handle_error()
        self.handle_close()

    def handle_close(self):
        name = str(self.name)
        self.nfo('link '+name+' closed')
        self.parent.on_link_closed(self)
        self.close()

    @trace
    def send_line(self,line,encoding='utf-8'):
        line = str(line)
        self.dbg(str(self)+' link send --> '+line)
        self.push(line.encode(encoding,errors='replace'))
        self.push(b'\n')

    def _handle_server_register(self,line):
        
        # format is
        #
        # SERVER name.of.server 0 0 :name.of.child1,name.of.child2,name.of.child3
        # given that there are 3 child servers from the incomming connection
        # 
        # for no children format is
        #
        # SERVER name.of.server 0 0 :name.of.server
        #
        parts = line.split(' ')
        if len(parts) < 5:
            self.close_when_done()
            return
        server_name = parts[1]
        response_parts = [server_name]
        self.name = server_name
        if self.parent.register_server(server_name,self):
            # get children from info as comma separated values
            for part in (' '.join(parts[4:]))[1:].split(','):
                part = part.strip()
                if self.parent.register_server(part,self):
                    response_parts.append(part)
            
                    # response info has the servers that were accepted
                    #
                    # format is
                    #
                    # :our.server.name SERVER our.server.name 0 0 :name.of.server,name.of.child1
                    #
            response = ':'+self.server.name+' SERVER '+self.server.name+' 0 0 :'
            response += ','.join(response_parts)
            response = response[-1] == ',' and response[:-1] or response
            self.send_line(response)

    def on_server(self,*args,**kwds):
        pass

    def _should_drop_line(self,line):
        ret = self.parent.require_auth
        if ret:
            if line[0] == ':' and ' ' in line:
                server_name = line.split(' ')[0]
                ret = server_name not in self.children
        return ret

class incoming_link(link):
    
    def on_server(self,src,msg,dst):
        self.dbg('link on_server src='+src+' dst='+dst+' msg='+msg)

    def _should_drop_line(self,line):
        if line.startswith('SERVER'):
            return False
        if line[0] == ':':
            return False
        self.close_when_done()
        return True

    def __str__(self):
        return 'incomming link name='+str(self.name)
    
class outgoing_link(link):

    def send_initial_servers(self):
        """
        send on intial connection what all our servers are
        """
        if self.parent.require_auth:
            request = 'SERVER '+self.server.name+' 0 0 :'
            for link in self.parent.links:
                if link == self or link.name is None:
                    continue
                request += link.name+','
            self.send_line(request[:-1])
        
    def __str__(self):
        return 'outgoing link '+link.__str__(self)

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
        self.servers = {}
        self.dbg = parent.dbg
        self.nfo = parent.nfo
        self.require_auth = parent.require_auth

    def reconnect_all(self):
        links = []
        for link in self.links:
            if link.reconnect:
                links.append(link)

        for link in links:
            self.link.remove(link)
            link.close_when_done()

    def disconnect_all(self):
        for link in self.links:
            link.reconnect = None
            link.close_when_done()
        self.links = []

    def quit(self,user,reason):
        for link in self.links:
            if link.relay:
                link.quit(user,reason)

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

    def _new_link(self,sock,reconnect,name,link_class=outgoing_link):
        if not self.server.on:
            return
        l = link_class(sock,self)
        l.name = None
        l.reconnect = reconnect
        # announce child link
        for link in self.links:
            if l.name is not None:
                link.send_line('SERVER '+self.server.name+' 0 0 :'+l.name)
        self.links.append(l)
        #self.server.send_global('link '+l.name+' up')

    def _link(self,connect,name):
        def f(name):
            self.dbg('connect link name='+str(name))
            sock = None
            err = None
            while sock is None and self.server.on:
                try:
                    sock , err = connect()
                except:
                    self.nfo('link '+str(name)+' failed reconnect')
                if sock is None:
                    time.sleep(10)

            self._new_link(sock,lambda : self._link(connect,name),name)
        threading.Thread(target=f,args=(name,)).start()

    def register_server(self,server_name,link):
        if server_name in self.servers:
            return False
        self.servers[server_name] = link
        link.children.append(server_name)
        return True

    def local_link(self,port):
        def connect():
            sock = socket.socket()
            sock.connect(('127.0.0.1',int(port)))
            return sock, None
        self._link(connect,'local-'+str(port))
        
    def i2p_link(self,host):
        self._link(lambda : util.i2p_connect(host),str(host))

    def tor_link(self,host,port=6660):
        self._link(lambda : util.tor_connect(host,int(port)),str(host))

    def ipv6_link(self,host,port=6660):
        def connect():
            sock = socket.socket(socket.AF_INET6)
            sock.connect((host,port))
            return sock, None
        self._link(connect,'remote6-'+host)

    def ipv4_link(self,host,port=6660):
        def connect():
            sock = socket.socket()
            sock.connect((host,port))
            return sock, None
        self._link(connect,'remote4-'+host)

    def on_link_closed(self,link):
        name = str(link.name)
        self.dbg('link '+name+' closed')
        #self.server.send_global('link '+name+' down')
        if link in self.links:
            self.links.remove(link)
            if link.reconnect is not None:
                link.reconnect()

    def handle_close(self):
        for link in self.links:
            link.reconnect = None
            link.close_when_done()

    def handle_error(self):
        self.server.handle_error()

    def handle_accepted(self,sock,addr):
        self.nfo('new link from '+str(addr))
        if self.server.on:
            self._new_link(sock,None,'incoming-'+str(addr[1]),incoming_link)
        
