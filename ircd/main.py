#!/usr/bin/env python
import server, user, adminserv, util, s2s
import signal, traceback, asyncore, json, sys
from threading import Thread

serv = None
def hup(sig,frame):
    '''
    called on SIGHUP
    '''
    print ('reload')
    try:
        global serv
        serv.reload()
    except:
        print ('Error reloading')
        print (traceback.format_exc())
    else:
        print ('okay')

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--port',type=int,help='port to run on',default=6667)

    ap.add_argument('--host',type=str,help='bind host',default='127.0.0.1')

    ap.add_argument('--debug',action='store_const',const=True, default=False,
                    dest='log',help='enable debug mode by default')

    ap.add_argument('--conf',type=str,help='config file',default=None)

    ap.add_argument('-6',action='store_const',const=True, default=False,
                    dest='ipv6',help='use ipv6')

    ap.add_argument('--trace',action='store_const',const=True,default=False,
                    dest='trace',help='function debug trace')

    ap.add_argument('--name',type=str,help='server name',default='nameless')

    ap.add_argument('--no-admin',action='store_const',const=False,default=True,
                    dest='admin',help='disable adminserv')

    ap.add_argument('--adminport',type=int,help='adminserv port',default=6666)

    ap.add_argument('--onion-urc',type=str,help='onion addres for s2s via URC',default=None)

    ap.add_argument('--i2p-urc',type=str,help='i2p destination for s2s via URC',default=None)

    ap.add_argument('--local-urc',type=str,help='port for s2s via URC on loopback',default=None)

    ap.add_argument('--link-port',type=int,help='linkserv port to bind on',default=6660)

    ap.add_argument('--no-link',action='store_const',const=True,default=False,
                    dest='no_link',help='disable incoming links')
    # parse args
    args = ap.parse_args()
    # check for SIGHUP
    if hasattr(signal,'SIGHUP'):
        signal.signal(signal.SIGHUP,hup)
    log = args.log
    global serv
    # make server 
    cfgs = { }
    if args.conf is not None:
        with open(args.conf) as r:
            cfgs = json.load(r)
    else:
        cfgs = {}
    if args.admin:
        cfgs['adminserv'] = ''
    util.toggle_trace = args.trace
    serv = server.Server((args.host,args.port),args.name,do_log=log,ipv6=args.ipv6,configs=cfgs)
    # make adminserv
    #if args.admin:
    #    adminserv.handler(serv,port=args.adminport)
    # start mainloop
    for t in serv.threads:
        t.start()
    link = not args.no_link
    if link:
        print ('enabling link')
    link = s2s.linkserv(serv,('127.0.0.1',args.link_port),allow_link=link)
    if args.onion_urc:
        link.tor_link(args.onion_urc,6660)
    elif args.i2p_urc:
        link.i2p_link(args.i2p_urc)
    elif args.local_urc:
        link.local_link(args.local_urc)
    serv.link = link
    # run mainloop
    try:
        asyncore.loop(timeout=10)
    except KeyboardInterrupt:
        # kill threads
        serv.stop()


if __name__ == '__main__':
    main()
