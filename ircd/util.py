# -*- coding: utf-8 -*-

import base64, hashlib, os, hmac, functools, inspect, string, json, sys, socket, struct, threading
from functools import wraps


class locking_dict(dict):

    def __init__(self,*args,**kwds):
        dict.__init__(self,*args,**kwds)
        self._lock = threading.Lock()
    def __iter__(self):
        self._lock.acquire()  
        ret = list(self.keys())
        self._lock.release()
        return ret.__iter__()
    


def _tripcode(user,secret,salt):
    code = b''
    data = str(user)
    data += '|'+str(secret)
    for digest in ['sha512','sha256']:
        h = hashlib.new(digest)
        h.update(data.encode('utf-8',errors='replace'))
        h.update(code)
        h.update(salt)
        code = h.digest()
        del h
    h = hmac.new(salt)
    h.update(code)
    code = h.digest()
    trip = base64.b32encode(code).replace(b'=',b'')
    trip = trip[ int( len(trip) / 2 ) :]
    return (user+b'|'+trip).decode('utf-8',errors='replace')


def socks_connect(host,port,socks_host):
    s = socket.socket()
    s.connect(socks_host)
    # socks connect
    s.send(struct.pack('BB',4,1))
    s.send(struct.pack('!H',port))
    s.send(struct.pack('BBBB',0,0,0,1))
    s.send(b'proxy\x00')
    s.send(host.encode('ascii'))
    s.send(b'\x00')
    # socks recv response
    d = s.recv(8)
    if len(d) != 8 or d[0] != 0:
        return None, 'Invalid Response From Socks Proxy : '+str(d)
    if d[1] == 90:
        return s , 'Connection Okay'
    else:
        return None, 'Socks Error got response code %s'%[d[1]]

def filter_unicode(data):
    # for marcusw's utf-8 allergies
    # meh nvm
    return data # data.replace(u'\u200F',u'')
    #ret = ''
    #for c in str(data):
    #    if ord(c) >= 128:
    #        ret += '?'
    #    else:
    #        ret += c
    #return ret

_salt = 'salt'
if os.path.exists('salt'):
    with open('salt') as s:
       _salt = bytes(s.read(),'ascii')


#_symbols = ''
#for n in range(128):
#    if n > 0 and chr(n) not in string.letters:
#        _symbols += chr(n)
    
def filter_message(s,replacement,whitelist):
    s = filter_unicode(s)
    parts = []
    last = ''
    # assume first word is "good"
    is_word = True
    # split word into parts
    # each part are alternating "word" and "not word"
    # a "word" is something that is qualified to be
    # checked against the whitelist
    for ch in s:
        # does letter have a different "symbolness" than the last
        # then add it to the part list
        if ( ch in _symbols ) ^ is_word:
            parts.append((last,ch in string.ascii_letters ))
            is_word = not is_word
            last = ''
        last += ch
    ret = ''
    parts.append((last,not is_word))
    # for each word that is a "word"
    # check for it being not in the whitelist
    for part, is_word in parts:
        if part.lower() in whitelist:
            ret += part
        else:
            ret += is_word and replacement or part
    return ret


def deprecate(f):
    @wraps(f)
    def w(*args,**kwds):
        raise Exception('Attempted to call Deprecated function %s'%f.func_name)
    return w

def decorate(func): 
    def isFuncArg(*args, **kw):
        return len(args) == 1 and len(kw) == 0 and (inspect.isfunction(args[0]) or isinstance(args[0], type))
    
    if isinstance(func, type):
        def class_wrapper(*args, **kw):
            if isFuncArg(*args, **kw):
                return func()(*args, **kw) # create class before usage
            return func(*args, **kw)
        class_wrapper.__name__ = func.__name__
        class_wrapper.__module__ = func.__module__
        return class_wrapper
   
    @wraps(func)
    def func_wrapper(*args, **kw):
        if isFuncArg(*args, **kw):
            return func(*args, **kw)
        
        def functor(userFunc):
            return func(userFunc, *args, **kw)
           
        return functor
   
    return func_wrapper

@deprecate
def get_admin_hash():
    with open('admin.hash') as r:
        return r.read().strip()

def get_admin_hash_list():
    with open('admins.json') as r:
        return json.load(r)

toggle_trace = False

def trace(f):
    global toggle_trace
    @wraps(f)
    def wrapper(*arg,**kw):
        '''This decorator shows how the function was called'''
        if toggle_trace:
            arg_str=','.join(['%s'%[a] for a in arg]+['%s=%s'%(key,kw[key]) for key in kw])
            print ("%s(%s)" % (f.__name__, arg_str))
        return f(*arg, **kw)
    return wrapper

tripcode = lambda nick, trip : _tripcode(nick,trip,_salt)
i2p_connect = lambda host: socks_connect(host,0,('127.0.0.1',9911))
tor_connect = lambda host,port: socks_connect(host,port,('127.0.0.1',9050))

is_version = lambda major,minor : sys.version_info[0] == major and sys.version_info[1] == minor

use_3_3 = is_version(3,3)
