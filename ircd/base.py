from nameless import util


class BaseObject:
    '''
    base data model object
    '''
    is_torchat = False
    is_service = False
    is_remote = False
    nick = ''
    usr = ''
    def __init__(self,server):
        if server is None:
            raise Exception('cannot give None as argument')
        self.server = server

    def get_full_name(self):
        '''
        get full user name
        '''
        return self.nick + '!user@' + self.server.name
