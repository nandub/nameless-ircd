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
    s2s link connector
    """

    def __init__(self,sock,parent,name='?'):
        async_chat.__init__(self,sock)
        self.parent = parent
        self.server = parent.server
        self.set_terminator(self.parent.delim)
        self.ibuffer = ''
        self.name = name
        self.syncing = False
        self.dbg = lambda m : self.parent.dbg('link-'+str(name)+': '+str(m))
        self.handle_error = self.server.handle_error
        self.init()

    def send_msg(self,data):
        self.send_raw(data)

    def collect_incoming_data(self,data):
        self.ibuffer += data

    def found_terminator(self):
        data = self.ibuffer
        self.ibuffer = ''
        '''
        :Name COMMAND parameter list
        '''
        p = data.split(' ')
        if data[0] == ':':
            if len(p) > 3:
                name = p[0][1:]
                cmd = p[1]
                param = p[2]
                ls = p[3].split(',')
                if hasattr(self,'on_'+cmd):
                    getattr(self,'on_'+cmd)(name,param,ls)
            else:
                self.err('bad data from '+self.name+': '+str([data]))

    def error(self,msg):
        self.server.err('linkerror: '+str(msg))
        self.close_when_done()


    def send_raw(self,data):
        self.push(data+'\r\n')
        
        

class link_user(User):

    def __init__(self,link,nick):
        self.link = link
        User.__init__(self,link.server)
        self.nick = nick
        self.usr = nick
        self.backlog = []
        self.is_remote = True
    
    def send_msg(self,msg):
        pass

class link_send(link):
    def init(self):
        self.send_raw('')

class link_recv(link):
    pass


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

    def inform_links(self,data):
        for link in self.links:
            link.sendmsg(data)
    
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
        self.dbg('using bindhost %s:%s'%self.bind_addr)
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
        self.dbg('check server='+str(server)+' login='+str(login))
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


