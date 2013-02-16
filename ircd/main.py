#!/usr/bin/env python
import server
import user
import signal, traceback, asyncore
serv = None
def hup(sig,frame):
    print 'reload'
    try:
        global serv
        serv.reload()
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
    ap.add_argument('-6',action='store_const',const=True, default=False,dest='ipv6',help='use ipv6')
    args = ap.parse_args()
    if hasattr(signal,'SIGHUP'):
        signal.signal(signal.SIGHUP,hup)
    log = False
    if args.opt is not None:
        log = args.opt.strip() == 'log'
    poni = args.pony
    if poni is not None:
        print 'Pony mode enganged'
    global serv
    serv = server.Server((args.host,args.port),do_log=log,poni=poni,ipv6=args.ipv6)
    server.admin(serv,'admin.sock')
    asyncore.loop()



if __name__ == '__main__':
    main()
