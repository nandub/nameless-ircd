from asyncore import dispatcher
import os, socket
import services, util

class handler(dispatcher):
    '''
    adminserv unix socket handler
    '''
    def __init__(self,server,path):
        if os.path.exists(path):
            os.unlink(path)
        self.server = server
        dispatcher.__init__(self)
        self.nfo = lambda m: self.server.nfo('adminloop: '+str(m))
        if not hasattr(socket,'AF_UNIX'):
            self.nfo('not using admin module')
            return
        self.create_socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        self.set_reuse_addr()
        self.bind(path)
        self.nfo('adminserv ready')

    def handle_read(self):
        '''
        read data and send each line to adminserv
        '''
        data = self.recv(1024)
        try:
            for line in data.split('\n'):
                self.nfo('adminserv got line '+line)
                if 'adminserv' in self.server.users:
                    self.server.users['adminserv'].handle_line(line)
        except:
            self.server.handle_error()



class adminserv(services.Service):
    
    def __init__(self,server,config={}):
        services.Service.__init__(self,server,config=config)
        self.nick = self.__class__.__name__
        self.cmds = {
            'debug':self.toggle_debug,
            'denerf':self.denerf_user,
            'nerf':self.nerf_user,
            'nerf_all':self.nerf_all,
            'denerf_all':self.denerf_all,
            'ping':self.set_ping,
            'global':self.send_global,
            'count':self.count,
            'list':self.list,
            'kill':self.kline,
            'help':self.send_help,
            'limit':self.limit,
            }

    def handle_line(self,line):
        class dummy:
            def __init__(self):
                self.nick = util.get_admin_hash()
                
            def privmsg(self,*args,**kwds):
                pass
        self.privmsg(dummy(),line)

    @services.admin
    def serve(self,server,user,line,resp_hook):
        services.Service.serve(self,server,user,line,resp_hook)


    def limit(self,args,resp_hook):
        """
        limit items
        """
        resp = []
        resp.append('topic: '+str(self.server.topic_limit) )
        if len(args) > 0:
            attr = args[0]
            val = None
            if len(args) > 1:
                try:
                    val = int(args[1])
                    if val <= 0:
                        raise Exception()
                except:
                    resp_hook('invlaid value: '+args[1])
                    return
            if attr == 'topic':
                if val is not None:
                    self.server.topic_limit = val
                resp = ['topic: '+str(self.server.topic_limit)]
        for line in resp:
            resp_hook(line)


    def send_help(self,args,resp_hook):
        """
        show help message
        """
        resp_hook('commands:')
        for cmd, func in self.cmds.items():
            resp_hook(cmd)
            h = func.func_doc or 'No Help'
            for line in h.split('\n'):
                resp_hook('-- '+line)
            resp_hook(' ')

    def toggle_debug(self,args,resp_hook):
        """
        toggle server debug mode
        """
        self.server.toggle_debug()
        resp_hook('DEBUG: %s' % self.server.debug())

    def nerf_user(self,args,resp_hook):
        """
        set mode +P on one or more users
        """
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.set_mode('+P')
                u.lock_modes()
                resp_hook('set mode +P on '+u.nick)
    def denerf_user(self,args,resp_hook):
        """
        unset mode +P on one or more users
        """
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.unlock_modes()
                u.set_mode('-P')
                resp_hook('set mode -P on '+u.nick)

    def nerf_all(self,args,resp_hook):
        """
        set +P on every user
        """
        self.server.send_global('Global +P Usermode Set')
        for u in self.server.handlers:
            u.set_mode('+P')
            u.lock_modes()
        resp_hook('GLOBAL +P')

    def denerf_all(self,args,resp_hook):
        """
        unset -P on every user
        """
        self.server.send_global('Global -P Usermode Set')
        for u in self.server.handlers:
            u.unlock_modes()
            u.set_mode('-P')
        resp_hook('GLOBAL -P')

    def set_ping(self,args,resp_hook):
        """
        set ping timeout
        """
        server = self.server
        if len(args) == 1:
            try:
                old = server.pingtimeout
                server.pingtimeout = int(args[0])
                if server.pingtimeout < 10:
                    server.pingtimeout = 10
            except:
                resp_hook('not a number')
        resp_hook('PING: '+str(server.pingtimeout)+' seconds')

    def set_flood_kill(self,args,resp_hook):
        """
        set floodkill settings

        interval [number]
           flood interval

        bpi [number]
           bytes per interval

        lpi [number]
           lines per interval
        """
        resp = []
        resp.append('interval: '+str(self.server.flood_interval) )
        resp.append('bpi: '+str(self.server.flood_bpi) )
        resp.append('lpi: '+str(self.server.flood_lpi) )
        if len(args) > 0:
            attr = args[0]
            val = None
            if len(args) > 1:
                try:
                    val = int(args[1])
                    if val <= 0:
                        raise Exception()
                except:
                    resp_hook('invlaid value: '+args[1])
                    return
            if attr == 'bpi':
                if val is not None:
                    self.server.flood_bpi = val
                resp = ['bpi: '+str(self.server.flood_bpi)]
            elif attr == 'lpi':
                if val is not None:
                    self.server.flood_lpi = val
                resp = ['lpi: '+str(self.server.flood_lpi)]
            elif attr == 'interval':
                if val is not None:
                    self.server.flood_interval = val
                resp = ['interval: '+str(self.server.flood_interval)]
        for line in resp:
            resp_hook(line)

    def send_global(self,args,resp_hook):
        """
        send global message to all users
        """
        msg = ' '.join(args)
        self.server.send_global(msg)
        resp_hook('GLOBAL: %s'%msg)
    
    def count(self,args,resp_hook):
        """
        count server objects
        
        user
            count users

        chan
            count channels
        """
        if len(args) > 0:
            for targ in args:
                i = []
                targ = targ.lower()
                if len(targ) == 0:
                    continue
                elif targ == 'user':
                    i = self.server.users.values()
                elif targ == 'chan':
                    i = self.server.chans.values()
                resp_hook(str(len(i))+' '+targ+'s')
        else:
            resp_hook('Usage: COUNT [user|chan]')
        
    def list(self,args,resp_hook):
        """
        list server objects
        
        user
            list users

        chan
            list channels
        """
        if len(args) > 0:
            for targ in args:
                i = []
                targ = targ.lower()
                if len(targ) == 0:
                    continue
                elif targ == 'user':
                    i = self.server.users
                elif targ == 'chan':
                    i = self.server.chans
                for obj in i:
                    resp_hook(targ+': '+str(obj))
        else:
            resp_hook('Usage: LIST [user|chan]')

    def kline(self,args,resp_hook):
        """
        kill one or more user's connections
        """
        for u in args:
            if u not in self.server.users:
                resp_hook('NO USER: '+str(u))
                continue
            u = self.server.users[u]
            u.kill('kline')
            resp_hook('KILLED '+str(u))

