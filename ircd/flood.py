import time, util

class flood:
    """
    flood detetcion and control object
    """

    def __init__(self):
        self.objs = util.locking_dict()
        self.hist = 50
        self.lines_per_interval = 4
        self.bytes_per_interval = 1024 
        self.word_spam = 10
        self.pm_per_target = 5
        self.interval = 5
        self.ignore_interval = 60
        self.flooders = util.locking_dict()

    def filter(self,line):
        """
        get list of "spam sources" from line
        """
        if not line.startswith(':nameless!nameless@'):
            yield line.split(' ')[0][1:]
        
        #if '!' in line:
        #    i = src.index('!')
        #    yield src[1:][:i] # user
        
    def now(self):
        """
        time right now
        """
        return int(time.time())

    def add_flooder(self,src):
        if src not in self.flooders:
            self.flooders[src] = self.now()
            self.objs.pop(src)

    def on_line(self,line):
        """
        call when a source sends line
        """
        srcs = self.filter(line)
        # if not in object tracker
        # add to object tracker
        for src in srcs:
            if src not in self.objs:
                self.objs[src] = []
            # roll off old messages
            while len(self.objs[src]) > self.hist:
                self.objs[src].pop()
            # add new message
            self.objs[src].append((self.now(),line))

    def tick(self):
        self.check_flood()
        for f in self.flooders:
            if int(self.now()) - self.flooders[f] > self.ignore_interval:
                self.flooders.pop(f)
                self.check_src(f)
                if f not in self.flooders:
                    self.unchoke(f)
                
    def chock(self,src):
        pass
    def unchoke(self,src):
        pass

    def line_is_flooding(self,line):
        # may slow stuff down
        for f in self.flooders:
            if f in line:
                return True
        
    def check_src(self,src):
        if src not in self.objs:
            self.objs[src] = []
            return
        hist = list(self.objs[src])
            
        hist.reverse()
        lines = dict()
        #
        # all messages are grouped into interval blocks
        #
        # these blocks contain all events that happened 
        # in an interval
        # 
        # i = beginning of the interval block in unix time
        #
        # [ block 0 ] list of events between i0 and i1 
        # [ block 1 ] list of events between i1 and i2
        #  ...
        # [ block N ] list of events between iN-1 and iN 
        #
        for tstamp , line in hist:
            tstamp /= self.interval
            tstamp = int(tstamp)
            #
            # send rate limit
            #
            if tstamp not in lines:
                lines[tstamp] = []
            lines[tstamp].append(line)
            # if there are enough lines in this interval block they are flooding
            if len(lines[tstamp]) > self.lines_per_interval:
                self.add_flooder(src)
            bsum = 0
            for l in lines[tstamp]:
                bsum += len(l)
                # if there are enough bytes in this interval block they are flooding
                if bsum > self.bytes_per_interval:
                    self.add_flooder(src)
                        
        #    
        # word spam limiting
        #
        # for each interval block
        #
        # if word is repeated more than self.word_spam times
        # they are flooding
        #
        for ls in lines.values():
            words = dict()
            for line in ls:        
                if 'PRIVMSG' in line:
                    firstword = True
                    for word in line.split(' ')[3:]:
                        if firstword:
                            word = word[1:]
                            firstword = False
                        if word not in words:
                            words[word] = 0
                    words[word] += 1
            for word in words:
                if words[word] > self.word_spam:
                    self.add_flooder(src)
                            
    

    def check_flood(self):
        """
        return a generator that gives the current things that are flooding
        """
        for src in self.objs:
            self.check_src(src)
