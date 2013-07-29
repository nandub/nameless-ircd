# -*- coding: utf-8 -*-

import base64, hashlib, os, hmac, functools, inspect, string
import json, sys, socket, struct, threading
try:
    import sqlite3
except ImportError:
    print ('no sqlite3, topics will not be stored')
    sqlite3 = None
from functools import wraps

chan_prefixs = ['&','#']

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

def get_salt():
    salt_file = get_setting('salt.file') or 'salt'
    _salt = 'salt'
    if os.path.exists(salt_file):
        with open(salt_file) as s:
            _salt = bytes(s.read(),'ascii')
    return _salt

_symbols = ''
for n in range(128):
    if n > 0 and chr(n) not in string.ascii_letters:
        _symbols += chr(n)

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

def get_admin_hash_list():
    fname = get_setting('admin.file') or 'admins.json'
    with open(fname) as r:
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


def init(_db='settings.db'):
    if sqlite3:
        c = sqlite3.connect(_db)
        cur = c.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS cache ( key TEXT , val TEXT )')
        cur.execute('CREATE TABLE IF NOT EXISTS settings ( key TEXT, val TEXT)')
        c.commit()
        c.close()

def put(k,v,settings=False,_db='settings.db'):
    if not sqlite3:
        return
    table = settings and 'settings' or 'cache'
    c = sqlite3.connect(_db)
    cur = c.cursor()
    cur.execute('SELECT count(val) FROM %s WHERE key = ?'%table,(k,))
    _v = cur.fetchone()[0]
    if _v > 0:
        cur.execute('UPDATE %s SET val = ? WHERE key = ?'%table,(v,k))
    else:
        cur.execute('INSERT INTO %s (key,val) VALUES ( ? , ? )'%table,(k,v))
    c.commit()
    c.close()

def get(k,settings=False,_db='settings.db'):
    if not sqlite3:
        return
    ret = None
    table = settings and 'settings' or 'cache'
    c = sqlite3.connect(_db)
    cur = c.cursor()
    cur.execute('SELECT count(val) FROM %s WHERE key = ?'%table,(k,))
    v = cur.fetchone()[0]
    if v > 0:
        cur.execute('SELECT val FROM %s WHERE key = ?'%table,(k,))
        ret =  cur.fetchone()[0]
    c.close()
    return ret


get_setting = lambda k : get(k,settings=True)
put_setting = lambda k,v : put(k,v,settings=True)


tripcode = lambda nick, trip : _tripcode(nick,trip,get_salt())
i2p_connect = lambda host: socks_connect(host,0,('127.0.0.1',int(get_setting('tor.socks.port') or 9911)))
tor_connect = lambda host,port: socks_connect(host,port,('127.0.0.1',int(get_setting('tor.socks.port') or 9050)))

is_version = lambda major,minor : sys.version_info[0] == major and sys.version_info[1] == minor

use_3_3 = is_version(3,3)

@trace
def dict_to_irc(d):
    """
    serialize a dict to an irc line
    """
    return ('src' in d and ':'+str(d['src']).strip()+' ' or '')+str(d['cmd']).strip()+('target' in d and ' '+ str(d['target']).strip() or '')+('param' in d and ' :'+str(d['param']) or '')

@trace
def irc_to_dict(line):
    """
    return dict describing irc line
    """
    d = {'src':None,'cmd':None,'target':None,'param':None}
    if len(line) == 0:
        return d
    if line[0] == ':':
        line = line[1:]
        parts = line.split()
        d['src'] = parts[0]
        parts = parts[1:]
    else:
        parts = line.split()
    l = len(parts)
    i = ':' in line and line.index(':') or -1
    if i != -1:
        d['param'] = line[i+1:]
    elif l == 3:
        d['param'] = parts[2]
    if l > 2:
        d['cmd'] = parts[0]
        d['target'] = parts[1]
    elif l == 2:
        d['cmd'] = parts[0]
        if i == -1:
            d['param'] = parts[1]
    elif l == 1:
        d['cmd'] = parts[0]
    return d

init()
