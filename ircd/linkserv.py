from services import Service, admin
from user import User
from util import socks_connect
from asynchat import async_chat
from asyncore import dispatcher
import json,socket,os,base64,threading,struct,traceback, time
import link_protocol, util

class listener(dispatcher):
    
    def __init__(self,parent):
        dispatcher.__init__(self)
        self.parent = parent
        self.create_socket(socket.AF_INET,socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(self.parent.bind_addr)
        self.listen(5)
        self.dbg = lambda m : self.parent.dbg('linkserv Listener>> %s'%m)

    def handle_accept(self):
        p = self.accept()
        if p is not None:
            sock,addr = p
            self.dbg('got connection from %s'%[addr])
            link_recv(sock,self.parent)

class link(async_chat):
    """
    s2s TL;DR 

    servers pass arround JSON Objects that are signed by their senders
    server could possibly unpack messages and claim they are from them
    by repacking the json object as their own.

    Nothing much can stop that so nothing will be done about it.
    """

    def __init__(self,sock,parent,name='?'):
        async_chat.__init__(self,sock)
        self.parent = parent
        self.server = parent.server
        self.set_terminator(self.parent.delim)
        self.ibuffer = ''
        self.state = 0
        self.name = name
        self.syncing = False
        self.dbg = lambda m : self.parent.dbg('link-%s %s'%(self.name,m))
        self.handle_error = self.server.handle_error
        self.init()

    @util.deprecate
    def sign(self,data):
        return link_protocol.sign(data)

    @util.deprecate
    def verify(self,data,sig):
        try:
            link_protocol.verify(data,sig)
            return data
        except:
            self.server.handle_error() # report error
            return None

    def gen_id(self):
        # probably won't be a problem for a while
        return int(time.time())

    def send_msg(self,data):
        data['id'] = self.gen_id()
        self.dbg('send '+str(data))
        data = json.dumps(data)
        self.push(data)
        self.push(link_protocol.delim)
        
    def collect_incoming_data(self,data):
        self.ibuffer += data

    def found_terminator(self):
        data = self.ibuffer
        self.ibuffer = ''
        if data is None:
            # drop unverifiable messages
            return 
        try:
            j = json.loads(data)
            self.dbg('Got Messsge '+str(j))
        except:
            self.bad_fomat()
            self.handle_error()
            return
        if 'error' in j:
            self.dbg('ERROR: %s'%j['error'])
            return
        self.on_message(j)

    def error(self,msg):
        self.dbg('error: %s'%msg)
        self.send_msg({'error':msg})
        self.close_when_done()

    def bad_format(self):
        self.error('bad format')

    def request_sync(self):
        self.send_msg({'sync':'sync'})

    def parse_sync(self,data):
        if 'sync' not in data:
            return False
        if data['sync'] == 'done':
            self.syncing = False
            return
        elif data['sync'] == 'sync':
            self.send_sync()
        else:
            if 'chans' in data['sync']:
                for chan in data['sync']['chans']:
                    for attr in ['topic','name']:
                        if attr not in chan:
                            self.error('channel format')
                            return
                    if chan['name'][0] not in ['&','#']:
                        self.error('channel format')
                        return
                    if chan['name'] not in self.server.chans:
                        self.server.chans[chan['name']] = Chan(chan['name'],self.server)
                        self.server.chans[chan['name']].set_topic(chan['topic'])
            if 'users' in data['sync']:
                for user in data['sync']['users']:
                    for attr in ['nick','chans']:
                        if attr not in user:
                            self.error('user format')
                            return
                    if user['nick'] not in self.server.users:
                        user = link_user(self,user['nick'])
                        self.server.users[user.nick] = user
                        for chan in user['chans']:
                            self.server.join_channel(self.server.users[user['nick']],chan)
        return True



    def send_sync(self):
        users = self.server.users.values()
        users = filter(lambda u : not u.nick.endswith('serv') , users)
        usersent = []
        for user in users:
            usersent.append({ 'nick' : user.nick, 'chans' : user.chans })
            
        chansent = []
        for chan in self.server.chans.values():
            chansent.append({'name':chan.name,'topic':chan.topic})
        self.send_msg({
                'sync':{
                    'chans':chansent,
                    'users':usersent
                    }
                })
        self.send_msg({'sync':'done'})

    def on_message(self,data):
        pass

    def init(self):
        pass

    def parse_message(self,data):
        if self.parse_sync(data):
            return
        for e in ['data','event','dst','id']:
            if e not in data:
                self.bad_format()
                return
        self.got_message(data['event'],data['data'],data['dst'])
        expunge = False
        if dst[0] not in ['#','&']:
            if dst in self.servers.users:
                if not self.servers.users[dst].is_remote:
                    expunge = True
        if not expunge:
            self.parent.forward(raw)

    def got_message(self,event,data,dst):
        event = event.lower()
        if not hasattr(self,'_got_%s'%event):
            self.error('bad event')
            return
        try:
            getattr(self,'_got_%s'%event)(dst,data)
        except:
            self.handle_error()

    def _got_raw(self,dst,data):
        if dst[0] in ['&', '#'] :
            if dst in self.server.chans:
                dst = self.server.chans[dst]
            else:
                return
        else:
            if dst in self.server.users:
                dst = self.server.users[dst]
            else:
                return
        dst.send_raw(data)        


class link_user(User):

    def __init__(self,link,nick):
        self.link = link
        User.__init__(self,link.server)
        self.nick = nick
        self.usr = nick
        self.backlog = []
        self.is_remote = True
    
    def send_msg(self,msg):
        if self.link.syncing:
            self.backlog.append(msg)
        else:
            while len(self.backlog) > 0:
                self.link.send_msg(self.backlog.pop())
            self.link.send_msg({'data':msg,'event':'raw','dst':str(self)})

class link_send(link):

    def init(self):
        login = self.parent.get_login(self.name)
        if login is not None:
            self.send_msg({'server':self.server.name,'login':login})
            self.state += 1
        else:
            self.error('no auth for '+str(self.dest))

    def on_message(self,data):
      
        if self.state == 1:
            if 'auth' not in data:
                self.error('bad auth')
                return
            if data['auth'].lower() == 'ok':
                self.state += 1
        elif self.state == 2:
            self.request_sync()
            self.state += 1
        elif self.state == 3:
            self.parse_message(data)


class link_recv(link):

    def on_message(self,data):
        if self.state == 0:
            for e in ['server','login']:
                if e not in data:
                    self.bad_format()
                    return
            if self.parent.check(data['server'],data['login']):
                self.name = data['server']
                self.parent.links.append(self)
                self.server.send_admin('server linked: %s'%self.name)
                self.send_msg({'auth':'ok'})
                self.request_sync()
                self.state += 1
            else:
                self.error('bad auth')
        elif self.state == 1:
            self.parse_message(data)




class linkserv(Service):
    _yes =  ['y','yes','1','true']
    def __init__(self,server,config={}):
        Service.__init__(self,server,config=config)
        self.listener = None
        self.nick = 'linkserv'
        self.delim = link_protocol.delim
        self.links = []
        if 'fname' in self.config:
            self._cfg_fname = self.config['fname']
        else:
            self._cfg_fname = 'linkserv.json'
        self._lock = threading.Lock()
        self._unlock = self._lock.release
        self._lock = self._lock.acquire
        self.reload(self.dbg)

    def get_login(self,dest):
        j =  self.get_cfg()
        if 'links' in j and dest in j['links']:
            return j['links'][dest]
        return None
    
    def forward_data(self,data):
        for link in self.links:
            link.push(data)
            link.push(link_protocol.delim)

    def start_listener(self):
        j = self.get_cfg()
        if 'bindaddr' in j:
            host,port = tuple(j['bindaddr'].split(':'))
            self.bind_addr = (host,int(port))
        else:
            self.bind_addr = ('127.0.0.1', 9991)
        if self.listener is not None:
            self.listener.close()
        self.listener = listener(self)

    @admin
    def serve(self,server,user,msg,resp_hook):
        msg = msg.strip()
        p = msg.split(' ')
        if msg == 'list':
            self.list_links(user)
        elif msg == 'reload':
            resp_hook('reloading...')
            if self.attempt(lambda : self.reload(resp_hook),resp_hook):
                resp_hook('reloaded')
        elif msg == 'link':
            resp_hook('starting link')
            if self.attempt(lambda : self.connect_all(resp_hook),resp_hook):
                resp_hook('Done')
        elif msg == 'kill':
            resp_hook('killing all links')
            if self.attempt(self.kill_links) and self.attempt(self.wait_for_links_dead):
                resp_hook('killed links')

    def list_links(self,hook):
        if len(self.links) == 0:
            hook('NO LINKS')
        for link in self.links:
            hook('LINK: %s'%link.name)
                
    def kill_links(self):
        while len(self.links) > 0:
            self.links.pop().close()

    def wait_for_links_dead(self):
        pass

    def reload(self,hook):
        self.start_listener()
        self.kill_links()
        j = self.get_cfg()
        if 'autoconnect' in j and str(j['autoconnect']) in self._yes:
            self.connect_all(hook)

    @util.deprecate
    def _fork(self,f):
        def func():
            try:
                f()
            except:
                for line in traceback.format_exc():
                    self.server.send_admin('link error: %s'%line)
        threading.Thread(target=func,args=()).start()


    def connect_all(self,hook):
        j = self.get_cfg()
        self.server.send_global('this server will freeze for syncing')
        def connect(link,login):
            hook('connect '+str(link)+' '+str(login))
            if not link.startswith('127.'):
                host,port = tuple(j['tor'].split(':'))
                if link.endswith('.i2p'):
                    host,port = tuple(j['i2p'].split(':'))
                port = int(port)
                sock, err = socks_connect(login,9999,(host,port))
            else:
                sock = socket.socket()
                host,port = tuple(link.split(':'))
                sock.connect((host,int(port)))
                err = None
            if err is not None:
                hook('link error: %s %s'%(link,err))
            else:
                hook('start link: %s'%link)
                link_send(sock,self,link)

        for link, login in j['links'].items():
            self.server.send_global('syncing')
            connect(link,login)
        self.server.send_global('server done syncing, have a nice day')


    def get_cfg(self):
        self._lock()
        with open(self._cfg_fname) as r:
            j = json.load(r)
        self._unlock()
        return j

    def set_cfg(self,cfg):
        self._lock()
        with open(self._cfg_fname,'w') as w:
            json.dump(cfg,w)
        self._unlock()
        

    def check(self,server,login):
        j = self.get_cfg()
        if server not in j['links']:
            if 'allow_all' not in j:
                return False
            elif str(j['allow_all']).lower() in self._yes :
                j['links'][server] = login
                self.set_cfg(j)
                return self.check(server,login)
            else:
                return False
        return login == j['links'][server]


