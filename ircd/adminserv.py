from asynchat import async_chat
from asyncore import dispatcher
import os, socket, time
import services, util
locking_dict = util.locking_dict

class adminserv(services.Service):
    
    def __init__(self,server,config={}):
        services.Service.__init__(self,server,config=config)
        self.nick = self.__class__.__name__
        self.cmds = locking_dict({
            'die':self.die,
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
            'flood':self.set_flood_kill,
            '?':self.send_help,
            'link':self.link_server,
            'delink':self.unlink_server,
            'quiet':self.quiet_user,
            'unquiet':self.unquiet_user,
            'check':self.toggle_force_check
            })

    def handle_line(self,line):
        class dummy:
            def __init__(self):
                self.nick = util.get_admin_hash_list()[0]

            def privmsg(self,*args,**kwds):
                pass
        self.privmsg(dummy(),line)

    @services.admin
    def serve(self,server,user,line,resp_hook):
        services.Service.serve(self,server,user,line,resp_hook)

    def link_server(self,user,args,resp_hook):
        """
        link to another server
        link local $port
        link i2p $i2pdest
        link onion $onion
        """
        if len(args) == 2:
            type = args[0]
            addr = args[1]
            if type == 'local':
                try:
                    addr = int(addr)
                except:
                    resp_hook('local link requires port number only')
                    return
                self.server.link.local_link(addr)
            elif type == 'i2p':
                self.server.link.i2p_link(addr)
            elif type == 'onion':
                self.server.link.tor_link(addr)
            else:
                resp_hook('bad link type: '+type)
        else:
            resp_hook('usage: link link_type link_address')

    def unlink_server(self,user,args,resp_hook):
        self.server.link.disconnect_all()
        resp_hook('delinked all servers')

    def toggle_force_check(self,user,args,resp_hook):
        """
        toggle dropping of old s2s protocol

        """
        self.server.force_check = not self.server.force_check
        resp_hook('drop old = %s'%self.server.force_check)

    def die(self,user,args,resp_hook):
        """
        turn sever off
        """
        reason = 'going offline'
        if len(args) > 0:
            reason = ' '.join(args)
        self.server.stop(reason)


    def limit(self,user,args,resp_hook):
        """
        rate limit actions, meant to replace ``flood''

        topic
            topic setting ratelimiting

        nick
            nickname changing

        privmsg#
            private messages to # channels

        privmsg&
            private messages to & channels
           
        join
            channel joining

        """
        resp = [ str(k) + ' : ' + str(v) for k,v in self.server.limits.items() ]
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
            if attr in self.server.limits:
                if val is not None:
                    self.server.limits[attr] = val
                resp = [attr + ' : ' + str(val)]
        for line in resp:
            resp_hook(line)


    def send_help(self,user,args,resp_hook):
        """
        show help message
        """
        resp_hook('commands:')
        for cmd, func in self.cmds.items():
            resp_hook(cmd)
            h = func.__doc__ or 'No Help'
            for line in h.split('\n'):
                resp_hook('-- '+line)
            resp_hook(' ')

    def toggle_debug(self,user,args,resp_hook):
        """
        toggle server debug mode
        """
        self.server.toggle_debug()
        resp_hook('DEBUG: %s' % self.server.debug())


    def quiet_user(self,user,args,resp_hook):
        """
        set quiet
        """
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.quiet = True
                
    def unquiet_user(self,user,args,resp_hook):
        """
        unset quiet
        """
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.quiet = False
                
    def nerf_user(self,user,args,resp_hook):
        """
        set mode +P on one or more users
        """
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.set_mode('+P')
                u.lock_modes()
                resp_hook('set mode +P on '+u.nick)
    def denerf_user(self,user,args,resp_hook):
        """
        unset mode +P on one or more users
        """
        for u in args:
            if u in self.server.users:
                u = self.server.users[u]
                u.unlock_modes()
                u.set_mode('-P')
                resp_hook('set mode -P on '+u.nick)

    def nerf_all(self,user,args,resp_hook):
        """
        set +P on every user
        """
        self.server.send_global('Global +P Usermode Set')
        for u in self.server.handlers:
            u.set_mode('+P')
            u.lock_modes()
        resp_hook('GLOBAL +P')

    def denerf_all(self,user,args,resp_hook):
        """
        unset -P on every user
        """
        self.server.send_global('Global -P Usermode Set')
        for u in self.server.handlers:
            u.unlock_modes()
            u.set_mode('-P')
        resp_hook('GLOBAL -P')

    def set_ping(self,user,args,resp_hook):
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

    
    def set_flood_kill(self,user,args,resp_hook):
        """
        set flood settings
        
        kill
           toggle kill on flood

        interval [float]
           flood interval in seconds

        bpi [integer]
           bytes per interval

        lpi [integer]
           lines per interval
        """
        resp = [
            'kill: '+str(self.server.flood_kill),
            'interval: '+str(self.server.flood_interval) ,
            'bpi: '+str(self.server.flood_bpi),
            'lpi: '+str(self.server.flood_lpi)
            ]
        if len(args) > 0:
            attr = args[0]
            val = None
            if len(args) > 1:
                try:
                    val = float(args[1])
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
            elif attr == 'kill':
                self.server.flood_kill = not self.server.flood_kill
                resp = ['kill: '+str(self.server.flood_kill)]
        for line in resp:
            resp_hook(line)

    def send_global(self,user,args,resp_hook):
        """
        send global message to all users
        """
        msg = ' '.join(args)
        self.server.send_global(msg)
        resp_hook('GLOBAL: %s'%msg)
    
    def count(self,user,args,resp_hook):
        """
        count server objects
        
        users
            count users

        chans
            count channels
        """
        if len(args) > 0:
            for targ in args:
                i = []
                targ = targ.lower()
                if len(targ) == 0:
                    continue
                elif targ == 'users':
                    i = self.server.users.values()
                elif targ == 'chans':
                    i = self.server.chans.values()
                resp_hook(str(len(i))+' '+targ+'s')
        else:
            resp_hook('Usage: COUNT [user|chan]')

    # still useful for debugging
    # undeprecated for now
    # adding more functionality 
    #@services.deprecated
    def list(self,user,args,resp_hook):
        """
        list server objects
        
        users
            list users

        chans
            list channels

        chan:&chan
        chan:#chan
            list users in channel
            
        user:nickname
            list channels user is in

        links
            list server links

        """
        if len(args) > 0:
            for targ in args:
                i = []
                targ = targ.lower()
                if len(targ) == 0:
                    continue
                elif targ == 'links':
                    i = self.server.link.links
                elif targ == 'users':
                    i = self.server.users
                elif targ == 'chans':
                    i = self.server.chans
                elif targ.count(':') > 0:
                    ind = targ.index(':')
                    t2,t1 = targ[ind+1:], targ[:ind]
                    if t1 == 'chan': 
                        # list users in channel as seen by server
                        i = t2 in self.server.chans and self.server.chans[t2].users or []
                        targ = t1 + ' has user'
                    elif t1 == 'user':
                        # list channels user is in as seen by server
                        i = t2 in self.server.users and self.server.users[t2].chans or []
                        targ = t1 + ' in channel'
                for obj in i:
                    resp_hook(targ+': '+str(obj))
        else:
            resp_hook('Usage: LIST [user|chan]')

    def kline(self,user,args,resp_hook):
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

