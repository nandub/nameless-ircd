class Channel:
    '''
    irc channel object
    '''
    def __init__(self,name,server):
        self.users = []
        self.server =  server
        self.topic = None
        self.name = str(name)
        # is anon means that the channel does not relay nicknames
        self.is_anon = self.name[0] == '&'
        self.empty = lambda : len(self.users) == 0
        # is invisible means that parts and joins are not relayed and the 
        # channel is not in the server channel list
        self.is_invisible = self.name[1] == '.'
        
    def set_topic(self,user,topic):
        '''
        set the topic by a user to string topic
        '''
        if user not in self.users:
            user.send_num(442, self.name+" :You're not on that channel")
            return
        self.topic = topic
        self.send_topic()

    def send_raw(self,msg):
        '''
        send raw to all users in channel
        '''
        for user in self.users:
            user.send_raw(msg)

    def __str__(self):
        return self.name

    def __len__(self):
        return len(self.users)

    def send_topic(self):
        '''
        send topic to all users in channel
        '''
        for user in self.users:
            self.send_topic_to_user(user)

    def send_topic_to_user(self,user):
        '''
        send topic to user
        '''
        if user not in self.users:
            return
        if self.topic is None:
            user.send_num(331,'%s :No topic is set'%self.name)
            return
        user.send_num(332 ,'%s :%s'%(self.name,self.topic))

    def joined(self,user):
        ''' 
        called when a user joins the channel
        '''
        for u in self.users:
            if u.nick == user.nick:
                user.send_num('443',str(user)+' '+str(self)+' :is already on channel')
                return
        # add to users in channel
        self.users.append(user)
        
        if self.is_anon:
            # send join to just the user for anon channel
            user.event(str(user),'join',self.name)
        else:
            # otherwise broadcast join
            for u in self.users:
                u.event(str(user),'join',self.name)
        # send topic
        self.send_topic_to_user(user)
        # send who
        self.send_who(user)

    def user_quit(self,user,reason='quitting'):
        '''
        called when a user parts the channel
        '''
        # check for in channel
        for u in self.users:
            if user.nick == u.nick:
                # remove from lists
                self.users.remove(u)
        # send part to user
        user.event(user,'part',self.name)
        # inform channel if needed
        if not self.is_anon: # case non anon channel
            for u in self.users:
                # send part to all users
                u.event(user,'part',self.name)
        # expunge empty channel
        if self.empty():
            self.server.remove_channel(self.name)

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
        user.send_num(366,'%s :End of NAMES list'%self.name)

