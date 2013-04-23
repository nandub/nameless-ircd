#
# torchat driver
#
import socket
from asynchat import asyc_chat as chat
from asyncore import dispatcher


class torchat(dispatcher):
    

    def __init__(self,host='127.0.0.1',port=11009):
        dispatcher.__init__(self)
        self.create_socket(socket.AF_INET,socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((host,port))
        self.listen(5)
