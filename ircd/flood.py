import time

class flood:
    """
    flood detetcion and control object
    """

    def __init__(self):
        self.objs = dict()
        self.hist = 50
        self.lines_per_interval = 10
        self.bytes_per_interval = 1024
        self.word_spam = 50
        self.pm_per_target = 5
        self.interval = 3

    def filter(self,line):
        """
        get list of "spam sources" from line
        """
        if '!' in line:
            i = src.index('!')
            yield src[1:][:i] # user
        
    def now(self):
        """
        time right now
        """
        return int(time.time())

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

    def check_flood(self):
        """
        return a generator that gives the current things that are flooding
        """
        for src in self.objs:
            # not in object tracker?
            # add to object tracker
            # return false

            # get history of object
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
                if len(dt[tstamp]) > self.lines_per_interval:
                    return True
                bsum = 0
                for l in lines[tstamp]:
                    bsum += len(l)
                    # if there are enough bytes in this interval block they are flooding
                    if bsum > self.bytes_per_interval:
                        yield user
                        
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
                            yield src
                            
