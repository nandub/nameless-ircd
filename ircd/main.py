#!/usr/bin/env python
import server
import user
import signal, traceback, asyncore

def hup(sig,frame):
    print 'reload'
    try:
        reload(server.user)
        reload(server.services)
        reload(server)
    except:
        print 'Error reloading'
        print traceback.format_exc()
    else:
        print 'okay'


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--port',type=int,help='port to run on',default=6666)
    ap.add_argument('--host',type=str,help='bind host',default='127.0.0.1')
    ap.add_argument('--opt',type=str,help='options',default=None)
    ap.add_argument('--pony',type=str,help='pony mode',default=None)
    args = ap.parse_args()
    if hasattr(signal,'SIGHUP'):
        signal.signal(signal.SIGHUP,hup)
    log = False
    if args.opt is not None:
        log = args.opt.strip() == 'log'
    poni = args.pony is not None
    if poni:
        print 'Pony mode enganged'
    serv = server.Server((args.host,args.port),do_log=log,poni=poni)
    server.admin(serv,'admin.sock')
    asyncore.loop()



if __name__ == '__main__':
    main()
