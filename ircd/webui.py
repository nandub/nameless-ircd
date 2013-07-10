import user
from cherrypy import tools, expose
import threading, traceback


class webuser(user.User):

    def __init__(self,server):
        user.User.__init__(self,server)
        self._q = []
        self._qlock = threading.Lock()
        self.send_raw = lambda msg : self._q_access(self._send_raw,msg)
        # verbose error messages?
        self._err_verbose = False

    def _q_access(self,func,*args,**kwds):
        """
        lock send queue 
        call function
        handle exceptions
        do it properly
        """
        ret = None
        self._qlock.acquire()
        try:
            ret = func(*args,**kwds)
        except:
            raise
        finally:
            self._qlock.release()
        return ret

    def _send_raw(self,line):
        self._q.append(line)
        

    def _format_err(self,exc):
        return str(exc) + self._err_verbose and '\n%s' % traceback.format_exc() or ''

    @api_require_session
    def _api_poll(self,args):
        """
        poll off all waiting messages
        """
        send = []
        def func(ls):
            while len(self._q) > 0:
                ls.append(self._serialize_line(self._q.pop()))
        self._q_access(func,send)
        return send

    def _serialize_line(self,line):
        """
        serialize irc line to json object
        """
        parts = line.split(':')


    def _irc_sanitize(self,line):
        """
        sanitize irc line from input
        """
        return line.replace('\n','').replace('\r','')

    @api_require_session
    def _api_send(self,args):
        """
        send a list of lines
        a line is a json object
        attributes are cmd,target,param , values must be strings
        """
        for line in args:
            for arg in ['cmd','target','param']:
                if arg not in line:
                    raise Exception('need argument: '+arg)
        
            l = str(args['cmd']).upper().strip()
            l += ' ' + str(args['target']).strip()
            l += ' :' + str(args['param'])
            l = self._irc_sanitize(l)
            self.handle_line(l)

    @tools.jsonify()
    def api(self,cmd,args):
        """
        main interaction point for web user via ajax json
        """
        _cmd = '_api_%s'%cmd
        if hasattr(self,_cmd):
            try:
                return {'status':'okay', 'response' : getattr(self,_cmd)(args)}
            except Exception as e:
                return {'status':'error', 'response' : self._format_err(e)} 
        return {'status':'error','response':'no such api command: %s'%cmd}
