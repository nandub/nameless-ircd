#
# torchat driver
#
import socket, time, random, threading
from asynchat import async_chat as chat
from asyncore import dispatcher
from util import locking_dict
import util

class dummy_client:
    def on_connected(self,connection):
        pass
    def on_disconnected(self,connection):
        pass
    def on_status(self,connection):
        pass
    def on_chat(self,connection,msg):
        pass
    def on_client(self,connection):
        pass
    def pump(self):
        pass
    def on_add_me(self,connections):
        pass
    def on_ping(self,onion,cookie):
        pass
    def on_pong(self,cookie):
        pass

class handler(chat):
    '''
    generic connection handler
    '''
    def __init__(self,sock,parent,client):
        chat.__init__(self,sock)
        self.handle_error = parent.handle_error
        self.parent = parent
        self.server = parent.server
        self.set_terminator(b'\n')
        self._ibuffer = []
        self.client = None
        self.version = None
        self.status = 'offline'
        self._client = client or dummy_client()
        self.handle_error = self.server.handle_error
        self.dbg = self.server.dbg
        
    def collect_incoming_data(self,data):
        self._ibuffer.append(data)

    def found_terminator(self):
        line = ''
        for part in self._ibuffer:
            line += part.decode('utf-8',errors='replace')        
        line = self._unescape(line)
        self.got_line(line)
        self._ibuffer = []

    def got_line(self,line):
        parts = line.split(' ')
        cmd = parts[0]
        self.dbg('tc got line '+line+' '+str(parts))
        if hasattr(self,'on_'+cmd):
            getattr(self,'on_'+cmd)(' '.join(parts[1:]))
        else:
            self.send_line('not_implemented '+line)

    def send_msg(self,line):
        self.send_line('message '+line)
    
    def _escape(self,line):
        return str(line).replace("\\", "\\/").replace("\n", "\\n")

    def _unescape(self,line):
        return str(line).replace("\\n", "\n").replace("\\/", "\\")

    def send_line(self,line):
        self.dbg('tc send line '+line)
        line = self._escape(line)
        self.push(line.encode('utf-8',errors='replace'))
        self.push(b'\n')

    def handle_close(self):
        
        self._client.on_disconnected(self)
            
        chat.handle_close(self)

    def on_add_me(self,string):
        self._client.on_add_me(self)

    def on_client(self,string):
        if self.client is None:
            self.client = string

    def on_version(self,string):
        if self.version is None:
            self.version = string

    def on_pong(self,string):
        pass
            
    def on_message(self,string):
        if not self.is_out:
            for line in string.split('\n'):
                self._client.on_chat(self,line)

    def on_status(self,string):
        if 'handshake' not in [string,self.status]:
            self.status = string
            self._client.on_status(self)

    def send_ping(self):
        self.send_line('ping '+self.parent.tc_onion+' '+self.parent.cookie)

    def readable(self):
        self._client.pump(self)
        if int(time.time()) % 4 == 0:
            self.send_update()
        return chat.readable(self)
        
    def pump_client(self):
        self._client.pump(self)

    def send_update(self):
        pass
        
class in_handler(handler):
    '''
    inbound chat handler
    '''
    is_out = False
    def __init__(self,sock,parent,client=None):
        handler.__init__(self,sock,parent,client)

    def on_ping(self,string):
        onion, cookie = tuple(string.split(' '))
        self.dbg('tc ping cookie='+cookie+' onion='+onion)
        if onion in self.parent.clients:
            self.parent.clients[onion].on_ping(onion,cookie)
        elif onion in self.parent.onions:
            con = self.parent.onions[onion]
            if hasattr(con,'server'):
                self.dbg('send pong')
                self.send_pong(cookie)
        else:
            self.parent.connect_out(onion,cookie,self._client)

    def on_pong(self,string):
        self._client.on_pong(string)

class out_handler(handler):
    '''
    outgoing chat handler
    '''
    is_out = True
    def __init__(self,cookie,onion,sock,parent,client=None):
        handler.__init__(self,sock,parent,client)
        self.cookie = cookie
        self.onion = onion
        self.send_ping()
        self.dbg('new out with cookie='+self.cookie)

    def send_update(self):
        if int(time.time()) % 5 == 0:
            self.send_line('status available')
        self.pump_client()

    def got_line(self,line):
        self._ibuffer = []
        
    def send_status(self):
        self.send_line('client '+self.parent.tc_client_name)
        self.send_line('version '+self.parent.tc_version)
        self.send_line('add_me')
        self.send_line('status available')
        self._client.on_connected(self)

    def send_pong(self,cookie):
        self.send_line('pong '+cookie)

class torchat(dispatcher):
    
    def __init__(self,server,onion,client_class,host='127.0.0.1',port=11009,db_fname='tc_cookies.db'):
        dispatcher.__init__(self)
        self.create_socket(socket.AF_INET,socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host,port))
        self.listen(5)
        self.tc_client_name = 'NamelessIRCD'
        self.tc_version = '0.0.1'
        self.tc_onion = onion
        self._db_fname = db_fname
        self._init_cookie()
        self.clients = locking_dict()
        self.onions = locking_dict()
        self.client_class = client_class
        self.server = server
        self.dbg = server.dbg
        self.cookie = self.gen_cookie()

    def gen_cookie(self):
        cookie = ''
        for n in range(35):
            cookie += str(random.randint(0,n+1))
        return cookie

    def handle_accepted(self,sock,addr):
        in_handler(sock,self,self.client_class(self))


    def connect_out(self,onion,cookie,client):
        def func(onion,cookie,client):
            onion += '.onion'
            while True:
                self.dbg('tc connect to '+onion+' cookie='+cookie)
                sock,err = util.tor_connect(onion,11009)
                if sock is not None:
                    onion = onion.replace('.onion','')
                    self.dbg('tc got outcon to '+onion)
                    self.onions[onion] = out_handler(cookie,onion,sock,self,client)
                    client.outcon = self.onions[onion]
                    client.outcon.send_pong(cookie)
                    client.outcon.send_status()
                    break
                self.dbg('tc connect error='+err)
                
        if onion not in self.onions:
            self.onions[onion] = threading.Thread(target=func,args=(onion,cookie,client)).start()
        

class nameless_client:
    '''
    client logic object
    '''
    def __init__(self,parent):
        self.server = parent.server
        self.parent = parent
        self.chan = None
        self.sendq = []
        self.onion = None
        self.dbg = self.server.dbg
        self.outcon = None
        self.incon = None

    def handle_cmd(self,con,cmd,args):
        if hasattr(self,'cmd_'+cmd):
            getattr(self,'cmd_'+cmd)(con,args)

    def _filter(self,msg):
        if msg.startswith('\01ACTION'):
            msg = msg.replace('\01ACTION','/me').replace('\01','')
        elif msg.startswith('\01'):
            i = ' 'in msg and msg.index(' ') or -1
            msg = '[CTCP '+parts[1:i]+']'
        return msg

    def send_line(self,line):
        self.sendq.append(line)

    def on_ping(self,onion,cookie):
        self.outcon.send_pong(cookie)
    
    def privmsg(self,src,msg):
        msg = self._filter(msg)
        self.send_msg('['+str(src)+'] '+msg)

    def on_add_me(self,con):
        pass

    def _get_cmds(self):
        cmds = []
        for cmd in self._cmds():
            cmds.append(cmd)
        return cmds

    def _cmds(self):
        for attr in dir(self):
            if attr.startswith('cmd_'):
                yield attr.replace('cmd_','')

    def cmd_help(self,con,args):
        '''
        display information on commands
        useage: !help command
        '''
        if len(args) != 1:
            args = ['help']
        
        cmd = 'cmd_'+args[0]
        cmd = hasattr(self,cmd) and getattr(self,cmd) or self.cmd_help
        con.send_msg('!'+args[0])
        for line in str(cmd.__doc__).split('\n'):
            con.send_msg(line)
        con.send_msg('current commands are: '+' '.join(self._get_cmds()))
            

    def cmd_list(self,con,args):
        '''
        list channels
        '''
        con.send_msg('channels')
        for chan in self.server.chans.values():
            con.send_msg('channel: '+chan.name+' '+str(len(chan))+' users')

    def cmd_who(self,con,args):
        '''
        list who is in the current channel
        '''
        if self.chan is not None:
            if self.chan.is_anon:
                con.send_msg('user: nameless')
            else:
                for user in self.chan.users:
                    con.send_msg('user: '+str(user).split('!')[0])
                for user in self.chan.remotes:
                    con.send_msg('user: '+str(user).split('!')[0])
                for user in self.chan.torchats:
                    con.send_msg('torchat user :'+user.onion)
    def on_pong(self,string):
        pass

    def on_status(self,con):
        self.status = con.status

    def cmd_channel(self,con,args):
        '''
        join a channel
        use !channel exit to exit the current channel or do !channel #otherchannel to exit and switch
        '''
        if len(args) != 1:
            con.send_msg('see !help channel for help')
        elif args[0] in self.server.chans:
            if self.chan is not None:
                self.chan.part_torchat(self)
            self.chan = self.server.chans[args[0]]
            con.send_msg('channel set to '+args[0])
            self.chan.join_torchat(self)
        elif args[0] == 'exit':
            if self.chan is not None:
                self.chan.part_torchat(self)
        else:
            con.send_msg('no such channel: '+args[0])
    def send_msg(self,msg):
        self.outcon.send_msg(msg)

    def on_chat(self,con,msg):
        con = self.outcon
        if msg.startswith('!'):
            parts = msg.split(' ')
            self.handle_cmd(con,parts[0][1:],parts[1:])
        elif self.chan is not None:
            self.chan.privmsg(self,msg)
            if self.server.link is not None:
                self.server.link.privmsg(self,self.chan,msg)
        else:
            con.send_msg('not in a channel')

    def on_connected(self,con):
        self.onion = con.onion
        self.incon = con
        self.parent.clients[self.onion.replace('.onion','')] = self
        self.dbg('tc connected')
        
    def on_disconnected(self,con):
        self.dbg('tc disconnected')
        if self.chan is not None:
            self.chan.part_torchat(self)
        if self.onion is not None:
            onion = self.onion.replace('.onion','')
            if onion in self.parent.onions:
                self.parent.onions.pop(onion)
            if onion in self.parent.clients:
                self.parent.clients.pop(onion)

    def pump(self,con):
        while len(self.sendq) > 0:
            con.send_line(self.sendq.pop())

    def __str__(self):
        return self.onion+'!torchat@'+self.server.name
