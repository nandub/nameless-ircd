from asyncore import dispatcher
from asynchat import async_chat
import user
import socket

class linkuser:
    """
    remote user object
    """

    def __init__(self,parent):
        self.parent = parent
        self.server = parent.server
        self.modes = user.modes


    def privmsg(self,src,msg,dst=None):
        if 


class link(async_chat):
    """
    generic link
    """

    def __init__(self,sock,parent):
        self.parent = parent
        self.server = parent.server
        async_chat.__init__(self,sock)
        self.set_terminator('\r\n')
        self.ibuff = ''

    def collect_incoming_data(self,data):
        self.ibuff += data

    def found_terminator(self):
        buff = self.ibuff
        self.ibuff = ''

    def handle_error(self):
        self.parent.handle_error()
        self.handle_close()

    def handle_close(self):
        self.parent.on_link_closed(self)
        self.close()

class linkserv(dispatcher):
    """
    s2s manager
    """
    
    def __init__(self,parent,addr,cfg_file,ipv6=False):
        dispatcher.__init__(self)
        af = ipv6 and socket.AF_INET6 or socket.AF_INET
        self.create_socket(af,socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(addr)
        self.listen(5)
        self.server = parent
        self.links = []

    def on_link_closed(self,link):
        if link in self.links:
            self.links.remove(link)
        self.server.on_link_closed(self,link)

    def handle_error(self):
        self.server.handle_error()

    def handle_accept(self):
        pair = self.accept()
        if pair:
            sock, addr = pair
            self.links.append(inbound_link(sock,self))
