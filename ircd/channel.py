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
        self.torchats = []
        self.limit = 300
        self.key = None
    
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
        for u in self.users:
            if u != user:
                self.send_topic_to_user(u)
        if self.link is not None and user is not None and not self.is_invisible:
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

    def set_key(self,user,key):
        if not self.is_invisible or self.key is not None:
            return
        if user.nick.count('|') > 0:
            self.key = (user.nick,key)
            if self.is_anon:
                user = 'nameless!nameless@irc.nameless.tld'
            for u in self.users:
                u.send_raw(':'+str(user)+' MODE '+str(self)+' +k '+key)

    def unset_key(self,user):
        if not self.is_invisible or self.key is None:
            return
        if self.key[0] == user.nick:
            self.key = None
            if self.is_anon:
                user = 'nameless!nameless@irc.nameless.tld'
            for u in self.users:
                u.send_raw(':'+str(user)+' MODE '+str(self)+' -k')

    @trace
    def joined(self,user):
        ''' 
        called when a user joins the channel
        '''
        tc = hasattr(user,'onion')
        if not tc:
            for u in self.users:
                if u.nick == user.nick:
                    user.send_num('443',str(user)+' '+str(self)+' :is already on channel')
                    return
        if len(self) > self.limit:
            user.notice(self.name,'channel is full')
            return
        # add to users in channel
        if not tc:
            self.users.append(user)
        
        if self.is_anon:
            # send join to just the user for anon channel
            if not tc:
                user.event(str(user),'join',self.name)
        else:
            # otherwise broadcast join
            if self.link is not None and not self.is_invisible:
                self.link.join(user,self.name)
            for u in self.users:
                u.event(str(user),'join',self.name)
        if not tc:
            # send topic
            self.send_topic_to_user(user)
            # send who
            self.send_who(user)
        msg = tc and 'torchat user '+user.onion+' joined the channel' or 'user '+str(user).split('!')[0] + ' joined the channel'
        for u in self.torchats:
            u.send_msg(msg)

    def part_user(self,user,reason='durr'):
        self._user_quit(user,reason)

    def _inform_part(self,user,reason):
        nick = str(user).split('!')[0]
        if not self.is_anon: # case non anon channel
            for u in self.users:
                # send part to all users
                u.action(nick,'part',reason,dst=self.name)
            if self.link is not None and not self.is_invisible:
                self.link.part(str(user),self.name,dst=reason)
            tc = hasattr(user,'onion')
            msg = tc and 'torchat user '+user.onion+' left the channel' or 'user '+nick+ ' left the channel'
            for u in self.torchats:
                u.send_msg(u)
                
                
    def _user_quit(self,user,reason):
        '''
        called when a user parts the channel
        '''
        tc = hasattr(user,'onion')
        # remove from channel
        if user in self.users and not tc: 
            self.users.remove(user) 
        if not tc and user.id in self._trips:
            for trip in self._trips[user.id]:
                self._inform_part(trip,reason)
        # send part to user
        if not tc:
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

        src = str(orig)

        if self.is_anon:
            src = 'nameless!nameless@' + str(self.server.name)

        for user in self.users:
            if user == orig:
                continue
            # send privmesg
            user.privmsg(src,msg,dst=self)

        for tc in self.torchats:
            if orig == tc:
                continue
            tc.privmsg(src.split('!')[0],msg)


    def join_torchat(self,tc):
        if self.key is None:
            if tc not in self.torchats:
                self.torchats.append(tc)
                self.joined(tc)
            else:
                tc.send_msg('already in channel '+self.name)
        else:
            tc.send_msg('cannot join password protected channel')

    def part_torchat(self,tc):
        if tc in self.torchats:
            self.torchats.remove(tc)
            tc.send_msg('left channel '+self.name)
            self.part_user(tc)
        else:
            tc.send_msg('not in channel '+self.name)

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
        if self.is_invisible:
            return
        nick = name.split('!')[0]
        for tc in self.torchats:
            if tc.onion == nick:
                if self.link is not None:
                    self.link.notice(self.name,nick,'will not join spoofed torchat user :p')
                return
        if len(self) < self.limit:
            self.remotes.append(name)
            self.send_raw(':'+name+' JOIN :'+self.name)

    @trace
    def part_remote_user(self,name,reason):
        if name in self.remotes and not self.is_invisible:
            self.remotes.remove(name)
            self.send_raw(':'+name+' PART :'+self.name)
            
    @trace
    def has_remote_user(self,name):
        nick = name.split('!')[0]
        for remote in self.remotes:
            if nick == remote.split('!')[0]:
                return True
        for tc in self.torchats:
            if tc.onion == nick:
                return True
        return nick in self.users and not self.is_invisible
