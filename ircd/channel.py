from util import locking_dict, trace
import util

class Channel:
    '''
    irc channel object
    '''
    def __init__(self,name,server):
        self.users = []
        self.server =  server
        self.name = str(name)
        self.topic = util.get(self.name)
        self.link = server.link
        # is anon means that the channel does not relay nicknames
        self.is_anon = self.name[0] == '&'
        self.empty = lambda : len(self.users) == 0
        # is invisible means that parts and joins are not relayed and the 
        # channel is not in the server channel list
        self.is_invisible = self.name[1] == '.'
        self._trips = locking_dict()
        self.remotes = []
        self.limit = 300
    
    
    def expunge(self,reason):
        for user in self.remotes:
            self.send_raw(':'+user+' PART '+self.name+' :'+reason)
        self.remotes = []
        for user in self.users:
            self.part_user(user,reason=reason)
        
        
    @trace
    def set_topic(self,user,topic):
        '''
        set the topic by a user to string topic
        '''
        if user is not None and user not in self.users:
            user.send_num(442, self.name+" :You're not on that channel")
            return
        self.topic = topic
        util.put(self.name,topic)
        self.send_topic()
        if self.link is not None and user is not None:
            self.link.topic(self.name,self.topic)
    @trace
    def send_raw(self,msg):
        '''
        send raw to all users in channel
        '''
        for user in self.users:
            user.send_raw(msg)

    def __str__(self):
        return self.name

    def __len__(self):
        return len(self.users) + len(self.remotes)

    def send_topic(self):
        '''
        send topic to all users in channel
        '''
        for user in self.users:
            self.send_topic_to_user(user)

    @trace
    def add_trip(self,user):
        if user.id not in self._trips:
            self._trips[user.id] = []
        self._trips[user.id].append(user.get_full_trip())
        self.send_raw(':'+user.get_full_trip()+' JOIN '+self.name)
        if self.link is not None:
            self.link.join(user.get_full_trip(),self.name)
    @trace
    def remove_trip(self,user):
        if user.id in self._trips:
            for trip in self._trips[user.id]:
                self._inform_part(trip,'durr')
            self._trips[user.id] = []
        
    
    def send_topic_to_user(self,user):
        '''
        send topic to user
        '''
        if user not in self.users:
            return
        if self.topic is None:
            user.send_num(331,'%s :No topic is set'%self.name)
            return

        user.send_num(332 ,self.name+' :'+self.topic)

    @trace
    def joined(self,user):
        ''' 
        called when a user joins the channel
        '''
        for u in self.users:
            if u.nick == user.nick:
                user.send_num('443',str(user)+' '+str(self)+' :is already on channel')
                return
        if len(self) > self.limit:
            user.notice(self.name,'channel is full')
            return
        # add to users in channel
        self.users.append(user)
        
        if self.is_anon:
            # send join to just the user for anon channel
            user.event(str(user),'join',self.name)
        else:
            # otherwise broadcast joi
            if self.link is not None:
                self.link.join(user,self.name)
            for u in self.users:
                u.event(str(user),'join',self.name)
        # send topic
        self.send_topic_to_user(user)
        # send who
        self.send_who(user)


    def part_user(self,user,reason='durr'):
        self._user_quit(user,reason)

    def _inform_part(self,user,reason):
        if not self.is_anon: # case non anon channel
            for u in self.users:
                # send part to all users
                u.action(user,'part',reason,dst=self.name)
            if self.link is not None:
                self.link.part(user,self.name,dst=reason)
        

    def _user_quit(self,user,reason):
        '''
        called when a user parts the channel
        '''
        # remove from channel
        if user in self.users: 
            self.users.remove(user) 
        if user.id in self._trips:
            for trip in self._trips[user.id]:
                self._inform_part(trip,reason)
        # send part to user
        user.action(user,'part',reason,dst=self.name)
        self._inform_part(user,reason)
        # inform channel if needed
        # expunge empty channel
        if self.empty():
            self.server.remove_channel(self.name)
    @trace
    def privmsg(self,orig,msg):
        '''
        send a private message from the channel to all users in the channel
        '''
        for user in self.users:
            if user == orig:
                continue
            src = 'nameless!user@' + str(self.server.name)
            if not self.is_anon: # case non anon channel
                src = str(orig)
            # send privmesg
            user.privmsg(src,msg,dst=self)
        
    def send_who(self,user):
        '''
        send WHO to user
        '''
        # mode for channel to send in response
        mod = '=' or self.is_invisible and '@' 
        nicks = user.nick
        if self.is_anon:
             nicks += ' nameless'
        else:
            for u in self.users:
                if u.nick == user.nick:
                    continue
                nicks += ' ' + u.nick

        user.send_num(353,'%s %s :%s'%(mod, self.name,nicks.strip()))
        nicks = ''
        for u in self.remotes:
            nicks += u.split('!')[0]
            nicks += ' '
        nicks = nicks.strip()
        if len(nicks) > 0:
            user.send_num(353,'%s %s :%s'%(mod, self.name,nicks))
        user.send_num(366,'%s :End of NAMES list'%self.name)

    @trace
    def join_remote_user(self,name):
        if len(self) < self.limit:
            self.remotes.append(name)
            self.send_raw(':'+name+' JOIN :'+self.name)
        else:
            if self.link is not None:
                self.link.send_line(':'+name+' NOTICE '+self.name+' channel is full')
                
    @trace
    def part_remote_user(self,name,reason):
        self.remotes.remove(name)
        self._inform_part(name,reason)
    @trace
    def has_remote_user(self,name):
        return name in self.remotes
